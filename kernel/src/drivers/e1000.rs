//! Intel e1000/8254x NIC detect shim — Month 3, drivers (network, extra).
//!
//! QEMU's default NIC is an Intel 82540EM, exposed on the PCI bus as vendor
//! 0x8086 device 0x100E. This module detects it and reports a `LIONOS_DRV_E1000`
//! found/absent marker, exactly like the virtio-blk detect shim.
//!
//! The transmit ring / register data path (BAR I/O + descriptor tables over the
//! bus-mastered MMIO registers) is a follow-up — wiring real NIC DMA is out of
//! this boot-verified scope. So this is *detect-only*; the pure matching core is
//! host-tested and the PCI probe never faults (absent → clean marker).

use crate::drivers::pci::{self, PciDevice};

/// Intel's PCI vendor id (all e100 + 8254X-family NICs).
pub const INTEL_VENDOR: u16 = 0x8086;
/// The QEMU-default 82540EM device id.
pub const E1000_ID: u16 = 0x100E;

/// Is this PCI (vendor, device) an Intel e100/8254X NIC? Pure, host-tested.
pub fn is_e1000(vendor: u16, device: u16) -> bool {
    vendor == 0x8086 && device == 0x100E
}

/// The e1000 NIC is detect-only; there's no data path yet (see module doc).
/// A detector via the pure match, so the config record gates the marker.
pub struct E1000 {
    pub pci: PciDevice,
}

impl E1000 {
    /// Scan bus 0 for the first e1000 NIC.
    #[cfg(target_os = "none")]
    pub fn probe() -> Option<E1000> {
        pci::probe_bus0()
            .into_iter()
            .find(|d| is_e1000(d.vendor, d.device))
            .map(|pci| E1000 { pci })
    }
}

/// Probe for the NIC and print its one boot marker — never faults, even with no
/// PCI bus or no NIC configured. Kernel-only (probe touches the PCI config bus).
#[cfg(target_os = "none")]
pub fn init() {
    match E1000::probe() {
        Some(n) => {
            crate::serial::write_str("LIONOS_DRV_E1000 found=1 pci=");
            crate::serial::write_hex(u64::from((n.pci.vendor as u32) << 16 | n.pci.device as u32));
            crate::serial::write_str(" slot=");
            crate::serial::write_dec(n.pci.slot as u64);
        }
        None => crate::serial::write_str("LIONOS_DRV_E1000 ABSENT"),
    }
    crate::serial::write_str("\r\n");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_emulated_nic() {
        assert!(is_e1000(INTEL_VENDOR, E1000_ID));
        // Wrong vendor is not Intel.
        assert!(!is_e1000(0x1AF4, E1000_ID));
        // The sibling 8255X dev is not the emulated 0x100E (other NICs exist).
        assert!(!is_e1000(INTEL_VENDOR, 0x1000));
    }
}