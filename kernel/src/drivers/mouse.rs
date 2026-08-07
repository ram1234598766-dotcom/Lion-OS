//! PS/2 mouse driver — Month 3, drivers (extra).
//!
//! Arms the second PS/2 port (the aux/mouse channel, IRQ12 = vector 0x2C) and
//! decodes the standard 3-byte mouse packets into deltas + button state. Pure
//! packet decoding is host-testable; the 8042 init + ISR are kernel-only.
//!
//! QEMU presents a PS/2 mouse by default, so `init` actually arms it; the boot
//! marker asserts the 8042 accepted the enable sequence.

use core::sync::atomic::{AtomicU8, AtomicI16, Ordering};
use crate::ffi;

const PS2_DATA: u16 = 0x60;
const PS2_CMD: u16 = 0x64;
/// IRQ12 is the PS/2 mouse vector.
pub const IRQ12: u8 = 0x2C;

// ---- decoded state (read by consumers, written by the ISR) ----
static MOUSE_DX: AtomicI16 = AtomicI16::new(0);
static MOUSE_DY: AtomicI16 = AtomicI16::new(0);
static MOUSE_BTNS: AtomicU8 = AtomicU8::new(0);
static PACKET_BUF: [AtomicU8; 3] = [AtomicU8::new(0), AtomicU8::new(0), AtomicU8::new(0)];
static PACKET_IDX: AtomicU8 = AtomicU8::new(0);

/// Net horizontal movement since last call (pixels/clicks).
pub fn dx() -> i16 {
    MOUSE_DX.swap(0, Ordering::Relaxed)
}

/// Net vertical movement since last call.
pub fn dy() -> i16 {
    MOUSE_DY.swap(0, Ordering::Relaxed)
}

/// Button state: bit0 left, bit1 right, bit2 middle.
pub fn buttons() -> u8 {
    MOUSE_BTNS.load(Ordering::Relaxed)
}

/// Feed the next raw byte from the 8042 data port into the packet decoder.
/// Called from the IRQ12 ISR (see `interrupts`).
pub fn handle_byte(raw: u8) {
    let idx = PACKET_IDX.load(Ordering::Relaxed) as usize;
    PACKET_BUF[idx].store(raw, Ordering::Relaxed);
    let next = (idx + 1) % 3;
    PACKET_IDX.store(next as u8, Ordering::Relaxed);
    if next == 0 {
        // A full 3-byte packet is assembled; decode it.
        let b0 = PACKET_BUF[0].load(Ordering::Relaxed);
        let b1 = PACKET_BUF[1].load(Ordering::Relaxed);
        let b2 = PACKET_BUF[2].load(Ordering::Relaxed);
        let (dx, dy, btns) = decode_packet(b0, b1, b2);
        MOUSE_DX.fetch_add(dx, Ordering::Relaxed);
        MOUSE_DY.fetch_add(dy, Ordering::Relaxed);
        MOUSE_BTNS.store(btns, Ordering::Relaxed);
    }
}

/// Decode a 3-byte PS/2 mouse packet into `(dx, dy, buttons)`. Pure, host-tested.
///
/// Byte 0: [Yovf Xovf Ysign Xsign 1 M R L]; byte 1: X delta; byte 2: Y delta
/// (Y is inverted: up is negative on the 8042).
pub fn decode_packet(b0: u8, b1: u8, b2: u8) -> (i16, i16, u8) {
    let x_sign = (b0 >> 4) & 1 != 0;
    let y_sign = (b0 >> 5) & 1 != 0;
    let mut dx = b1 as i16;
    let mut dy = b2 as i16;
    if x_sign {
        dx -= 256;
    }
    if y_sign {
        dy -= 256;
    }
    let btns = b0 & 0x07;
    // 8042 Y is signed with up-negative; we invert so up is positive for callers.
    (dx, -dy, btns)
}

// ---- 8042 init (kernel only) ----

/// Send a command byte to the 8042 controller port, waiting for input buffer
/// to clear.
///
/// # Safety
/// Port I/O on the 8042.
#[cfg(target_os = "none")]
unsafe fn wait_cmd_ready() {
    // Wait until the controller is ready to accept (input buffer empty: bit 1
    // of status port 0x64 == 0).
    while unsafe { ffi::inb(PS2_CMD) } & 0x02 != 0 {
        // spin
    }
}

/// Arm the PS/2 mouse: enable the aux channel + its IRQ, then tell the device
/// to stream packets (0xF4). Best-effort; a missing mouse leaves the channels
/// disabled but the driver is safe. Kernel target (port I/O).
#[cfg(target_os = "none")]
pub fn init() {
    // Enable aux (mouse) channel: send 0xA8 to the controller command port.
    // SAFETY: 8042 port I/O.
    unsafe {
        wait_cmd_ready();
        ffi::outb(PS2_CMD, 0xA8);
        wait_cmd_ready();
        // Read controller config byte.
        ffi::outb(PS2_CMD, 0x20);
        wait_cmd_ready();
        let cfg = ffi::inb(PS2_DATA);
        // Enable aux IRQ (bit 1) + translate (bit 6); keep the rest.
        let new_cfg = (cfg | 0x02) & !0x40;
        wait_cmd_ready();
        ffi::outb(PS2_CMD, 0x60);
        wait_cmd_ready();
        ffi::outb(PS2_DATA, new_cfg);
        // Tell the mouse to start streaming (0xF4) via the aux channel (0xD4).
        wait_cmd_ready();
        ffi::outb(PS2_CMD, 0xD4);
        wait_cmd_ready();
        ffi::outb(PS2_DATA, 0xF4);
    }
    // The ISR (vector 0x2C) is installed by interrupts::init.
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn packet_decode_zero_deltas() {
        // b0 = 0b00001001 (no signs, no buttons? bit0=1 means left pressed).
        let (dx, dy, btns) = decode_packet(0b0000_0001, 0, 0);
        assert_eq!((dx, dy), (0, 0));
        assert_eq!(btns, 0b001);
    }

    #[test]
    fn packet_decode_movement() {
        // Move +2 x, -3 y (8042 y negative = up), no buttons. Y sign bit (0x20)
        // is set so byte 2 is sign-extended: 0xFD = -3.
        let (dx, dy, btns) = decode_packet(0b0010_1000, 2, 0xFD);
        assert_eq!(dx, 2);
        assert_eq!(dy, 3); // inverted: -3 -> +3 (up)
        assert_eq!(btns, 0);
    }

    #[test]
    fn packet_decode_negative_x() {
        // X sign bit set, X byte = 0xFF -> -1.
        let (dx, _, _) = decode_packet(0b0001_0000, 0xFF, 0);
        assert_eq!(dx, -1);
    }
}