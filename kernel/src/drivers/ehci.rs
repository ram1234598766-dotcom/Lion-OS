//! USB EHCI host-controller driver — Month 3, drivers (extra).
//!
//! EHCI (`Enhanced Host Controller Interface`) is the PCI USB 2.0 host
//! controller. It shows up on the PCI bus as a standard serial-bus device:
//! class `0x0C`, subclass `0x03`. This module detects it via the existing PCI
//! bus-0 probe and reports a `LIONOS_DRV_EHCI` found/absent marker.
//!
//! Detection is PCI-config only; the QH/TD schedule from the EHCI MMIO register
//! block is a follow-up (needs the BAR0 MMIO base mapped through the physical-
//! memory window, like the deferred virtio virtqueue). The pure class/subclass
//! predicate is host-tested; the PCI scan is kernel-target only.

use crate::drivers::pci::{self, PciDevice};

/// PCI base class for all serial-bus controllers (USB).
pub const PCI_CLASS_SERIAL: u8 = 0x0C;
/// EHCI: the USB 2.0 host-controller subclass.
pub const PCI_SUBCLASS_EHCI: u8 = 0x03;

/// Is this PCI (class, subclass) an EHCI host controller? Pure, host-tested.
pub fn is_ehci(class: u8, subclass: u8) -> bool {
    class == 0x0C && subclass == 0x03
}

/// A detected EHCI host controller. The PCI record is enough to gate the
/// marker; the UHCI-style register schedule is deferred (see module doc).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Ehci {
    pub pci: PciDevice,
}

impl Ehci {
    /// Scan bus 0 for the first EHCI serial-bus controller.
    #[cfg(target_os = "none")]
    pub fn probe() -> Option<Ehci> {
        pci::probe_bus0()
            .into_iter()
            .find(|d| is_ehci(d.class, d.subclass))
            .map(|pci| Ehci { pci })
    }
}

/// Probe and print the boot marker for the EHCI controller. Report found (with
/// the PCI vendor/device id) or ABSENT — never a fault.
#[cfg(target_os = "none")]
pub fn init() {
    let ehci = Ehci::probe();
    match &ehci {
        Some(e) => {
            crate::serial::write_str("LIONOS_DRV_EHCI found=1 pci=");
            crate::serial::write_hex(u64::from((e.pci.vendor as u32) << 16 | e.pci.device as u32));
        }
        None => crate::serial::write_str("LIONOS_DRV_EHCI ABSENT"),
    }
    crate::serial::write_str("\r\n");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_ehci_subclass() {
        assert!(is_ehci(0x0C, 0x03));
    }
}