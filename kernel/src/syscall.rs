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
        for n in 0..6 {
            assert!(lookup(n).is_some(), "number {n} must be defined");
        }
        assert!(lookup(6).is_none());
        assert_eq!(name_of(SYS_EXIT), "exit");
        assert_eq!(name_of(0xFFFF), "unknown");
    }

    #[test]
    fn errnos_are_negative() {
        assert!(ERRNO_ENOSYS < 0 && ERRNO_EINVAL < 0);
    }
}
