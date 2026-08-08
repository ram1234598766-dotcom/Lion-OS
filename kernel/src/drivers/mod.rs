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
pub mod ide;
pub mod keyboard;
pub mod mouse;
pub mod pci;
pub mod rtc;
pub mod speaker;
pub mod vga;
pub mod virtio_blk;

use crate::fs;
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

    // --- disk layer: ATA PIO + virtio-blk detect + read-only FAT32 ---
    // ATA is the real PIO block transport this month; virtio is detect-only
    // until the virtqueue ring lands. Absence is reported, never faulted.
    let virtio = virtio_blk::VirtioBlk::probe();
    match &virtio {
        Some(v) => {
            serial::write_str("LIONOS_DRV_VIRTIO found pci=");
            serial::write_hex(u64::from((v.pci.vendor as u32) << 16 | v.pci.device as u32));
        }
        None => serial::write_str("LIONOS_DRV_VIRTIO ABSENT"),
    }
    serial::write_str("\r\n");

    let disks = ide::probe_all();
    if disks.is_empty() {
        serial::write_str("LIONOS_DRV_IDE ABSENT\r\n");
    } else {
        serial::write_str("LIONOS_DRV_IDE disks=");
        serial::write_dec(disks.len() as u64);
        serial::write_str("\r\n");
        // Mount the first drive whose boot sector parses as FAT32.
        let mut fs_ok = false;
        for (i, disk) in disks.iter().enumerate() {
            match fs::Fs::mount(disk) {
                Ok(f) => {
                    serial::write_str("LIONOS_FS_OK disk=");
                    serial::write_dec(i as u64);
                    serial::write_str("\r\n");
                    let mut entries = alloc::vec::Vec::new();
                    if f.ls(disk, &mut entries) {
                        serial::write_str("LIONOS_FS_LS count=");
                        serial::write_dec(entries.len() as u64);
                        serial::write_str(" [");
                        for (k, e) in entries.iter().enumerate() {
                            if k > 0 { serial::write_str(", "); }
                            serial::write_str(&e.display_name());
                        }
                        serial::write_str("]\r\n");
                        // Read the first listed file back — the end-to-end check
                        // that the FAT walk follows a real cluster chain.
                        if let Some(e0) = entries.first() {
                            let mut data = alloc::vec::Vec::new();
                            if f.read(disk, e0.cluster, e0.size, &mut data) {
                                serial::write_str("LIONOS_FS_READ name=");
                                serial::write_str(&e0.display_name());
                                serial::write_str(" bytes=");
                                serial::write_dec(data.len() as u64);
                                // Deterministic content check: first 4 bytes as
                                // LE hex, so CI can assert byte-identity.
                                let mut head = 0u32;
                                for (i, b) in data.iter().take(4).enumerate() {
                                    head |= (*b as u32) << (8 * i);
                                }
                                serial::write_str(" head=");
                                serial::write_hex(u64::from(head));
                                serial::write_str("\r\n");
                            } else {
                                serial::write_str("LIONOS_FS_READ_ERR\r\n");
                            }
                        }
                    } else {
                        serial::write_str("LIONOS_FS_LS_ERR\r\n");
                    }
                    fs_ok = true;
                    break;
                }
                Err(_) => {
                    serial::write_str("LIONOS_FS_BAD_BPB\r\n");
                }
            }
        }
        if !fs_ok {
            serial::write_str("LIONOS_FS_NONE_MOUNTED\r\n");
        }
    }
}
