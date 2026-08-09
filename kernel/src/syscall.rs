//! Syscall ABI — Month 4, userland.
//!
//! The ring-3 → ring-0 path uses `syscall`/`sysret` (not `int`): the kernel
//! programs `STAR`/`LSTAR`/`SFMASK` (see `docs/SYSCALLS.md`), and a user
//! process calls `syscall` with the number in `rax`. This module owns the
//! number table (pure, host-tested) and the MSR encodings; the actual entry
//! stub + dispatch live on the kernel target (Task 3 of Month 4).
//!
//! Calling convention (summary — full ABI in docs/SYSCALLS.md):
//!   rax = syscall number; rdi/rsi/rdx/r10 = args 0..3;
//!   return in rax (negative = errno). `rcx`/`r11` are clobbered by the
//!   hardware and cannot carry arguments.

use crate::gdt;

// ------------------------------ numbers -------------------------------------

/// `exit(code)` — never returns.
pub const SYS_EXIT: u64 = 0;
/// `putc(char)` — write one byte to the console.
pub const SYS_PUTC: u64 = 1;
/// `puts(ptr, len)` — write `len` bytes from a user buffer.
pub const SYS_PUTS: u64 = 2;
/// `getc()` — read one byte (or `EAGAIN`).
pub const SYS_GETC: u64 = 3;
/// `ledget(hz)` — PIT rate placeholder (IPC routing later).
pub const SYS_LEDGET: u64 = 4;
/// `sleep(ms)` — park until the PIT advances.
pub const SYS_SLEEP: u64 = 5;
/// `recv()` — read (drain) the kernel IPC mailbox (ring-3 shell).
pub const SYS_RECV: u64 = 6;
/// `send()` — write the kernel IPC mailbox (ring-3 shell).
pub const SYS_SEND: u64 = 7;

/// System-call error values (negative, stable).
pub const ERRNO_ENOSYS: i64 = -38; // unknown syscall number
pub const ERRNO_EINVAL: i64 = -22;
pub const ERRNO_EACCES: i64 = -13;
pub const ERRNO_EFAULT: i64 = -14;

/// Resolve a syscall number to its mnemonic, if it is defined.
pub fn lookup(n: u64) -> Option<&'static str> {
    match n {
        SYS_EXIT => Some("exit"),
        SYS_PUTC => Some("putc"),
        SYS_PUTS => Some("puts"),
        SYS_GETC => Some("getc"),
        SYS_LEDGET => Some("ledget"),
        SYS_SLEEP => Some("sleep"),
        SYS_RECV => Some("recv"),
        SYS_SEND => Some("send"),
        _ => None,
    }
}

/// Name of a syscall number ("unknown" for undefined numbers).
pub fn name_of(n: u64) -> &'static str {
    lookup(n).unwrap_or("unknown")
}

// ------------------------------- MSRs ---------------------------------------

/// IA32_STAR — syscall/sysret selector base.
pub const MSR_STAR: u32 = 0xC000_0081;
/// IA32_LSTAR — kernel RIP of the syscall entry stub.
pub const MSR_LSTAR: u32 = 0xC000_0082;
/// IA32_SFMASK — RFLAGS bits cleared on syscall entry.
pub const MSR_SFMASK: u32 = 0xC000_0084;

/// STAR value: [47:32] = kernel CS (0x08), [63:48] = user CS base (0x28).
/// On `syscall` the CPU loads CS=STAR[47:32] (SS=+8) at RPL0; on `sysretq` it
/// loads CS=STAR[63:48]|3 (SS=+8) at RPL3 — so the user code/data pair is
/// exactly the two descriptors we installed in the writable GDT.
pub const fn star_value() -> u64 {
    ((gdt::USER_CODE as u64) << 48) | ((gdt::KERNEL_CODE as u64) << 32)
}

/// SFMASK value: clear IF (bit 9) on entry so a user-set interrupt flag can't
/// mask kernel interrupts mid-handler. (Debug/TF masking can be added later.)
pub const fn sfmask_value() -> u64 {
    1 << 9
}

// ------------------------- kernel-target helpers ----------------------------

/// Whether this CPU has the `syscall`/`sysret` instructions (CPUID extended
/// leaf 1, EDX bit 11). The ring-3 fast path is gated on this.
#[cfg(target_os = "none")]
pub fn cpu_has_syscall() -> bool {
    let r = crate::ffi::cpuid(0x8000_0001, 0);
    (r[3] & (1 << 11)) != 0 // EDX
}

