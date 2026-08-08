//! UHCI USB host controller PCI detect shim — Month 3, drivers (USB, real standard).
//!
//! UHCI is Intel's USB 1.1 host controller (UHCI = USB Host Controller Interface).
//! It's exposed on the PCI bus as a serial-bus (0x0C) / USB (0x03) device with
//! vendor `0x8086` and device id `0x7020`. QEMU exposes one when the machine has
//! a USB bus (`-usb` with the default `piix3-uhci`).
//!
//! Mirroring `virtio_blk.rs`, this module is a PCI **detect** shim: it reports a
//! `LIONOS_DRV_UHCI` found/absent marker. The actual UHCI register port I/O
//! (SMI/bulk/control frames via the BAR registers) is deliberately out of scope —
//! UHCI's frame descriptors and transfer descriptors live in host memory and need
//! the phys-offset mapping owned in Month 2, so a live schedule is a follow-up.
//! The pure detection core is host-tested; the boot probe never faults.

use crate::drivers::pci::{self, PciDevice};

/// Intel PCI vendor id (UHCI controllers are always Intel).
pub const INTEL_VENDOR: u16 = 0x8086;
/// Intel UHCI USB host controller device id, device 0.
pub const UHCI_8086_0x7020: u16 = 0x7020;

/// Is this PCI (vendor, device) an Intel UHCI host controller? Pure, host-tested.
pub fn is_uhci(vendor: u16, device: u16) -> bool {
    vendor == 0x8086 && device == 0x7020
}

/// A detected UHCI host controller. Keeps the PCI record; the reagent register
/// set (BAR0 register map) is deferred along with the transfer-descriptor path.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Uhci {
    pub pci: PciDevice,
}

impl Uhci {
    /// Scan bus 0 for the first UHCI host controller.
    #[cfg(target_os = "none")]
    pub fn probe() -> Option<Uhci> {
        pci::probe_bus0()
            .into_iter()
            .find(|d| is_uhci(d.vendor, d.device))
            .map(|pci| Uhci { pci })
    }
}

/// Probe and print the `LIONOS_DRV_UHCI` found/absent boot marker — never faults.
#[cfg(target_os = "none")]
pub fn init() {
    match Uhci::probe() {
        Some(u) => {
            crate::serial::write_str("LIONOS_DRV_UHCI found=1 ");
            // UHCI is an I/O BAR: BAR0 decodes to a port. Read the
            // CMD register (0) and FRNUM register (8) as real 16-bit ports.
            let port: u16 = crate::drivers::pci::bar_addr(&u.pci, 0) as u16;
            let cmd: u16 = crate::drivers::mmio::inw(port);
            let frame: u16 = crate::drivers::mmio::inw(port + 8);
            crate::serial::write_str("cmd=");
            crate::serial::write_hex(u64::from(cmd));
            crate::serial::write_str(" frame=");
            crate::serial::write_hex(u64::from(frame));
        }
        None => crate::serial::write_str("LIONOS_DRV_UHCI ABSENT"),
    }
    crate::serial::write_str("\r\n");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_intel_uhci_ids() {
        assert!(is_uhci(0x8086, 0x7020));
        // Same vendor, different device (e.g. a different Intel part) is not UHCI.
        assert!(!is_uhci(0x8086, 0x7000));
        // Wrong vendor is not UHCI.
        assert!(!is_uhci(0x1AF4, 0x7020));
    }
}