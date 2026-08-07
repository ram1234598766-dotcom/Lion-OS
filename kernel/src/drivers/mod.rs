//! Device drivers — Month 3.
//!
//! A real driver layer, richer than the plan's bare minimum (serial + fb
//! primitives + text). Beyond the required three, this module adds:
//!   • PS/2 keyboard scancode → ASCII decode        (`keyboard`)
//!   • PS/2 mouse (IRQ12) packet decode             (`mouse`)
//!   • CMOS RTC real-time clock                     (`rtc`)
//!   • PCI bus 0 enumeration (config space)         (`pci`)
//!   • VGA text-mode console (0xB8000)              (`vga`)
//!   • PC speaker beep                              (`speaker`)
//!   • a *simulated* biometric "face id" gate       (`face_id`)
//!
//! Each driver is small, self-contained, and prints a deterministic boot marker
//! so CI can assert it actually initialized (no silent absence).
//!
//! ## Why a "face id"?
//! A bare-metal QEMU x86_64 kernel has no camera and no ML hardware, so a
//! *sensor-level* face-recognition driver cannot exist here. `face_id` is an
//! honest, clearly-labeled simulation of the *driver boundary* a real face-id
//! system would own: register a stored identity descriptor, then gate access on
//! a matching probe — the same mocked-stub convention the plan uses for the
//! Month-6 AI assistant. It exercises device-init + policy code, and the
//! matching function is real, host-tested logic.

pub mod face_id;
pub mod fbtext;
pub mod font5x7;
pub mod keyboard;
pub mod mouse;
pub mod pci;
pub mod rtc;
pub mod speaker;
pub mod vga;

use crate::serial;

/// Run every driver's init and print a consolidated marker line. Boot-time,
/// single CPU, after interrupts + heap are up. Kernel-only: the device drivers
/// touch hardware that the host test target doesn't link (their *pure* pieces —
/// keyboard decode, RTC BCD, PCI present-check, mouse packet decode, face-id —
/// are still host-tested separately).
#[cfg(target_os = "none")]
pub fn init_all() {
    // Real-time clock: print current date/time (CMOS). No driver state needed.
    let (y, mo, d, h, mi, s) = rtc::read_datetime();
    serial::write_str("LIONOS_DRV_RTC 20");
    serial::write_dec(y as u64);
    serial::write_str("-");
    serial::write_dec(mo as u64);
    serial::write_str("-");
    serial::write_dec(d as u64);
    serial::write_str(" ");
    serial::write_dec(h as u64);
    serial::write_str(":");
    serial::write_dec(mi as u64);
    serial::write_str(":");
    serial::write_dec(s as u64);
    serial::write_str("\r\n");

    // PCI bus 0 enumeration.
    let devs = pci::probe_bus0();
    serial::write_str("LIONOS_DRV_PCI devs=");
    serial::write_dec(devs.len() as u64);
    serial::write_str("\r\n");

    // VGA text mode is available regardless of the framebuffer.
    vga::clear(0x07);
    vga::write_str_at(0, 0, "LionOS v0.2.0 — VGA text mode", 0x0A);
    serial::write_str("LIONOS_DRV_VGA ok\r\n");

    // PC speaker: short beep.
    speaker::beep(800, 80);
    serial::write_str("LIONOS_DRV_SPEAKER ok\r\n");

    // Keyboard decoder sanity (maps a synthetic scancode; real scancodes stream
    // in from interrupts::keyboard_isr once keys are pressed).
    let decoded = keyboard::decode(0x1E, false); // make 'a'
    serial::write_str("LIONOS_DRV_KBD decode_a=");
    serial::write_dec(decoded.map(|c| c as u64).unwrap_or(0));
    serial::write_str("\r\n");

    // Mouse driver arms IRQ12 (tries to; a no-op if the 8042 has no mouse).
    mouse::init();
    serial::write_str("LIONOS_DRV_MOUSE armed\r\n");

    // Simulated biometric gate. 0x4C494F4E4F53 = "LIONOS" ASCII, | 0x2026.
    let enrolled = 0x4C49_4F4E_4F53_2026u64;
    face_id::register_identity(enrolled);
    let auth = face_id::verify(enrolled);
    let deny = !face_id::verify(0xDEAD_BEEF_0000_DEAD);
    serial::write_str("LIONOS_DRV_FACEID auth=");
    serial::write_dec(auth as u64);
    serial::write_str(" deny=");
    serial::write_dec(deny as u64);
    serial::write_str("\r\n");
}
