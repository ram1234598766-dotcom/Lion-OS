//! AHCI (SATA host controller) detect shim — Month 3, drivers (extras).
//!
//! QEMU exposes SATA controllers on the PCI bus as mass-storage class (0x01)
//! with subclass 0x06 (SATA / AHCI). This module detects one and reports a
//! `LIONOS_DRV_AHCI` found/absent marker.
//!
//! The AHCI *data path* (HBA BAR MMIO — the "HBA Memory" registers, 32-bit port
//! slots, command-list/command-table DMA descriptor rings) is a follow-up: it
//! needs MMIO mapping over the physical-memory offset window and DMA-privileged
//! frames that are only safe once the page tables are fully owned (Month 2
//! takeover) and is deliberately out of this task's boot-verified scope. This
//! module therefore reports *present-but-not-wired*; the pure detection core is
//! host-tested.

use crate::drivers::pci::{self, PciDevice};

/// PCI mass-storage base class (all disk controllers, incl. AHCI/SATA).
const PCI_CLASS_STORAGE: u8 = 0x01;
/// PCI mass-storage subclass for SATA / AHCI.
const PCI_SUBCLASS_SATA: u8 = 0x06;

/// Is this PCI (class, subclass) an AHCI (SATA) controller? Pure, host-tested.
pub fn is_ahci(class: u8, subclass: u8) -> bool {
    class == PCI_CLASS_STORAGE && subclass == PCI_SUBCLASS_SATA
}

/// A detected AHCI controller. The PCI record is enough to gate the marker;
/// the HBA register block needs the (deferred) MMIO mapping.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Ahci {
    pub pci: PciDevice,
}

impl Ahci {
    /// Scan bus 0 for the first AHCI/SATA controller.
    #[cfg(target_os = "none")]
    pub fn probe() -> Option<Ahci> {
        pci::probe_bus0()
            .into_iter()
            .find(|d| is_ahci(d.class, d.subclass))
            .map(|pci| Ahci { pci })
    }
}

#[cfg(target_os = "none")]
pub fn init() {
    match Ahci::probe() {
        Some(a) => {
            crate::serial::write_str("LIONOS_DRV_AHCI found=1 pci=");
            crate::serial::write_hex(u64::from((a.pci.vendor as u32) << 16 | a.pci.device as u32));
        }
        None => crate::serial::write_str("LIONOS_DRV_AHCI ABSENT"),
    }
    crate::serial::write_str("\r\n");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_ahci_class() {
        assert!(is_ahci(1, 6));
        assert!(!is_ahci(1, 8));
        // Same ids but wrong class is not AHCI.
        assert!(!is_ahci(0x02, 6));
    }
}