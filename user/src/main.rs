//! A tiny real user program, loaded by the kernel's ELF loader.
//!
//! It exercises the syscall ABI exactly like the old hand-encoded ring-3 stub:
//!   SYS_GETC (3) with its own CS (proves ring 3), SYS_PUTC ('A'),
//!   SYS_SLEEP (5), then the IPC mailbox SYS_RECV (6) / SYS_SEND (7), then
//!   SYS_EXIT (0). The dispatcher prints the same LIONOS_USER_CS /
//!   LIONOS_SHELL_READ / LIONOS_SHELL_WROTE / LIONOS_USER_CALLS=6 markers CI
//!   greps, so this is a drop-in replacement for the byte stub.
#![no_std]
#![no_main]

use core::arch::asm;
use core::panic::PanicInfo;

/// A `syscall` with `num` in rax and `a0` in rdi. rcx/r11 are clobbered.
#[inline(never)]
unsafe fn sc(num: u64, a0: u64) {
    asm!("syscall", in("rax") num, in("rdi") a0, out("rcx") _, out("r11") _,
         options(nostack));
}

#[inline(never)]
unsafe fn sc_n(num: u64) {
    asm!("syscall", in("rax") num, out("rcx") _, out("r11") _, options(nostack));
}

#[no_mangle]
pub extern "C" fn _start() -> ! {
    unsafe {
        // Read the user segment selector to prove we're at ring 3.
        let cs: u64;
        asm!("mov {0}, cs", out(reg) cs, options(nomem, nostack));

        sc(3, cs);           // SYS_GETC(cs)  -> LIONOS_USER_CS
        // SYS_PUTS: place "Hello!" on the ring-3 stack and pass its address+len,
        // proving user→kernel data copy (bounds-checked copy_from_user).
        asm!(
            "sub rsp, 8",
            "mov rax, 0x216f6c6c6548", // "Hello!" little-endian
            "mov [rsp], rax",
            "mov rdi, rsp",
            "mov rsi, 6",
            "mov rax, 2", // SYS_PUTS
            "syscall",
            "add rsp, 8",
        );
        sc(5, 4);            // SYS_SLEEP(4)
        sc_n(6);             // SYS_RECV      -> LIONOS_SHELL_READ
        sc_n(7);             // SYS_SEND      -> LIONOS_SHELL_WROTE
        sc_n(0);             // SYS_EXIT      -> LIONOS_USER_CALLS
    }
    loop {}
}

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {}
}