/// Program STAR/LSTAR/SFMASK for the fast syscall path. `lstar` is the virtual
/// address of the `syscall` entry stub. Call once, ring 0, interrupts disabled.
///
/// # Safety
/// `lstar` must be the address of a valid, executable kernel entry stub; the
/// CPU supports `syscall` (see [`cpu_has_syscall`]).
#[cfg(target_os = "none")]
pub unsafe fn enable(lstar: u64) {
    crate::ffi::write_msr(MSR_STAR, star_value());
    crate::ffi::write_msr(MSR_LSTAR, lstar);
    crate::ffi::write_msr(MSR_SFMASK, sfmask_value());
    // The `syscall` instruction itself is gated on EFER.SCE (bit 0) — without
    // it, ring-3 `syscall` raises #UD. Turn it on.
    let efer = crate::ffi::read_msr(0xC000_0080);
    crate::ffi::write_msr(0xC000_0080, efer | 1);
}

//------------------------------------------------------------------------------
// Kernel-entry machinery (the asm stub in asm/cpu.s calls into these).
//------------------------------------------------------------------------------

// The LSTAR entry stub — `lion_syscall_entry` in `kernel/asm/cpu.s`.
#[cfg(target_os = "none")]
extern "C" {
    fn lion_syscall_entry();
}

/// A dedicated kernel stack for the syscall entry path (`syscall` does NOT
/// switch stacks). The asm stub reads this value and `mov`s RSP to it. Zero
/// initializer → lives in writable `.bss`, not the read-only `.data` mapping.
#[cfg(target_os = "none")]
#[no_mangle]
pub static mut SYSCALL_KSTACK: u64 = 0;

/// Virtual address of the syscall entry stub, for `LSTAR`.
#[cfg(target_os = "none")]
pub fn syscall_entry_addr() -> u64 {
    lion_syscall_entry as *const () as usize as u64
}

/// Count of syscalls serviced this boot (single ring-3 program, so a `static`).
#[cfg(target_os = "none")]
static mut SYSCALLS: u64 = 0;

/// The IPC mailbox (see `ipc.rs`), read/written by the ring-3 shell through
/// `SYS_RECV`/`SYS_SEND`. Zero-size initializer → `.bss`, writable.
#[cfg(target_os = "none")]
static mut MAILBOX: crate::ipc::Mailbox = crate::ipc::Mailbox::new();

/// Seed the IPC mailbox with a message before the ring-3 shell starts (a
/// stand-in for "input arriving from another party"). The shell then
/// `recv`s it.
#[cfg(target_os = "none")]
pub fn seed_mailbox(line: &[u8]) {
    let held = unsafe { &mut *core::ptr::addr_of_mut!(MAILBOX) };
    held.send(line);
}

/// The loaded user program's VA range (set by `user::bring_up` after loading),
/// so `copy_from_user` is bounds-checked against it.
#[cfg(target_os = "none")]
static mut USER_VA_START: u64 = 0;
#[cfg(target_os = "none")]
static mut USER_VA_END: u64 = 0;

/// Record the loaded user program's [start, end) VA range for `copy_from_user`.
#[cfg(target_os = "none")]
pub fn set_user_range(start: u64, end: u64) {
    unsafe {
        USER_VA_START = start;
        USER_VA_END = end;
    }
}

/// Whether CR4.SMAP is enabled (set by `bring_up`), so `copy_from_user` can
/// wrap its copy in `stac`/`clac` (the SMAP window).
#[cfg(target_os = "none")]
static SMAP_ENABLED: core::sync::atomic::AtomicBool = core::sync::atomic::AtomicBool::new(false);

/// Record whether SMAP is active (called by `user::bring_up` after the CPUID
/// gate).
#[cfg(target_os = "none")]
pub fn set_smap(enabled: bool) {
    SMAP_ENABLED.store(enabled, core::sync::atomic::Ordering::Relaxed);
}

/// Bounds-checked copy of `n` bytes from the user VA `src` into `dst`. Returns
/// `false` if `[src, src+n)` falls outside the loaded user program's range (the
/// classic `copy_from_user` check). Only the ring-3 caller can reach this.
#[cfg(target_os = "none")]
fn user_copy_in(dst: &mut [u8], src: u64, n: usize) -> bool {
    let (s, e) = unsafe { (USER_VA_START, USER_VA_END) };
    if s == 0 || src < s {
        return false;
    }
    let want_end = src.saturating_add(n as u64);
    if want_end > e {
        return false;
    }
    let smap = SMAP_ENABLED.load(core::sync::atomic::Ordering::Relaxed);
    // With SMAP on, ring-0 reads of user pages fault unless AC is set — so open
    // the window (stac) around the copy, then close it (clac). Without SMAP,
    // stac/clac are skipped (they'd #UD).
    if smap {
        crate::ffi::stac();
    }
    // SAFETY: `src..+n` is within the user pages we mapped.
    unsafe { core::ptr::copy_nonoverlapping(src as *const u8, dst.as_mut_ptr(), n) };
    if smap {
        crate::ffi::clac();
    }
    true
}

