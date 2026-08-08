//! Read-only FAT filesystem — Month 3, kernel-core.
//!
//! Host-first (the master plan's rule: validate a parser on the host before it
//! touches a real disk). [`parse_boot`] validates a 512-byte FAT boot sector and
//! extracts the geometry (`FAT32` metadata); it is pure and fuzzable. The block
//! transport (virtio-blk / ATA) lives in `drivers/`, and `ls`/`read` glue the two.
//!
//! FAT32 geometry, per the MS spec:
//!   • BPB_BytsPerSec >= 512, power of two
//!   • BPB_SecPerClus a power of two
//!   • BPB_TotSec32 (or 16), BPB_RsvdSecCnt, BPB_FATSz32
//!   • root cluster = BPB_RootClus; data region starts after the FATs
//! We *validate* the structures here enough to derive sane geometry; the
//! on-disk walk (cluster chains, 32-bit FAT entries) is short-8.3-names-only
//! by design (plan: read-only FAT32, no LFN, no subdir reads).

use alloc::vec::Vec;

/// A directory entry's cluster is stored as two 16-bit words: the **high** word
/// at byte offset 20 and the **low** word at byte offset 26 (NOT a little-endian
/// u32 at byte 20). FAT32 entry values are masked to 28 bits; 0x0FFFFFF7 is a
/// bad cluster and 0x0FFFFFF8..0x0FFFFFFF end the chain.
pub const FAT32_LAST: u32 = 0x0FFF_FFFF;

/// Validated FAT metadata for a mounted volume.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FatInfo {
    pub bytes: u32,
    pub sectors_per_cluster: u8,
    pub reserved_sectors: u16,
    pub fat_count: u8,
    pub total_sectors: u32,
    pub sectors_per_fat: u32,
    pub root_cluster: u32,
    /// Sector where cluster 2 begins = reserved + (fat_count * spf).
    pub data_start: u32,
}

/// Why a boot sector was rejected.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FatError {
    /// Signature at offset 510 must be 0x55AA, or the read out of range.
    BadSignature,
    /// Bytes-per-sector not 512 (we only support 512).
    UnsupportedSectorSize,
    /// Sectors-per-cluster is zero or not a power of two.
    BadSectorsPerCluster,
    /// Reserved-sector count is zero.
    BadReserved,
    /// FAT count is zero.
    BadFatCount,
    /// No usable total-sector count (both fields zero).
    ZeroTotal,
    /// Sectors-per-FAT is zero (both the 16- and 32-bit fields).
    BadFatsParam,
    /// A boot sector that fixes a FAT16 root dir (root isn't a cluster ≥ 2).
    NotFat32,
}

/// Read a u16 at a byte offset (little-endian) from a 512-byte boot sector.
#[inline]
fn rd16(b: &[u8], off: usize) -> u16 {
    u16::from_le_bytes([b[off], b[off + 1]])
}

#[inline]
fn rd32(b: &[u8], off: usize) -> u32 {
    u32::from_le_bytes([b[off], b[off + 1], b[off + 2], b[off + 3]])
}

/// True when `c` is not a walkable data cluster: cluster 0/1 are reserved, and
/// values ≥ 0x0FFFFFF7 are the bad-cluster marker / end-of-chain sentinels.
pub fn is_chain_end(c: u32) -> bool {
    c < 2 || c >= 0x0FFF_FFF7
}

