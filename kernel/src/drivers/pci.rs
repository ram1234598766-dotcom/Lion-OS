//! PCI bus enumeration (config space) — Month 3, drivers (extra).
//!
//! Probes bus 0 (which virtually all QEMU machines populate) via the legacy
//! config mechanism (0xCF8/0xCFC), listing each present device's vendor, device
//! ID, and class. This is real device discovery — QEMU exposes a PCI bus by
//! default — and a foundation for driver-to-device binding later (IDE/virtio).
//!
//! The port-I/O probe is kernel-target only; the data model + a pure helper are
//! host-testable.

use core::arch::asm;

const CONFIG_ADDR: u16 = 0xCF8;
const CONFIG_DATA: u16 = 0xCFC;

/// A single PCI device discovered on bus 0.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PciDevice {
    pub bus: u8,
    pub slot: u8,
    pub func: u8,
    pub vendor: u16,
    pub device: u16,
    pub class: u8,
    pub subclass: u8,
}

/// True if a config vendor/device dword indicates "no device here".
pub fn is_present(vd: u32) -> bool {
    let vendor = (vd & 0xFFFF) as u16;
    vendor != 0xFFFF && vendor != 0x0000
}

/// Read a 32-bit config dword for `(bus, slot, func)` at `offset` (0..=252, /4).
///
/// # Safety
/// Port I/O; CONFIG_ADDR/DATA are the standard x86 PCI mechanism #1 registers.
#[cfg(target_os = "none")]
pub unsafe fn config_read(bus: u8, slot: u8, func: u8, offset: u8) -> u32 {
    let addr = 0x8000_0000u32
        | ((bus as u32) << 16)
        | ((slot as u32) << 11)
        | ((func as u32) << 8)
        | (offset as u32 & 0xFC);
    // SAFETY: write addr then read data — standard PCI mechanism #1.
    unsafe { outl(CONFIG_ADDR, addr) };
    unsafe { inl(CONFIG_DATA) }
}

/// Enumerate bus 0 for present devices.
#[cfg(target_os = "none")]
pub fn probe_bus0() -> alloc::vec::Vec<PciDevice> {
    let mut found = alloc::vec::Vec::new();
    for slot in 0..32u8 {
        // Function 0 vendor/device; if absent, no device on this slot.
        // SAFETY: config reads on valid (bus,slot,func) are safe.
        let vd = unsafe { config_read(0, slot, 0, 0x00) };
        if !is_present(vd) {
            continue;
        }
        let vendor = (vd & 0xFFFF) as u16;
        let device = (vd >> 16) as u16;
        // If function 0 is a multi-function device, scan funcs 1..7.
        // SAFETY: header-type register at 0x0C, multi-function bit 7 of byte 3.
        let multi = unsafe { config_read(0, slot, 0, 0x0C) } >> 16 & 0x80 != 0;
        let mut funcs_found = 0u8;
        if multi {
            for func in 1..8u8 {
                // SAFETY: probing other functions is safe (missing -> all-ones).
                let fvd = unsafe { config_read(0, slot, func, 0x00) };
                if is_present(fvd) {
                    // SAFETY: class/subclass in 0x08.
                    let reg = unsafe { config_read(0, slot, func, 0x08) };
                    found.push(PciDevice {
                        bus: 0, slot, func,
                        vendor: (fvd & 0xFFFF) as u16,
                        device: (fvd >> 16) as u16,
                        class: (reg >> 24) as u8,
                        subclass: (reg >> 16) as u8,
                    });
                    funcs_found += 1;
                }
            }
        }
        if funcs_found == 0 {
            // Single-function device at func 0.
            // SAFETY: class/subclass in 0x08.
            let reg = unsafe { config_read(0, slot, 0, 0x08) };
            found.push(PciDevice {
                bus: 0, slot, func: 0, vendor, device,
                class: (reg >> 24) as u8,
                subclass: (reg >> 16) as u8,
            });
        }
    }
    found
}

// ---- 32-bit port I/O (the asm layer only has byte-wide inb/outb) ----

/// Write 32 bits to an I/O port.
///
/// # Safety
/// `port` must be a valid 32-bit I/O port.
#[cfg(target_os = "none")]
unsafe fn outl(port: u16, val: u32) {
    // SAFETY: caller guarantees a valid port.
    unsafe { asm!("out dx, eax", in("dx") port, in("eax") val, options(nomem, nostack)) };
}

/// Read 32 bits from an I/O port.
///
/// # Safety
/// `port` must be a valid 32-bit I/O port.
#[cfg(target_os = "none")]
unsafe fn inl(port: u16) -> u32 {
    // SAFETY: caller guarantees a valid port.
    let v: u32;
    unsafe { asm!("in eax, dx", out("eax") v, in("dx") port, options(nomem, nostack)) };
    v
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn present_check() {
        assert!(is_present(0x1234_8086)); // vendor 0x8086 (Intel)
        assert!(!is_present(0xFFFF_FFFF)); // no device
        assert!(!is_present(0x0000_0000)); // invalid
    }
}
