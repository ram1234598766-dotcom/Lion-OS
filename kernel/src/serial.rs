//! Minimal COM1 (serial port 0x3F8) driver for the Week-1 placeholder.
//!
//! No `core::fmt`, no locking, no buffering — just enough to emit the CI boot
//! marker and a small fixed panic note over serial. A proper spinlock-protected
//! driver (with a `core::fmt::Write` impl) lands in Month 3; `core::fmt` output
//! itself is revisited there too (the Week-1 `writeln!` build triple-faults at
//! boot, tracked in `docs/ARCHITECTURE.md` §1 watch-notes).

use core::arch::asm;

const COM1: u16 = 0x3F8;

// SAFETY: the caller must ensure the port is valid and not used concurrently.
unsafe fn outb(port: u16, value: u8) {
    asm!("out dx, al", in("dx") port, in("al") value, options(nomem, nostack, preserves_flags));
}

// SAFETY: the caller must ensure the port is valid.
unsafe fn inb(port: u16) -> u8 {
    let value: u8;
    asm!("in al, dx", out("al") value, in("dx") port, options(nomem, nostack, preserves_flags));
    value
}

/// Initialise COM1 at 38400 baud, 8N1.
pub fn init() {
    // SAFETY: these are the standard 16550 UART init writes on COM1.
    unsafe {
        outb(COM1 + 1, 0x00); // disable interrupts
        outb(COM1 + 3, 0x80); // enable DLAB (set baud divisor)
        outb(COM1 + 0, 0x03); // divisor low byte  (38400 baud)
        outb(COM1 + 1, 0x00); // divisor high byte
        outb(COM1 + 3, 0x03); // 8N1, DLAB off
        outb(COM1 + 2, 0xC7); // enable + clear FIFO
        outb(COM1 + 4, 0x0B); // IRQs enabled, RTS/DSR set
    }
}

/// Write one byte, waiting until the transmit-holding register is empty.
pub fn write_byte(byte: u8) {
    // Wait until the transmit-holding register is empty (bit 5 of line status).
    // SAFETY: reading COM1+5 is always safe.
    while unsafe { inb(COM1 + 5) } & 0x20 == 0 {}
    // SAFETY: COM1 is a valid write target and we waited for room.
    unsafe { outb(COM1, byte) };
}

/// Write a byte slice raw.
pub fn write_raw(bytes: &[u8]) {
    for &byte in bytes {
        write_byte(byte);
    }
}

/// Write a `&str` raw.
pub fn write_str(s: &str) {
    write_raw(s.as_bytes());
}

const HEX: &[u8; 16] = b"0123456789abcdef";

/// Write `value` as fixed-width lowercase hex (no `0x` prefix).
///
/// Keep this on raw `outb`/`write_byte` rather than `core::fmt`: the Week-1
/// stub triple-faulted when it called `core::fmt` at boot (see
/// `docs/ARCHITECTURE.md` §1 watch-note); the raw port path is proven safe.
pub fn write_hex(value: u64) {
    for shift in (0..64).step_by(4).rev() {
        write_byte(HEX[((value >> shift) & 0xF) as usize]);
    }
}

/// Write `value` as decimal.
pub fn write_dec(value: u64) {
    if value == 0 {
        write_byte(b'0');
        return;
    }
    let mut buf = [0u8; 20];
    let mut n = value;
    let mut i = buf.len();
    while n > 0 {
        i -= 1;
        buf[i] = b'0' + (n % 10) as u8;
        n /= 10;
    }
    write_raw(&buf[i..]);
}
