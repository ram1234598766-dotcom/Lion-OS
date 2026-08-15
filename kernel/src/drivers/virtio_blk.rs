//! virtio-blk modern virtio-pci (1.0) driver with a real virtqueue — Month 3+.
//!
//! QEMU's `-drive file=…,if=virtio` exposes a virtio-blk-pci device (vendor
//! 0x1AF4, device 0x1041, PCI class mass-storage). This is NOT detect-only: it
//! parses the virtio-pci capability list (common/notify/device config),
//! negotiates `VIRTIO_F_VERSION_1`, sets up a split virtqueue over four physical
//! frames, then submits real `VIRTIO_BLK` read requests and polls the used ring.
//! It implements [`crate::fs::BlockDevice`], so read-only FAT32 can mount a
//! virtio disk.
//!
//! MMIO goes through the physical-memory window (`mmio::*`). The rings + request
//! buffers live in physical frames the device addresses by their physical page,
//! reached from the kernel through the same window. Single-flight (one request
//! in) at boot, so a bare `avail.idx` / `used.idx` cursor suffices.

use core::cell::Cell;

use crate::drivers::mmio;
use crate::drivers::pci::{self, PciDevice};
use crate::frames;
use crate::paging;

/// Virtio PCI vendor id.
pub const VIRTIO_VENDOR: u16 = 0x1AF4;
/// Modern virtio-blk device id; QEMU's transitional `virtio-blk-pci` presents it.
pub const VIRTIO_BLK_MODERN: u16 = 0x1041;
/// Legacy virtio-blk id — a transitional PCI device may advertise this instead.
pub const VIRTIO_BLK_LEGACY: u16 = 0x1001;
const PCI_CLASS_STORAGE: u8 = 0x01;

// --- virtio-pci capability (cap id 0x09) ---
const VIRTIO_CAP_ID: u8 = 0x09;
const CFG_COMMON: u8 = 0x01;
const CFG_NOTIFY: u8 = 0x02;
const CFG_DEVICE: u8 = 0x04;

// --- device status bits (common cfg `device_status`, u8 @20) ---
const STAT_ACKNOWLEDGE: u8 = 0x01;
const STAT_DRIVER: u8 = 0x02;
const STAT_FEATURES_OK: u8 = 0x08;
const STAT_DRIVER_OK: u8 = 0x04;

/// VIRTIO_F_VERSION_1 = bit index 32 -> the bit set in feature dword 1.
const FEATURE_VERSION_1: u32 = 0x0000_0001;

// --- `virtio_pci_common_cfg` byte offsets (virtio 1.0 spec) ---
const COMMON_GFSEL: u64 = 0x08; // driver_feature_select u32
const COMMON_GF: u64 = 0x0C;    // driver_feature u32
const COMMON_STATUS: u64 = 20;  // device_status u8
const COMMON_Q_SEL: u64 = 22;   // queue_select u16
const COMMON_Q_SIZE: u64 = 24;  // queue_size u16
const COMMON_Q_ENABLE: u64 = 28; // queue_enable u16
const COMMON_Q_NOFF: u64 = 30;  // queue_notify_off u16
const COMMON_Q_DESC: u64 = 32;  // queue_desc u64 (lo 32)
const COMMON_Q_DRIVER: u64 = 40; // queue_driver u64 (lo 32)
const COMMON_Q_DEVICE: u64 = 48; // queue_device u64 (lo 32)

// descriptor flags
const DESC_F_NEXT: u16 = 0x0001;
const DESC_F_WRITE: u16 = 0x0002;

/// Is this PCI (vendor, device, class) a modern virtio block device? Pure.
pub fn is_virtio_blk(vendor: u16, device: u16, class: u8) -> bool {
    vendor == VIRTIO_VENDOR
        && (device == VIRTIO_BLK_MODERN || device == VIRTIO_BLK_LEGACY)
        && class == PCI_CLASS_STORAGE
}

// ---------------------------------------------------------------------------
// Kernel-only: capability decode, negotiation, virtqueue.
// ---------------------------------------------------------------------------

#[cfg(target_os = "none")]
fn cfg8(d: &PciDevice, off: u8) -> u8 {
    let w = unsafe { pci::config_read(d.bus, d.slot, d.func, off & 0xFC) };
    ((w >> (8 * (off & 3))) & 0xFF) as u8
}

/// Byte-accumulated 32-bit config read (handles unaligned capability fields).
#[cfg(target_os = "none")]
fn cfg32(d: &PciDevice, off: u8) -> u32 {
    let mut v = 0u32;
    for i in 0..4 {
        v |= (cfg8(d, off + i) as u32) << (8 * i);
    }
    v
}