/// Parse + validate a FAT32 boot sector (512 bytes) into `FatInfo`.
pub fn parse_boot(b: &[u8]) -> Result<FatInfo, FatError> {
    if b.len() < 512 || b[510] != 0x55 || b[511] != 0xAA {
        return Err(FatError::BadSignature);
    }
    let bytes_per_sec = rd16(b, 11) as u32;
    if bytes_per_sec != 512 {
        return Err(FatError::UnsupportedSectorSize);
    }
    let sec_per_clus = b[13];
    if sec_per_clus == 0 || !sec_per_clus.is_power_of_two() {
        return Err(FatError::BadSectorsPerCluster);
    }
    let reserved = rd16(b, 14);
    if reserved == 0 { return Err(FatError::BadReserved); }
    let fat_count = b[16];
    if fat_count == 0 { return Err(FatError::BadFatCount); }

    let total16 = rd16(b, 19) as u32;
    let total32 = rd32(b, 32);
    let total = if total16 != 0 { total16 } else { total32 };
    if total == 0 { return Err(FatError::ZeroTotal); }

    let spf16 = rd16(b, 22) as u32;
    let spf32 = rd32(b, 36);
    let spf = if spf16 != 0 { spf16 } else { spf32 };
    if spf == 0 { return Err(FatError::BadFatsParam); }

    let root_cluster = rd32(b, 44);
    if root_cluster < 2 {
        // FAT16 roots hold a sector count, not a cluster; reject as not-FAT32.
        return Err(FatError::NotFat32);
    }

    let data_start = (reserved as u32)
        .checked_add(fat_count as u32 * spf)
        .ok_or(FatError::ZeroTotal)?;

    Ok(FatInfo {
        bytes: bytes_per_sec,
        sectors_per_cluster: sec_per_clus,
        reserved_sectors: reserved,
        fat_count,
        total_sectors: total,
        sectors_per_fat: spf,
        root_cluster,
        data_start,
    })
}

/// A read of one 512-byte sector by LBA. The kernel's block shim (virtio-blk /
/// ATA) implements this; the host tests back it with an in-memory image.
pub trait BlockDevice {
    /// Copy the 512-byte sector at `lba` into `buf`; false if out of range.
    fn read_sector(&self, lba: u32, buf: &mut [u8; 512]) -> bool;
}

/// A mounted FAT32 volume. Mounting reads only the boot sector; directory and
/// file reads pull on demand through the caller's [`BlockDevice`].
#[derive(Debug, Clone)]
pub struct Fs {
    pub info: FatInfo,
}

impl Fs {
    /// Read sector 0 and validate it as a FAT32 boot sector.
    pub fn mount(dev: &impl BlockDevice) -> Result<Fs, FatError> {
        let mut s = [0u8; 512];
        if !dev.read_sector(0, &mut s) {
            return Err(FatError::BadSignature); // "no drive at all
        }
        Ok(Fs { info: parse_boot(&s)? })
    }

    /// List the volume's root directory into `out` (short names only).
    pub fn ls(&self, dev: &impl BlockDevice, out: &mut Vec<DirEntry>) -> bool {
        list_dir(dev, &self.info, self.info.root_cluster, out)
    }

    /// Look up a directory entry by its exact 8.3 bytes (space-padded).
    pub fn find(&self, dev: &impl BlockDevice, name: &[u8; 11]) -> Option<DirEntry> {
        let mut all = Vec::new();
        self.ls(dev, &mut all);
        all.into_iter().find(|e| &e.name == name)
    }

    /// Read a whole file (given its first cluster + size) into `out`. Returns
    /// false if the chain breaks or a drive read fails.
    pub fn read(
        &self, dev: &impl BlockDevice, first_cluster: u32, size: u32, out: &mut Vec<u8>,
    ) -> bool {
        read_file(dev, &self.info, first_cluster, size, out)
    }
}

/// The FAT32 directory entry (8.3 name). LFN entries are skipped; subdirectories
/// are skipped (read-only scan, per plan).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct DirEntry {
    pub name: [u8; 11], // 8.3, space-padded
    pub cluster: u32,
    pub size: u32,
}

impl DirEntry {
    /// Render the 8.3 name as `"BASE.EXT"`, trimming padding, with the FAT
    /// "0x05 → 0xE5" leading-byte substitution applied.
    pub fn display_name(&self) -> alloc::string::String {
        let mut name = self.name;
        if name[0] == 0x05 { name[0] = 0xE5; }
        let base = &name[..8];
        let ext = &name[8..];
        let base = base.iter().take_while(|&&b| b != b' ').copied().collect::<alloc::vec::Vec<_>>();
        let ext = ext.iter().take_while(|&&b| b != b' ').copied().collect::<alloc::vec::Vec<_>>();
        let mut out = alloc::vec::Vec::with_capacity(12);
        out.extend_from_slice(&base);
        if !ext.is_empty() {
            out.push(b'.');
            out.extend_from_slice(&ext);
        }
        // Lazy-but-safe: 8.3 names are ASCII except the FAT 0x05/E5 lead char,
        // which renders as a replacement glyph until a codepage table lands.
        alloc::string::String::from_utf8_lossy(&out).into_owned()
    }
}