/// The syscall dispatcher, called by the asm stub with the C calling convention:
/// `(num, a0, a1, a2, a3, user_rsp)`. Runs in ring 0 on the syscall kernel
/// stack. Emits deterministic `LIONOS_*` markers so CI can prove the ring-3 →
/// ring-0 → ring-3 round trip.
#[cfg(target_os = "none")]
#[no_mangle]
pub extern "C" fn syscall_dispatch(
    num: u64,
    a0: u64,
    a1: u64,
    _a2: u64,
    _a3: u64,
    user_rsp: u64,
) -> i64 {
    unsafe { SYSCALLS += 1 };
    match num {
        SYS_PUTS => {
            // User→kernel data passing (closes copy_from_user): copy `a1` bytes
            // from the user buffer at `a0`, bounds-checked to the loaded user
            // program's VA range (the ELF the loader built). Emits them on serial.
            let n = a1.min(64) as usize;
            let mut buf = [0u8; 64];
            let ok = user_copy_in(&mut buf[..n], a0, n);
            crate::serial::write_str("LIONOS_SYS_PUTS ok=");
            crate::serial::write_dec(ok as u64);
            crate::serial::write_str(" str=\"");
            for &b in &buf[..n] {
                crate::serial::write_byte(b);
            }
            crate::serial::write_str("\"\r\n");
            0
        }
        // The user-constructed program passes its own CS in `a0` — proving it
        // really is at ring 3 (CS selector has RPL3).
        SYS_GETC => {
            crate::serial::write_str("LIONOS_USER_CS=");
            crate::serial::write_hex(a0);
            crate::serial::write_str(" rstk=");
            crate::serial::write_hex(user_rsp);
            crate::serial::write_str("\r\n");
            0
        }
        SYS_RECV => {
                // Ring-3 shell "reads" the IPC mailbox: drain it and report the
                // carried bytes (proves the message passed through the kernel).
                let held = unsafe { &mut *core::ptr::addr_of_mut!(MAILBOX) };
                let mut tmp = [0u8; 8];
                let n = held.drain(&mut tmp);
                // Fold the first up-to-8 bytes into a sentinel for the marker.
                let head = tmp.iter().fold(0u64, |acc, &b| (acc << 8) | u64::from(b));
                crate::serial::write_str("LIONOS_SHELL_READ n=");
                crate::serial::write_dec(n as u64);
                crate::serial::write_str(" head=");
                crate::serial::write_hex(head);
                crate::serial::write_str("\r\n");
                0
            }
            SYS_SEND => {
                // The shell "writes" an acknowledgement into the mailbox.
                let ok = b"ok!";
                let held = unsafe { &mut *core::ptr::addr_of_mut!(MAILBOX) };
                let n = held.send(ok);
                crate::serial::write_str("LIONOS_SHELL_WROTE n=");
                crate::serial::write_dec(n as u64);
                crate::serial::write_str("\r\n");
                0
            }
            SYS_PUTC | SYS_SLEEP | SYS_LEDGET => 0,
        SYS_EXIT => {
            // All syscalls this round-trip have been serviced; prove the full
            // user→kernel→user traversal occurred (each is a `syscall`+`sysretq`).
            crate::serial::write_str("LIONOS_USER_CALLS=");
            crate::serial::write_dec(unsafe { SYSCALLS });
            crate::serial::write_str("\r\n");
            0
        }
        _ => ERRNO_ENOSYS as i64,
    }
}

// ------------------------------- tests --------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn star_encodes_kernel_and_user_code() {
        let v = star_value();
        assert_eq!((v >> 32) & 0xFFFF, gdt::KERNEL_CODE as u64);
        assert_eq!((v >> 48) & 0xFFFF, gdt::USER_CODE as u64);
    }

    #[test]
    fn star_user_pair_is_contiguous() {
        // user data must be exactly +8 from user code so sysret's implicit SS
        // (SYSRET_CS + 8) lands on USER_DATA.
        assert_eq!(gdt::USER_DATA, gdt::USER_CODE + 8);
    }

    #[test]
    fn sfmask_clears_if() {
        assert_eq!(sfmask_value() & (1 << 9), 1 << 9);
    }

    #[test]
    fn lookup_round_trips_all_numbers() {
        for n in 0..8 {
            assert!(lookup(n).is_some(), "number {n} must be defined");
        }
        assert!(lookup(8).is_none());
        assert_eq!(name_of(SYS_EXIT), "exit");
        assert_eq!(name_of(SYS_RECV), "recv");
        assert_eq!(name_of(0xFFFF), "unknown");
    }

    #[test]
    fn errnos_are_negative() {
        assert!(ERRNO_ENOSYS < 0 && ERRNO_EINVAL < 0);
    }
}
