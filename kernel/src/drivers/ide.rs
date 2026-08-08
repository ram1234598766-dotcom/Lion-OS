//! ATA-1 legacy PIO block driver — Month 3, drivers (disk, real standard).
//!
//! Classic 40-pin ATA on the primary (`0x1F0`) / secondary (`0x170`) I/O base.
//! The plan's host-first rule means the pure geometry (`lba28_capacity`,
//! `drive_reg`) is host-tested, and the port-I/O identify + sector read live
//! behind `#[cfg(target_os = "none")]`, exactly like `rtc.rs`.
//!
//! This is the read-only block transport that backs [`crate::fs`] when a real
//! (QEMU `-device`/`-drive if=ide`) disk is attached. Absent a drive, [`probe`]
//! returns `None` and the boot marker reports `LIONOS_DRV_IDE ABSENT` (never a
//! fault — see `drivers/mod.rs`).

use crate::ffi;
use crate::fs::BlockDevice;

/// I/O base for the primary ATA channel (master drive).
pub const ATA_PRIMARY: u16 = 0x1F0;
/// I/O base for the secondary ATA channel.
pub const ATA_SECONDARY: u16 = 0x170;

// Register offsets from the channel base (ATA PIO register map).
const REG_DATA: u16 = 0;    // 16-bit data port
const REG_DRIVE: u16 = 6;   // drive/head select
const REG_STAT: u16 = 7;    // status (and command on write)
const REG_SECCNT: u16 = 2;  // sector count
const REG_LBA_LO: u16 = 3;
const REG_LBA_MID: u16 = 4;
const REG_LBA_HI: u16 = 5;

const STATUS_BSY: u8 = 0x80; // drive busy
const STATUS_DRQ: u8 = 0x08; // data request ready
const STATUS_ERR: u8 = 0x01; // error (also ERR bit)

/// A detected, drive at `base`. Holds the ATA ID capacity so the pure parts are
/// host-testable and the driver's state is just a couple of registers.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AtaDisk {
    /// Channel I/O base (`0x1F0` / `0x170`).
    pub base: u16,
    /// Sector capacity from IDENTIFY words 61:60 (LB A-28).
    pub lba28_capacity: u32,
}

/// The ATA IDENTIFY LBA-28 capacity lives in words 60 (low) + 61 (high).
pub fn lba28_capacity(words_60_hi: [u16; 2]) -> u32 {
    ((words_60_hi[1] as u32) << 16) | words_60_hi[0] as u32
}

/// The DRIVE/HEAD register to select a master with the LBA bit + the high bits
/// of a 28-bit LBA (bits 27..24 fit the low nibble; register high nibble `0xE0`
/// is "select master, enable LBA").
pub fn drive_reg(lba: u32) -> u8 {
    0xE0 | ((lba >> 24) as u8 & 0x0F)
}

// ---------------------------------------------------------------------------
// Kernel-only port-I/O (blocks aren't present on the host test target).
// ---------------------------------------------------------------------------

/// Wait (bounded) for the drive to clear BSY. False on timeout.
#[cfg(target_os = "none")]
fn wait_bs(base: u16) -> bool {
    for _ in 0..20_000 {
        // SAFETY: reading the ATA status register is always safe.
        if unsafe { ffi::inb(base + REG_STAT) } & STATUS_BSY == 0 {
            return true;
        }
        ffi::nasm_io_wait();
    }
    false
}

/// Issue `IDENTIFY` on the master and read the 256-word (512-byte) payload.
/// Returns `None` if no ATA device answers (that's a clean "absent").
#[cfg(target_os = "none")]
fn identify(base: u16) -> Option<[u8; 512]> {
    // SAFETY: standard ATA IDENTIFY write sequence on a valid channel base.
    unsafe { ffi::outb(base + REG_DRIVE, 0xA0) }; // select master (CHS+nop)
    if !wait_bs(base) { return None; }
    unsafe { ffi::outb(base + REG_SECCNT, 0) };
    unsafe { ffi::outb(base + REG_LBA_LO, 0) };
    unsafe { ffi::outb(base + REG_LBA_MID, 0) };
    unsafe { ffi::outb(base + REG_LBA_HI, 0) };
    unsafe { ffi::outb(base + REG_STAT, 0xEC) }; // ATA IDENTIFY
    if !wait_bs(base) { return None; }
    let st = unsafe { ffi::inb(base + REG_STAT) };
    if st & STATUS_ERR != 0 { return None; } // no ATA drive / not present
    if st & STATUS_DRQ == 0 { return None; }

    let mut out = [0u8; 512];
    for chunk in out.chunks_exact_mut(2) {
        // SAFETY: drive asserted DRQ, so it will supply the full IDENT payload.
        let w = unsafe { ffi::nasm_inw(base + REG_DATA) };
        chunk[0] = (w & 0xff) as u8;
        chunk[1] = (w >> 8) as u8;
    }
    Some(out)
}