/// Read the 32-bit FAT entry for cluster `c`. FAT32: entry at byte `(c*4)` in
/// the FAT region (sector = `reserved_sectors + byte/512`).
fn read_fat_entry(dev: &impl BlockDevice, info: &FatInfo, c: u32) -> Option<u32> {
    let byte_off = c as u64 * 4;
    if byte_off / 512 >= info.sectors_per_fat as u64 {
        return None; // cluster's FAT entry lives outside the FAT → corrupt/short
    }
    let lba = info.reserved_sectors as u32 + (byte_off / 512) as u32;
    let in_sector = (byte_off % 512) as usize;
    let mut s = [0u8; 512];
    if !dev.read_sector(lba, &mut s) { return None; }
    let raw = s[in_sector] as u32
        | (s[in_sector + 1] as u32) << 8
        | (s[in_sector + 2] as u32) << 16
        | (s[in_sector + 3] as u32) << 24;
    Some(raw & FAT32_LAST)
}

/// A bounded walk that yields the short filenames in the directory located at
/// `start_cluster`. Pure; verified against a real mtools image (host-side).
pub fn list_dir(
    dev: &impl BlockDevice, info: &FatInfo, start_cluster: u32, out: &mut Vec<DirEntry>,
) -> bool {
    if is_chain_end(start_cluster) { return true; }
    let mut c = start_cluster;
    for _ in 0..1000 { // bound against an endless cluster chain
        if is_chain_end(c) { break; }
        // Directory's data sectors = cluster's mapping into the data region.
        let first_sector = info.data_start + (c - 2) * info.sectors_per_cluster as u32;
        for s in 0..info.sectors_per_cluster as u32 {
            let mut buf = [0u8; 512];
            if !dev.read_sector(first_sector + s, &mut buf) { return false; }
            for off in (0..512).step_by(32) {
                let name0 = buf[off];
                if name0 == 0 { return true; }   // end-of-directory
                if name0 == 0xE5 { continue; }   // deleted
                if buf[off + 11] & 0x0F == 0x0F { continue; } // LFN, skip
                if buf[off + 11] & 0x10 != 0 { continue; }    // subdir, skip
                let mut name = [b' '; 11];
                name.copy_from_slice(&buf[off..off + 11]);
                // FAT32: cluster = (hi word @ 20 << 16) | (lo word @ 26).
                let cluster = ((rd16(&buf, off + 20) as u32) << 16)
                    | rd16(&buf, off + 26) as u32;
                let size = rd32(&buf, off + 28) as u32;
                out.push(DirEntry { name, cluster, size });
            }
        }
        match read_fat_entry(dev, info, c) {
            Some(next) if !is_chain_end(next) => c = next,
            _ => break,
        }
    }
    true
}

/// Follow a file's chain and read its bytes (up to `size`) into `out`.
pub fn read_file(
    dev: &impl BlockDevice, info: &FatInfo, first_cluster: u32, size: u32, out: &mut Vec<u8>,
) -> bool {
    if is_chain_end(first_cluster) { return false; }
    let mut need = size as usize;
    let mut c = first_cluster;
    for _ in 0..1000 {
        if need == 0 { return true; }
        if is_chain_end(c) { return false; }
        let first_sector = info.data_start + (c - 2) * info.sectors_per_cluster as u32;
        for s in 0..info.sectors_per_cluster as u32 {
            if need == 0 { return true; }
            let mut buf = [0u8; 512];
            if !dev.read_sector(first_sector + s, &mut buf) { return false; }
            let take = need.min(512);
            out.extend_from_slice(&buf[..take]);
            need -= take;
        }
        match read_fat_entry(dev, info, c) {
            Some(next) if !is_chain_end(next) => c = next,
            _ => break,
        }
    }
    need == 0
}

// ------------------------------ host tests -----------------------------------
#[cfg(test)]
mod tests {
    use super::*;
    use alloc::vec::Vec;

