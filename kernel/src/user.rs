//! Userland bring-up — Month 4, the ring-3 entry.
//!
//! `bring_up()` maps a user code page + a user stack (U/S), gives the syscall
//! path a dedicated kernel stack + a TSS RSP0, programs the syscall MSRs, and
//! descends to ring 3 via `iretq`. The ring-3 program is a tiny hand-encoded,
//! position-independent stub (raw bytes — no relocations) that makes a few
//! `syscall`s to prove the full user → kernel → user traversal, then spins.
//!
//! It is exercised once at the end of boot so all Month-1..3 markers (which the
//! boot path prints earlier) remain the deterministic CI contract; Month 4 adds
//! `LIONOS_USER_*` + `LIONOS_SYSCALL_*` on top.

use crate::gdt;
use crate::paging;
use crate::syscall;

/// The ring-3 program is now a real user ELF embedded into the kernel (built by
/// `build.rs` from the `user/` crate and loaded via `crate::elf`, replacing the
/// former hand-encoded byte stub).

/// Bring up the first ring-3 process. Returns `false` (boot continues, e.g. the
/// scheduler idle loop) if the CPU has no `syscall`/`sysret` or no free low
/// region; otherwise descends to ring 3 and never returns.
///
/// # Safety
/// Boot-time, single CPU. Runs after interrupts, heap, framing, and the
/// scheduler markers are all on the wire. Allocates a syscall kernel stack,
/// overwrites the TSS RSP0, maps user pages, and `iretq`s to ring 3.
#[cfg(target_os = "none")]
pub unsafe fn bring_up() -> bool {
    if !syscall::cpu_has_syscall() {
        crate::serial::write_str("LIONOS_SYSCALL_UNSUPPORTED\r\n");
        return false;
    }

    let offset = paging::phys_offset();

    // 1. Load the embedded user program — a real non-PIE ELF (the `user`
    //    crate), replacing the old hand-encoded byte stub. Parse its PT_LOAD
    //    segments + entry, then map them into the ring-3 address space.
    let elf_bytes: &[u8] = include_bytes!(env!("USER_ELF"));
    // Pick a fresh, user-owned ring-3 region (so its tables are U/S at every
    // level). A fixed base can collide with a supervisor PML4 entry and fault
    // e=0x15 on the first user fetch, so the loader offsets the ELF's relative
    // VAs by this runtime `base`.
    let base_idx = paging::find_free_top_index(offset).expect("no free user region");
    if base_idx >= 256 {
        crate::serial::write_str("LIONOS_USER_NO_LOW_REGION\r\n");
        return false;
    }
    let base = (base_idx as u64) << 39;
    let entry_off = crate::elf::entry_point(elf_bytes).expect("user ELF entry");
    let entry_va = base + entry_off;
    let mut segs = alloc::vec::Vec::new();
    crate::elf::load_segments(elf_bytes, &mut segs);
    if segs.is_empty() {
        crate::serial::write_str("LIONOS_ELF_NO_SEGMENTS\r\n");
        return false;
    }
    let mut max_end: u64 = 0;
    for s in &segs {
        let pages = (s.memsz + 4095) / 4096;
        for i in 0..pages {
            let vaddr = base + s.vaddr + (i as u64) * 4096;
            let f = crate::frames::allocate_frame().expect("user seg frame") * 4096;
            // SAFETY: `vaddr` is in the fresh user region, page-aligned.
            let r = if s.writable() {
                crate::paging::map_user_data(offset, vaddr, f)
            } else {
                crate::paging::map_user_page(offset, vaddr, f)
            };
            r.expect("map user PT_LOAD");
            // Copy this page's share of the segment's file bytes into the page.
            let file_start = s.file_off + i * 4096;
            let n = s.filesz.saturating_sub(i * 4096).min(4096);
            if n > 0 {
                // SAFETY: `vaddr` is now mapped user-writable; src..+n is in the
                // embedded ELF slice.
                let src = elf_bytes.as_ptr().add(file_start);
                core::ptr::copy_nonoverlapping(src, vaddr as *mut u8, n);
            }
        }
        max_end = max_end.max(s.vaddr + s.memsz as u64);
    }
    // 2. A dedicated user NX stack just above the program image.
    let user_stack_page = base + ((max_end + 0xFFF) & !0xFFF);
    let stack_f = crate::frames::allocate_frame().expect("user stack frame") * 4096;
    crate::paging::map_user_data(offset, user_stack_page, stack_f).expect("map user stack");
    let user_stack_top = user_stack_page + 0x1000;
    // Record the user program's VA range so the syscall handler bounds-checks
    // `copy_from_user` (SYS_PUTS) against it.
    syscall::set_user_range(base, user_stack_top);

    // 3. A dedicated kernel stack for the syscall entry path (and ring-3 IRQs).
    let kstack = alloc::boxed::Box::<[u8; 8192]>::leak(alloc::boxed::Box::new([0u8; 8192]));
    let ktop = (kstack.as_ptr() as usize + 8192) as u64;
    // SAFETY: single-threaded ring-3 process; stack is set before descent.
    unsafe {
        syscall::SYSCALL_KSTACK = ktop;
        crate::gdt::set_rsp0(ktop);
    }

    // 4. Program the syscall MSRs; LSTAR points at `lion_syscall_entry`.
    let entry = syscall::syscall_entry_addr();
    // SAFETY: entry is a valid executable stub; CPU supports syscall.
    unsafe { syscall::enable(entry) };
    crate::serial::write_str("LIONOS_SYSCALL_MSR star=");
    crate::serial::write_hex(syscall::star_value());
    crate::serial::write_str(" sfmask=");
    crate::serial::write_hex(syscall::sfmask_value());
    crate::serial::write_str(" lstar=");
    crate::serial::write_hex(entry);
    crate::serial::write_str("\r\n");

    // 4a. Security hardening: the user stack is mapped No-Execute (always), and
    //     SMEP is enabled when the CPU supports it. (SMAP is left 0 — enabling
    //     it would make the ring-0 SYS_PUTS copy_from_user fault until the copy
    //     is wrapped in stac/clac; that's the documented follow-up.) Writing a
    //     CR4 bit the CPU does not implement #GPs — QEMU's default CPU lacks
    //     SMEP/SMAP, which was the earlier boot stall — so gate on the flag.
    let feat = crate::ffi::cpuid(7, 0);
    let smep = ((feat[1] >> 7) & 1) == 1; // CPUID.7.0:EBX bit 7
    let cr4 = crate::ffi::read_cr4();
    if smep && cr4 & (1 << 20) == 0 {
        crate::ffi::write_cr4(cr4 | (1 << 20));
    }
    crate::serial::write_str("LIONOS_SEC_CAPS nx=1 smep=");
    crate::serial::write_dec(smep as u64);
    crate::serial::write_str(" smap=0\r\n");

    // 4b. Seed the IPC mailbox so the ring-3 shell has a message to `recv`
    //     (stands in for input arriving from another party).
    syscall::seed_mailbox(b"LiOS");

    // 5. Descend to ring 3 (iretq to a frame with RPL3 CS/SS, IF off).
    let user_cs = (gdt::USER_CODE as u64) | 3;
    let user_ss = (gdt::USER_DATA as u64) | 3;
    crate::serial::write_str("LIONOS_USER_DROP rip=");
    crate::serial::write_hex(entry_va);
    crate::serial::write_str(" cs=");
    crate::serial::write_hex(user_cs);
    crate::serial::write_str(" rsp=");
    crate::serial::write_hex(user_stack_top);
    crate::serial::write_str("\r\n");

    // SAFETY: `entry_va` is the mapped executable user code page; the stack is
    // the NX user page just above. Interrupts are OFF in ring 3.
    crate::ffi::cli();
    crate::ffi::usermode_go(entry_va, user_stack_top, user_cs, user_ss, 0x2);

    loop {} // type-unifying never path (long jumps to ring 3 actually)
}