/// Parse the virtio-pci capabilities → (common, notify, notify_mult, device-cfg).
#[cfg(target_os = "none")]
fn caps(d: &PciDevice) -> Option<(u64, u64, u32, u64)> {
    let mut cp = cfg8(d, 0x34); // PCI capabilities pointer
    let mut c = (0u64, 0u64, 0u32, 0u64);
    while cp != 0 {
        if cfg8(d, cp) == VIRTIO_CAP_ID {
            let typ = cfg8(d, cp + 3);
            let bar = cfg8(d, cp + 4);
            let off = cfg32(d, cp + 8) as u64;
            let base = pci::bar_addr(d, bar);
            match typ {
                CFG_COMMON => c.0 = base + off,
                CFG_NOTIFY => { c.1 = base + off; c.2 = cfg32(d, cp + 16); }
                CFG_DEVICE => c.3 = base + off,
                _ => {}
            }
        }
        cp = cfg8(d, cp + 1); // next
    }
    (c.0 != 0).then(|| c)
}

/// Map a physical address through the physical-memory window (bootloader 0.11
/// does not identity-map device memory into the kernel).
#[cfg(target_os = "none")]
fn virt(phys: u64) -> u64 { phys + paging::phys_offset() }

/// A modern virtio-blk device with a live virtqueue.
#[cfg(target_os = "none")]
pub struct VirtioBlk {
    // The PCI record is kept for diagnostics/registers, but nothing reads it
    // yet — `_d` documents intent while staying warning-free.
    _d: PciDevice,
    common: u64,
    notify: u64,
    notify_mult: u32,
    qsz: u16,
    fr_desc: u64, fr_avail: u64, fr_used: u64, fr_buf: u64,
    // Break the single-flight avail/used cursors via `Cell` so `read_sector`
    // can stay `&self` (the BlockDevice trait signature).
    avail_head: Cell<u16>,
}

#[cfg(target_os = "none")]
impl VirtioBlk {
    fn rd8(&self, o: u64) -> u8 { mmio::read8(self.common + o) }
    fn rd16(&self, o: u64) -> u16 { mmio::read16(self.common + o) }
    fn wr8(&self, o: u64, v: u8) { mmio::write8(self.common + o, v) }
    fn wr16(&self, o: u64, v: u16) { mmio::write16(self.common + o, v) }
    fn wr(&self, o: u64, v: u32) { mmio::write32(self.common + o, v) }
    fn status(&self) -> u8 { self.rd8(COMMON_STATUS) }

    /// Find + bring up the device. Returns None if absent or init fails (never
    /// faults).
    pub fn probe() -> Option<VirtioBlk> {
        let d = pci::probe_bus0().into_iter().find(|d| is_virtio_blk(d.vendor, d.device, d.class))?;
        let (common, notify, mult, _devcfg) = caps(&d)?;
        let mut v = VirtioBlk {
            _d: d, common, notify, notify_mult: mult,
            qsz: 0, fr_desc: 0, fr_avail: 0, fr_used: 0, fr_buf: 0,
            avail_head: Cell::new(0),
        };
        if !v.reset_and_negotiate() {
            crate::serial::write_str("LIONOS_DRV_VIRTIO_BLK negfail\r\n");
            return None;
        }
        if !v.setup_queue() {
            crate::serial::write_str("LIONOS_DRV_VIRTIO_BLK qfail\r\n");
            return None;
        }
        Some(v)
    }

    fn reset_and_negotiate(&mut self) -> bool {
        self.wr8(COMMON_STATUS, 0); // reset
        self.wr8(COMMON_STATUS, STAT_ACKNOWLEDGE | STAT_DRIVER);
        self.wr(COMMON_GFSEL, 0);
        self.wr(COMMON_GF, 0);
        self.wr(COMMON_GFSEL, 1);
        self.wr(COMMON_GF, FEATURE_VERSION_1); // bit 32 = VERSION_1
        self.wr(COMMON_GFSEL, 0);
        self.wr8(COMMON_STATUS, STAT_ACKNOWLEDGE | STAT_DRIVER | STAT_FEATURES_OK);
        self.status() & STAT_FEATURES_OK != 0
    }

    fn setup_queue(&mut self) -> bool {
        self.wr16(COMMON_Q_SEL, 0);
        self.qsz = self.rd16(COMMON_Q_SIZE);
        if self.qsz == 0 || self.qsz > 256 { return false; }
        let (d, a, u, b) = match alloc_frames() {
            Some(x) => x,
            None => return false,
        };
        // physical addresses are < 4 GiB, so write low 32-bit, high = 0.
        self.wr(COMMON_Q_DESC, d as u32);
        self.wr(COMMON_Q_DESC + 4, 0);
        self.wr(COMMON_Q_DRIVER, a as u32);
        self.wr(COMMON_Q_DRIVER + 4, 0);
        self.wr(COMMON_Q_DEVICE, u as u32);
        self.wr(COMMON_Q_DEVICE + 4, 0);
        self.wr16(COMMON_Q_ENABLE, 1);
        self.fr_desc = d; self.fr_avail = a; self.fr_used = u; self.fr_buf = b;
        self.wr8(COMMON_STATUS, self.status() | STAT_DRIVER_OK);
        true
    }

