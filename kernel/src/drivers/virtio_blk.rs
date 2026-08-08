//! virtio-blk PCI detect shim — Month 3, drivers (disk, modern standard).
//!
//! QEMU's `-drive file=…,if=virtio` exposes a virtio-blk device on the PCI bus
//! (vendor 0x1AF4). This module detects it and reports a `LIONOS_DRV_VIRTIO`
//! found/absent marker; [`AtaDisk`](crate::drivers::ide::AtaDisk) is the fully
//! wired PIO block transport backing [`crate::fs`] on QEMU.
//!
//! The virtio *virtqueue* data path (descriptor ring setup over the BAR0 MMIO
//! capability + the PCI config `vq` notify) is a follow-up — a real transport
//! needs MMIO mapping that's only safe once the page tables are fully owned
//! (Month 2 takeover) and is deliberately out of this task's boot-verified
//! scope. [`VirtioBlk::read_sector`] therefore reports *present-but-not-wired*;
//! the pure detection core is host-tested.

use crate::drivers::pci::{self, PciDevice};

/// Virtio PCI vendor id (all virtio-pci devices).
pub const VIRTIO_VENDOR: u16 = 0x1AF4;
/// Legacy virtio-blk device id (pre-1.0).
pub const VIRTIO_BLK_LEGACY: u16 = 0x1001;
/// Modern virtio-blk device id (virtio 1.0+).
pub const VIRTIO_BLK_MODERN: u16 = 0x1041;
/// PCI mass-storage base class.
const PCI_CLASS_STORAGE: u8 = 0x01;

/// Is this PCI (vendor, device, class) a virtio block device? Pure, host-tested.
pub fn is_virtio_blk(vendor: u16, device: u16, class: u8) -> bool {
    vendor == VIRTIO_VENDOR
        && (device == VIRTIO_BLK_LEGACY || device == VIRTIO_BLK_MODERN)
        && class == PCI_CLASS_STORAGE
}

/// A detected virtio-blk device. The PCI record is enough to gate the marker;
/// sector reads need the (deferred) virtqueue.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct VirtioBlk {
    pub pci: PciDevice,
}

impl VirtioBlk {
    /// Scan bus 0 for the first virtio block device.
    #[cfg(target_os = "none")]
    pub fn probe() -> Option<VirtioBlk> {
        pci::probe_bus0()
            .into_iter()
            .find(|d| is_virtio_blk(d.vendor, d.device, d.class))
            .map(|pci| VirtioBlk { pci })
    }
}

impl crate::fs::BlockDevice for VirtioBlk {
    /// No data path yet: the virtqueue ring isn't implemented (see module doc).
    /// ATA covers the real block read on QEMU this month.
    fn read_sector(&self, _lba: u32, _buf: &mut [u8; 512]) -> bool {
        false // ponytail: detect-only shim; add the BAR0 virtqueue transport when the FS needs a second disk
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_virtio_block_ids() {
        assert!(is_virtio_blk(VIRTIO_VENDOR, VIRTIO_BLK_LEGACY, PCI_CLASS_STORAGE));
        assert!(is_virtio_blk(VIRTIO_VENDOR, VIRTIO_BLK_MODERN, PCI_CLASS_STORAGE));
        // Same ids but wrong class (e.g. a virtio-net NIC) is not a block dev.
        assert!(!is_virtio_blk(VIRTIO_VENDOR, VIRTIO_BLK_LEGACY, 0x02));
        // Wrong vendor is not virtio.
        assert!(!is_virtio_blk(0x8086, VIRTIO_BLK_LEGACY, PCI_CLASS_STORAGE));
    }
}