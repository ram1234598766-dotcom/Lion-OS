//! Realtek RTL8139 PCI Ethernet NIC detect — Month 3, drivers (extra).
//!
//! Detection-only shim, same shape as [`virtio_blk`](crate::drivers::virtio_blk):
//! QEMU exposes the RTL8139 as a PCI device (vendor 0x10EC, device 0x8139), so
//! this module scans bus 0 and reports a `LIONOS_DRV_RTL8139` found/absent
//! marker.
//!
//! The 8139's PIO register set (its 256-byte I/O block indexed off the BAR, the
//! transmit/receive descriptor rings, and the "Command" + "Config" regs) is
//! deliberately out of this task's boot-verified scope — a real NIC data path
//! needs an interrupt mailbox (Month 2 system) plus the driver owning the BAR,
//! both deferred. The pure detection core is host-tested.

use crate::drivers::pci::{self, PciDevice};

/// Realtek (first party) PCI vendor id.
pub const REALTEK_VENDOR: u16 = 0x10EC;
/// RTL8139 PCI device id.
pub const RTL8139_DEVICE: u16 = 0x8139;

/// Is this PCI (vendor, device) an RTL8139 NIC? Pure, host-tested.
pub fn is_rtl8139(vendor: u16, device: u16) -> bool {
    vendor == REALTEK_VENDOR && device == RTL8139_DEVICE
}

/// A detected RTL8139. The PCI record gates the boot marker; the PIO NIC data
/// path is deferred (see module doc).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Rtl8139 {
    pub pci: PciDevice,
}

impl Rtl8139 {
    /// Scan bus 0 for the first RTL8139 NIC. Kernel target (PCI port I/O).
    #[cfg(target_os = "none")]
    pub fn probe() -> Option<Rtl8139> {
        pci::probe_bus0()
            .into_iter()
            .find(|d| is_rtl8139(d.vendor, d.device))
            .map(|pci| Rtl8139 { pci })
    }
}

/// Boot-time detection hook: print `LIONOS_DRV_RTL8139 found=1 dev=… ` and a
/// newline when present, or `LIONOS_DRV_RTL8139 ABSENT` when not. Never faults.
#[cfg(target_os = "none")]
pub fn init() {
    let found = Rtl8139::probe();
    match found {
        Some(n) => {
            crate::serial::write_str("LIONOS_DRV_RTL8139 found=1 dev=");
            crate::serial::write_hex(u64::from(n.pci.vendor as u16) << 16 | u64::from(n.pci.device as u16));
        }
        None => crate::serial::write_str("LIONOS_DRV_RTL8139 ABSENT"),
    }
    crate::serial::write_str("\r\n");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_rtl8139_id() {
        assert!(is_rtl8139(REALTEK_VENDOR, RTL8139_DEVICE));
        // Wrong device id (same vendor) is not an RTL8139.
        assert!(!is_rtl8139(REALTEK_VENDOR, 0x8039));
        // Wrong vendor is not Realtek 8139.
        assert!(!is_rtl8139(0x8086, RTL8139_DEVICE));
    }
}