/// Build an `AtaDisk` from an IDENTIFY payload, or `None` if not ATA.
#[cfg(target_os = "none")]
fn from_identify(base: u16, id: &[u8; 512]) -> AtaDisk {
    let lo = u16::from_le_bytes([id[120], id[121]]); // word 60
    let hi = u16::from_le_bytes([id[122], id[123]]); // word 61
    AtaDisk { base, lba28_capacity: lba28_capacity([lo, hi]) }
}

/// Probe both channels (master only) for every ATA drive present. A real PC may
/// expose the boot disk on the primary channel and a FAT volume on the
/// secondary, so `drivers/mod.rs` mounts the first drive whose boot sector
/// parses as FAT32 rather than assuming a single disk.
#[cfg(target_os = "none")]
pub fn probe_all() -> alloc::vec::Vec<AtaDisk> {
    let mut out = alloc::vec::Vec::new();
    for base in [ATA_PRIMARY, ATA_SECONDARY] {
        if let Some(id) = identify(base) {
            out.push(from_identify(base, &id));
        }
    }
    out
}

/// Probe both channels and return the first drive found.
#[cfg(target_os = "none")]
pub fn probe() -> Option<AtaDisk> {
    probe_all().into_iter().next()
}

/// Drive the parity of `identify`: same selection logic, but sector reads.
#[cfg(target_os = "none")]
impl BlockDevice for AtaDisk {
    fn read_sector(&self, lba: u32, buf: &mut [u8; 512]) -> bool {
        if lba >= self.lba28_capacity as u32 {
            // Out-of-range: the capacity word may be 0 on some drives; never
            // rearrange the caller's buffer on a failed read.
            return false;
        }
        if !wait_bs(self.base) { return false; }
        // SAFETY: LBA-28 sector read sequence (READ SECTOR(S), count 1).
        unsafe {
            ffi::outb(self.base + REG_DRIVE, drive_reg(lba));
            ffi::outb(self.base + REG_SECCNT, 1);
            ffi::outb(self.base + REG_LBA_LO, (lba & 0xff) as u8);
            ffi::outb(self.base + REG_LBA_MID, ((lba >> 8) & 0xff) as u8);
            ffi::outb(self.base + REG_LBA_HI, ((lba >> 16) & 0xff) as u8);
            ffi::outb(self.base + REG_STAT, 0x20); // READ SECTOR
        }
        if !wait_bs(self.base) { return false; }
        if unsafe { ffi::inb(self.base + REG_STAT) } & (STATUS_ERR) != 0 {
            return false;
        }
        for chunk in buf.chunks_exact_mut(2) {
            // SAFETY: DRQ set; the drive will stream 256 words.
            let w = unsafe { ffi::nasm_inw(self.base + REG_DATA) };
            chunk[0] = (w & 0xff) as u8;
            chunk[1] = (w >> 8) as u8;
        }
        // SAFETY: post-read status to catch the error flag.
        if unsafe { ffi::inb(self.base + REG_STAT) } & STATUS_ERR != 0 {
            return false;
        }
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lba28_capacity_from_identify_words() {
        // word 60 = 0x1234, word 61 = 0x0000 => 0x1234 sectors.
        assert_eq!(lba28_capacity([0x1234, 0x0000]), 0x1234);
        assert_eq!(lba28_capacity([0x0000, 0x0001]), 0x0001_0000);
    }

    #[test]
    fn drive_reg_selects_master_with_lba() {
        assert_eq!(drive_reg(0), 0xE0);
        assert_eq!(drive_reg((15 << 24) | 5), 0xEF); // high bits 0xF | 0xE0
    }
}