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

/// The ring-3 program, hand-assembled (64-bit, no relocations, no memory ops):
///   48 8c c8              mov rax, cs            ; prove we are ring3
///   48 89 c7              mov rdi, rax           ; CS -> arg0
///   48 c7 c0 03 00 00 00  mov rax, 3             ; SYS_GETC (echo CS)
///   0f 05                 syscall
///   48 c7 c0 01 00 00 00  mov rax, 1             ; SYS_PUTC
///   48 c7 c7 41 00 00 00  mov rdi, 65            ; 'A'
///   0f 05                 syscall
///   48 c7 c0 05 00 00 00  mov rax, 5             ; SYS_SLEEP
///   48 c7 c7 04 00 00 00  mov rdi, 4
///   0f 05                 syscall
///   48 c7 c0 00 00 00 00  mov rax, 0             ; SYS_EXIT
///   0f 05                 syscall
///   eb fe                 jmp $                  ; park in ring3
const USER_PROGRAM: &[u8] = &[
    0x48, 0x8c, 0xc8, // mov rax, cs
    0x48, 0x89, 0xc7, // mov rdi, rax
    0x48, 0xc7, 0xc0, 0x03, 0x00, 0x00, 0x00, // mov rax, SYS_GETC
    0x0f, 0x05, // syscall
    0x48, 0xc7, 0xc0, 0x01, 0x00, 0x00, 0x00, // mov rax, SYS_PUTC
    0x48, 0xc7, 0xc7, 0x41, 0x00, 0x00, 0x00, // mov rdi, 'A'
    0x0f, 0x05, // syscall
    0x48, 0xc7, 0xc0, 0x05, 0x00, 0x00, 0x00, // mov rax, SYS_SLEEP
    0x48, 0xc7, 0xc7, 0x04, 0x00, 0x00, 0x00, // mov rdi, 4
    0x0f, 0x05, // syscall
    0x48, 0xc7, 0xc0, 0x06, 0x00, 0x00, 0x00, // mov rax, SYS_RECV (shell reads mailbox)
    0x0f, 0x05, // syscall
    0x48, 0xc7, 0xc0, 0x07, 0x00, 0x00, 0x00, // mov rax, SYS_SEND (shell writes ack)
    0x0f, 0x05, // syscall
    0x48, 0xc7, 0xc0, 0x00, 0x00, 0x00, 0x00, // mov rax, SYS_EXIT
    0x0f, 0x05, // syscall
    0xeb, 0xfe, // jmp $
];

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

    // 1. A free region in the LOW (non-canonical) half — reachable from ring 3.
    let idx = paging::find_free_top_index(offset).expect("no free region for user");
    if idx >= 256 {
        crate::serial::write_str("LIONOS_USER_NO_LOW_REGION\r\n");
        return false;
    }
    let user_base = (idx as u64) << 39; // page-aligned low-half virtual
    let user_stack_top = user_base + 0x2000; // stack page at base + 0x1000

    // 2. Two user pages: code (with the stub) and a stack, both U/S + writable.
    let code_phys = crate::frames::allocate_frame().expect("user code frame") * 4096;
    let stack_phys = crate::frames::allocate_frame().expect("user stack frame") * 4096;
    // SAFETY: `user_base`/`user_base+0x1000` are page-aligned and unmapped.
    crate::paging::map_user_page(offset, user_base, code_phys).expect("map code");
    crate::paging::map_user_page(offset, user_base + 0x1000, stack_phys).expect("map stack");
    // Copy the program into the code page via the physical-memory window.
    // SAFETY: `code_phys + offset` is the mapped code frame; USER_PROGRAM fits.
    crate::ffi::memcpy(
        (code_phys + offset) as *mut u8,
        USER_PROGRAM.as_ptr(),
        USER_PROGRAM.len(),
    );

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

    // 4b. Seed the IPC mailbox so the ring-3 shell has a message to `recv`
    //     (stands in for input arriving from another party).
    syscall::seed_mailbox(b"LiOS");

    // 5. Descend to ring 3 (iretq to a frame with RPL3 CS/SS, IF off).
    let user_cs = (gdt::USER_CODE as u64) | 3;
    let user_ss = (gdt::USER_DATA as u64) | 3;
    crate::serial::write_str("LIONOS_USER_DROP rip=");
    crate::serial::write_hex(user_base);
    crate::serial::write_str(" cs=");
    crate::serial::write_hex(user_cs);
    crate::serial::write_str(" rsp=");
    crate::serial::write_hex(user_stack_top);
    crate::serial::write_str("\r\n");

    // SAFETY: `user_base` is an executable user (page-flags U/S) code page; the
    // stack lives in the second user page. Interrupts are OFF in ring 3.
    crate::ffi::cli();
    crate::ffi::usermode_go(user_base, user_stack_top, user_cs, user_ss, 0x2);

    loop {} // type-unifying never path (long jumps to ring 3 actually)
}