    /// Build a minimally-valid FAT32 boot sector with a given signature.
    fn boot(signature_ok: bool) -> [u8; 512] {
        let mut b = [0u8; 512];
        b[11] = 0x00; b[12] = 0x02;   // bytes_per_sec = 512
        b[13] = 8;                    // sec_per_clus = 8
        b[14] = 2; b[15] = 0;         // reserved = 2
        b[16] = 2;                    // fat_count = 2
        b[19] = 0; b[20] = 0;         // total16 = 0 -> use total32
        b[22] = 0; b[23] = 0;         // spf16 = 0 -> use spf32
        b[32] = 0x00; b[33] = 0x00; b[34] = 0x10; b[35] = 0x00; // total32 = 1_048_576
        b[36] = 0x00; b[37] = 0x20; b[38] = 0x00; b[39] = 0x00; // spf32 = 8192
        b[44] = 2; b[45] = 0; b[46] = 0; b[47] = 0;             // root_cluster = 2
        if signature_ok { b[510] = 0x55; b[511] = 0xAA; }
        b
    }

    #[test]
    fn parses_valid_boot_sector() {
        let info = parse_boot(&boot(true)).unwrap();
        assert_eq!(info.bytes, 512);
        assert_eq!(info.sectors_per_cluster, 8);
        assert_eq!(info.sectors_per_fat, 8192);
        assert_eq!(info.data_start, 16386); // 2 + 2*8192
    }

    #[test]
    fn rejects_bad_signature() {
        assert_eq!(parse_boot(&boot(false)), Err(FatError::BadSignature));
    }

    #[test]
    fn rejects_non_power_of_two_spc() {
        let mut v = boot(true);
        v[13] = 3;
        assert_eq!(parse_boot(&v), Err(FatError::BadSectorsPerCluster));
    }

    #[test]
    fn rejects_unsupported_sector_size() {
        let mut v = boot(true);
        v[11] = 0x00; v[12] = 0x01; // 256 bytes/sec
        assert_eq!(parse_boot(&v), Err(FatError::UnsupportedSectorSize));
    }

    #[test]
    fn rejects_zero_reserved() {
        let mut v = boot(true);
        v[14] = 0; v[15] = 0;
        assert_eq!(parse_boot(&v), Err(FatError::BadReserved));
    }

    #[test]
    fn rejects_fat16_root_layout() {
        let mut v = boot(true);
        v[44] = 0; v[45] = 0; v[46] = 0; v[47] = 0; // root "dir entries," not a cluster
        assert_eq!(parse_boot(&v), Err(FatError::NotFat32));
    }

    /// An in-memory `BlockDevice`. Sector index → 512-byte contents.
    struct MemDisk { sectors: Vec<[u8; 512]> }
    impl BlockDevice for MemDisk {
        fn read_sector(&self, lba: u32, buf: &mut [u8; 512]) -> bool {
            match self.sectors.get(lba as usize) {
                Some(s) => { *buf = *s; true }
                None => false,
            }
        }
    }

    /// Build a small FAT32 volume. Geometry: bps=512, spc=1, reserved=2,
    /// fat_count=2, spf32=1, root_cluster=2 → data_start=4. FAT: c2→c3→EOC.
    /// The dir entry writes cluster **hi**@20 and **lo**@26 — the *real* FAT32
    /// layout — so the fixture catches the old "read rd32@20" byte-order bug.
    fn build_mem_disk() -> (MemDisk, Vec<u8>) {
        let mut boot = [0u8; 512];
        boot[11] = 0x00; boot[12] = 0x02;      // bps = 512
        boot[13] = 1;                          // spc = 1
        boot[14] = 2; boot[15] = 0;            // reserved = 2
        boot[16] = 2;                          // fat_count = 2
        boot[32] = 0x10; boot[33] = 0x00; boot[34] = 0x00; boot[35] = 0x00; // total32 = 0x10
        boot[36] = 0x01; boot[37] = 0x00; boot[38] = 0x00; boot[39] = 0x00; // spf32 = 1
        boot[44] = 2; boot[45] = 0; boot[46] = 0; boot[47] = 0;             // root = 2
        boot[510] = 0x55; boot[511] = 0xAA;

        let mut sectors = Vec::new();
        sectors.push(boot);              // [0]
        sectors.push([0u8; 512]);        // [1] reserved

        let mut fat = [0u8; 512];
        fat[0..4].copy_from_slice(&0x0FFF_FFF8u32.to_le_bytes());  // media
        fat[4..8].copy_from_slice(&0x0FFF_FFFFu32.to_le_bytes());  // fat[1] reserved
        fat[8..12].copy_from_slice(&3u32.to_le_bytes());           // c2 -> c3
        fat[12..16].copy_from_slice(&0x0FFF_FFFFu32.to_le_bytes()); // c3 -> EOC
        sectors.push(fat);               // [2] FAT1
        sectors.push(fat);               // [3] FAT2 (mirror)

        let content = b"HELLO LIONOS FAT"; // 15 bytes
        let mut root = [0u8; 512];
        root[0..11].copy_from_slice(b"HELLO   TXT");  // 8.3 short name
        root[11] = 0x20;                               // archive attr
        root[20..22].copy_from_slice(&0u16.to_le_bytes()); // cluster HI = 0
        root[26..28].copy_from_slice(&3u16.to_le_bytes()); // cluster LO = 3
        root[28..32].copy_from_slice(&(content.len() as u32).to_le_bytes()); // size
        sectors.push(root);              // [4] root dir
        let mut data = [0u8; 512];
        data[..content.len()].copy_from_slice(content);
        sectors.push(data);              // [5] c3 data

        (MemDisk { sectors }, content.to_vec())
    }

