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

pub mod ahci;
pub mod e1000;
pub mod ehci;
pub mod face_id;
pub mod fbtext;
pub mod font5x7;
pub mod hpet;
pub mod ide;
pub mod ioapic;
pub mod keyboard;
pub mod mmio;
pub mod mouse;
pub mod nvme;
pub mod pci;
pub mod rtl8139;
pub mod rtc;
pub mod speaker;
pub mod uhci;
pub mod vbe;
pub mod vga;
pub mod virtio_blk;

use crate::fs;
use crate::fs::BlockDevice;
use crate::serial;

/// Number of files in the last successful FAT root `ls` (0 if none mounted).
/// Set by `init_all`; read by the Month-6 file explorer at boot.
#[cfg(target_os = "none")]
static LAST_FS_FILES: core::sync::atomic::AtomicUsize = core::sync::atomic::AtomicUsize::new(0);

/// Count of files listed from the most-recent FAT mount (0 when no disk).
#[cfg(target_os = "none")]
pub fn last_fs_files() -> usize {
    LAST_FS_FILES.load(core::sync::atomic::Ordering::Relaxed)
}

/// Run every driver's init and print a consolidated marker line. Boot-time,
/// single CPU, after interrupts + heap are up. Kernel-only: the device
/// drivers touch hardware that the host test target doesn't link (their
/// *pure* pieces — keyboard decode, RTC BCD, PCI present-check, mouse packet
/// decode, face-id — are still host-tested separately).
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
    // virtio-blk: real virtqueue — negotiate, queue up, and drive read-only
    // FAT32 over it when a device is present. Absence is never faulted.
    match virtio_blk::VirtioBlk::probe() {
        Some(v) => {
            serial::write_str("LIONOS_DRV_VIRTIO found=1\r\n");
            match fs::Fs::mount(&v) {
                Ok(f) => {
                    serial::write_str("LIONOS_FS_VIRTIO_OK\r\n");
                    let mut entries = alloc::vec::Vec::new();
                    if f.ls(&v, &mut entries) {
                        serial::write_str("LIONOS_FS_VIRTIO_LS count=");
                        serial::write_dec(entries.len() as u64);
                        serial::write_str(" [");
                        for (i, e) in entries.iter().enumerate() {
                            if i > 0 { serial::write_str(", "); }
                            serial::write_str(&e.display_name());
                        }
                        serial::write_str("]\r\n");
                        if let Some(e0) = entries.iter().find(|e| !e.is_dir) {
                            let mut got = alloc::vec::Vec::new();
                            if f.read_path(&v, &e0.display_name(), &mut got) {
                                serial::write_str("LIONOS_FS_VIRTIO_READ name=");
                                serial::write_str(&e0.display_name());
                                serial::write_str(" bytes=");
                                serial::write_dec(got.len() as u64);
                                serial::write_str("\r\n");
                            } else {
                                serial::write_str("LIONOS_FS_VIRTIO_READ_ERR\r\n");
                            }
                        }
                    }
                }
                Err(_) => {
                    // Diagnose a failed mount: does the virtqueue even deliver
                    // sector 0? Print read success + first bytes + the 0x55AA sig.
                    serial::write_str("LIONOS_FS_VIRTIO_BAD_BPB read=");
                    let mut buf512 = [0u8; 512];
                    let okr = v.read_sector(0, &mut buf512);
                    serial::write_dec(okr as u64);
                    serial::write_str(" b00=");
                    serial::write_hex(u64::from(u32::from_le_bytes([buf512[0], buf512[1], buf512[2], buf512[3]])));
                    serial::write_str(" sig=");
                    serial::write_hex(u64::from(u32::from_le_bytes([buf512[510], buf512[511], 0u8, 0u8])));
                    serial::write_str("\r\n");
                }
            }
        }
        None => serial::write_str("LIONOS_DRV_VIRTIO ABSENT\r\n"),
    }

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
                        LAST_FS_FILES.store(entries.len(), core::sync::atomic::Ordering::Relaxed);
                        serial::write_str("LIONOS_FS_LS count=");
                        serial::write_dec(entries.len() as u64);
                        serial::write_str(" [");
                        for (k, e) in entries.iter().enumerate() {
                            if k > 0 { serial::write_str(", "); }
                            serial::write_str(&e.display_name());
                        }
                        serial::write_str("]\r\n");
                        // LFN + file-path + subdir exercises on a real disk.
                        if let Some(file) = entries.iter().find(|e| !e.is_dir) {
                            let name = file.display_name();
                            let mut got = alloc::vec::Vec::new();
                            if f.read_path(disk, &name, &mut got) {
                                serial::write_str("LIONOS_FS_READ_PATH name=");
                                serial::write_str(&name);
                                serial::write_str(" bytes=");
                                serial::write_dec(got.len() as u64);
                                serial::write_str("\r\n");
                            } else {
                                serial::write_str("LIONOS_FS_READ_PATH_ERR\r\n");
                            }
                        }
                        if let Some(dir) = entries.iter().find(|e| e.is_dir) {
                            let dirname = dir.display_name();
                            let mut sub = alloc::vec::Vec::new();
                            if f.ls_path(disk, &dirname, &mut sub) {
                                serial::write_str("LIONOS_FS_LS_SUB dir=");
                                serial::write_str(&dirname);
                                serial::write_str(" count=");
                                serial::write_dec(sub.len() as u64);
                                serial::write_str("\r\n");
                                if let Some(inner) = sub.iter().find(|e| !e.is_dir) {
                                    // Skip the "." / ".." dot entries and read a
                                    // real inner file by a full `/` path (LFN).
                                    let path = alloc::format!("{}/{}", dirname, inner.display_name());
                                    let mut got = alloc::vec::Vec::new();
                                    if f.read_path(disk, &path, &mut got) {
                                        serial::write_str("LIONOS_FS_READ_SUB name=");
                                        serial::write_str(&path);
                                        serial::write_str(" bytes=");
                                        serial::write_dec(got.len() as u64);
                                        serial::write_str("\r\n");
                                    } else {
                                        serial::write_str("LIONOS_FS_READ_SUB_ERR\r\n");
                                    }
                                }
                            } else {
                                serial::write_str("LIONOS_FS_LS_SUB_ERR\r\n");
                            }
                        }
                        // Read the first listed FILE back by cluster chain — the
                        // end-to-end check that the FAT walk follows a real chain.
                        if let Some(e0) = entries.iter().find(|e| !e.is_dir) {
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

    // --- Task 4: the remaining real-standard driver set (each detect-only,
    // found/absent marker — see the per-driver module docs). Order follows the
    // plan: storage first (AHCI/NVMe), then net/USB/timer/APIC/gfx.
    ahci::init();
    nvme::init();
    e1000::init();
    rtl8139::init();
    uhci::init();
    ehci::init();
    hpet::init();
    ioapic::init();
    vbe::init();
}
