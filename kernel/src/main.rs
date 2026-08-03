#![no_std]
#![no_main]

//! LionOS kernel stub — Month 1 / Week 1 placeholder.
//!
//! This is intentionally minimal: it initialises the COM1 serial port and
//! prints a single marker string, then halts. It exists to prove the whole
//! toolchain (nightly rustc, `x86_64-unknown-none`, bootloader crate, QEMU,
//! CI serial capture) end-to-end. Month 1 Week 3 replaces this stub with the
//! real bootloader -> kernel handoff (memory map, paging, long-mode entry).

use core::arch::asm;
use core::panic::PanicInfo;

mod serial;

/// Boot marker printed to COM1 on success. CI greps for this exact string.
///
/// Overridable at build time via the `LIONOS_BOOT_MARKER` env var so CI can
/// run a real negative test (boot with a wrong marker -> assert it is absent).
fn boot_marker() -> &'static str {
    option_env!("LIONOS_BOOT_MARKER").unwrap_or("LIONOS_INIT_OK")
}

/// Entry point called by the bootloader.
#[no_mangle]
pub extern "C" fn _start() -> ! {
    serial::init();
    serial::write_raw(boot_marker().as_bytes());
    serial::write_byte(b'\r');
    serial::write_byte(b'\n');
    // Boot success. Park the CPU (the real kernel brings up interrupts later).
    loop {
        // SAFETY: hlt is always safe; interrupts are disabled at this point.
        unsafe { asm!("hlt", options(nomem, nostack, preserves_flags)) }
    }
}

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    serial::init();
    serial::write_raw(b"PANIC\r\n");
    loop {
        // SAFETY: hlt is always safe.
        unsafe { asm!("hlt", options(nomem, nostack, preserves_flags)) }
    }
}