    fn notify(&self) {
        let n = self.rd16(COMMON_Q_NOFF) as u32;
        let phys = self.notify + (n * self.notify_mult) as u64;
        // SAFETY: notify register is a u16 store of the queue index (0).
        unsafe { core::ptr::write_volatile(virt(phys) as *mut u16, 0u16) };
    }

    /// Submit one READ of `lba` into `out`; poll used ring; check the status byte.
    fn xfer(&self, lba: u32, out: &mut [u8; 512]) -> bool {
        let b = self.fr_buf;
        // Request frame (phys b): header(16) | data(512) | status(1).
        // SAFETY: b is a writable frame we own; type=0 (READ), sector=lba.
        unsafe {
            let h = virt(b) as *mut u8;
            core::ptr::write_volatile(h as *mut u32, 0);
            core::ptr::write_volatile((h as *mut u32).add(1), 0);
            core::ptr::write_volatile((h as *mut u64).add(1), lba as u64);
            core::ptr::write_volatile(virt(b + 1024) as *mut u8, 0); // status
        }
        // SAFETY: fr_desc / fr_avail are writable frames we own.
        unsafe {
            let vd = virt(self.fr_desc) as *mut u8;
            write_des(vd, 0, b, 16, DESC_F_NEXT, 1);
            write_des(vd, 1, b + 512, 512, DESC_F_WRITE | DESC_F_NEXT, 2);
            write_des(vd, 2, b + 1024, 1, DESC_F_WRITE, 0);

            let va = virt(self.fr_avail) as *mut u16;
            let head = self.avail_head.get();
            let slot = (head % self.qsz) as usize;
            core::ptr::write_volatile(va.add(1), head.wrapping_add(1)); // avail.idx = one more placed
            core::ptr::write_volatile(va.add(2 + slot), 0);           // ring[slot] = desc 0
            self.avail_head.set(head.wrapping_add(1));
        }
        // Remember the used position before the request runs, then poke the device.
        let vu = unsafe { (virt(self.fr_used) as *mut u16).add(1) };
        let done = unsafe { core::ptr::read_volatile(vu) };
        self.notify();

        for _ in 0..40_000_000 {
            // SAFETY: fr_used is a mapped frame we own; used.idx at byte +2.
            let used = unsafe { core::ptr::read_volatile(vu) };
            if used != done {
                // A completion arrived (single-flight → our request).
                // SAFETY: copy the device-writable payload out.
                unsafe { core::ptr::copy_nonoverlapping(virt(b + 512) as *const u8, out.as_mut_ptr(), 512); }
                let ok = unsafe { core::ptr::read_volatile(virt(b + 1024) as *const u8) } == 0;
                return ok;
            }
            crate::ffi::pause();
        }
        false
    }
}

#[cfg(target_os = "none")]
impl crate::fs::BlockDevice for VirtioBlk {
    fn read_sector(&self, lba: u32, buf: &mut [u8; 512]) -> bool {
        self.xfer(lba, buf)
    }
}

/// Write the 16-byte descriptor `n` into the descriptor frame at `d`.
#[cfg(target_os = "none")]
unsafe fn write_des(d: *mut u8, n: usize, addr: u64, len: u32, flags: u16, next: u16) {
    unsafe {
        let e = d.add(n * 16);
        core::ptr::write_volatile(e as *mut u64, addr);
        core::ptr::write_volatile((e as *mut u32).add(2), len);
        core::ptr::write_volatile((e as *mut u16).add(6), flags);
        core::ptr::write_volatile((e as *mut u16).add(7), next);
    }
}

/// Allocate four physical frames for rings + data; return their phys addresses.
#[cfg(target_os = "none")]
fn alloc_frames() -> Option<(u64, u64, u64, u64)> {
    let mut o = [0u64; 4];
    for s in o.iter_mut() {
        *s = frames::allocate_frame().map(|f| f * 4096)?;
    }
    Some((o[0], o[1], o[2], o[3]))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_virtio_block_ids() {
        assert!(is_virtio_blk(VIRTIO_VENDOR, VIRTIO_BLK_MODERN, PCI_CLASS_STORAGE));
        assert!(is_virtio_blk(VIRTIO_VENDOR, VIRTIO_BLK_LEGACY, PCI_CLASS_STORAGE));
        assert!(!is_virtio_blk(VIRTIO_VENDOR, VIRTIO_BLK_MODERN, 0x02));
        assert!(!is_virtio_blk(0x8086, VIRTIO_BLK_MODERN, PCI_CLASS_STORAGE));
    }

    #[test]
    fn version_one_is_bit_32() {
        assert_eq!(FEATURE_VERSION_1, 1);
    }
}