    #[test]
    fn mount_ls_and_reads_short_file() {
        let (disk, content) = build_mem_disk();
        let fs = Fs::mount(&disk).unwrap();
        assert_eq!(fs.info.data_start, 4);

        let mut entries = Vec::new();
        assert!(fs.ls(&disk, &mut entries));
        assert_eq!(entries.len(), 1);
        let e = entries[0];
        assert_eq!(&e.name, b"HELLO   TXT");
        assert_eq!(e.cluster, 3); // hi@20=0, lo@26=3
        assert_eq!(e.size, content.len() as u32);

        let mut got = Vec::new();
        assert!(fs.read(&disk, e.cluster, e.size, &mut got));
        assert_eq!(got, content);
    }

    #[test]
    fn find_by_name_returns_entry() {
        let (disk, content) = build_mem_disk();
        let fs = Fs::mount(&disk).unwrap();
        let e = fs.find(&disk, b"HELLO   TXT").expect("file present");
        assert_eq!(e.size, content.len() as u32);
    }

    #[test]
    fn display_name_formats_dot() {
        let e = DirEntry { name: *b"HELLO   TXT", cluster: 3, size: 15 };
        assert_eq!(e.display_name(), "HELLO.TXT");
    }

    #[test]
    fn chain_end_detection() {
        assert!(is_chain_end(0));
        assert!(is_chain_end(1));
        assert!(is_chain_end(0x0FFF_FFF7)); // bad cluster
        assert!(is_chain_end(0x0FFF_FFF8));
        assert!(is_chain_end(0x0FFF_FFFF)); // EOC
        assert!(!is_chain_end(2));
        assert!(!is_chain_end(100));
        assert!(!is_chain_end(0x0FFF_FFF0)); // reserved but still a number
    }

    #[test]
    fn empty_directory_returns_no_entries() {
        let mut boot = [0u8; 512];
        boot[11] = 0x00; boot[12] = 0x02;
        boot[13] = 1; boot[14] = 2; boot[15] = 0; boot[16] = 2;
        boot[32] = 0x10; boot[36] = 0x01; boot[44] = 2;
        boot[510] = 0x55; boot[511] = 0xAA;
        let mut sectors = Vec::new();
        sectors.push(boot);
        sectors.push([0u8; 512]);
        let mut fat = [0u8; 512];
        fat[0..4].copy_from_slice(&0x0FFF_FFF8u32.to_le_bytes());
        fat[4..8].copy_from_slice(&0x0FFF_FFFFu32.to_le_bytes());
        sectors.push(fat); sectors.push(fat);
        sectors.push([0u8; 512]); // root dir, all zero -> end-of-dir
        let disk = MemDisk { sectors };
        let fs = Fs::mount(&disk).unwrap();
        let mut e = Vec::new();
        assert!(fs.ls(&disk, &mut e));
        assert!(e.is_empty());
    }
}