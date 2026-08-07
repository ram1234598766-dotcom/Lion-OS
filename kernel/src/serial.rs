//! COM1 (serial port 0x3F8) driver — Month 3, formalized with a spinlock.
//!
//! Raw output primitives (`write_str`/`write_hex`/`write_dec`) plus a
//! `core::fmt::Write` impl (`Serial`) so `writeln!`/`write!` work.
//!
//! **Concurrency (W1D1):** the whole public write path is serialized by a
//! spinlock so output from two contexts (the deferred main loop and ISRs that
//! log) never interleaves. Internally the port writes go through the *unlocked*
//! helpers so `write_raw`/`write_hex`/`write_dec` acquire the lock once per
//! logical message, not once per byte.
//!
//! `core::fmt` output triple-faulted under the Week-1 0.9.35 bootloader; with
//! bootloader 0.11 it is re-verified in `main.rs` (`LIONOS_FMT_OK`).

use core::arch::asm;
use core::fmt;

use crate::spinlock::SpinLock;

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

/// Serialize serial output. Acquired once per logical write.
static LOCK: SpinLock<()> = SpinLock::new(());

/// Initialise COM1 at 38400 baud, 8N1. Boot-time, single CPU, pre-concurrency.
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
/// **Locked** — use [`write_byte_unlocked`] when the caller already holds the lock.
pub fn write_byte(byte: u8) {
    let _g = LOCK.lock();
    write_byte_unlocked(byte);
}

/// The lock-free core of [`write_byte`]. Caller must hold [`LOCK`].
fn write_byte_unlocked(byte: u8) {
    // Wait until the transmit-holding register is empty (bit 5 of line status).
    // SAFETY: reading COM1+5 is always safe.
    while unsafe { inb(COM1 + 5) } & 0x20 == 0 {}
    // SAFETY: COM1 is a valid write target and we waited for room.
    unsafe { outb(COM1, byte) };
}

/// Write a byte slice raw. **Locked once** for the whole slice.
pub fn write_raw(bytes: &[u8]) {
    let _g = LOCK.lock();
    for &byte in bytes {
        write_byte_unlocked(byte);
    }
}

/// Write a `&str` raw. **Locked once** for the whole string.
pub fn write_str(s: &str) {
    let _g = LOCK.lock();
    for &byte in s.as_bytes() {
        write_byte_unlocked(byte);
    }
}

/// A handle for `core::fmt` output. There is one serial port, so any `Serial`
/// value writes to COM1.
pub struct Serial;

/// Acquire a writer handle bound to COM1.
pub const fn serial() -> Serial {
    Serial
}

impl fmt::Write for Serial {
    fn write_str(&mut self, s: &str) -> fmt::Result {
        write_str(s);
        Ok(())
    }
}

const HEX: &[u8; 16] = b"0123456789abcdef";

/// Write `value` as fixed-width lowercase hex (no `0x` prefix). **Locked once.**
///
/// Kept on the raw write path (rather than `core::fmt`) so it can be called
/// before `fmt` output and on hot diagnostic paths; `core::fmt` (`writeln!` via
/// [`Serial`]) is available and re-verified at boot.
pub fn write_hex(value: u64) {
    let _g = LOCK.lock();
    for shift in (0..64).step_by(4).rev() {
        write_byte_unlocked(HEX[((value >> shift) & 0xF) as usize]);
    }
}

/// Write `value` as decimal. **Locked once.**
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
    let _g = LOCK.lock();
    for &byte in &buf[i..] {
        write_byte_unlocked(byte);
    }
}
