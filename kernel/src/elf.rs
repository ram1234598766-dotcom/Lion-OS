//! Minimal ELF64 loader for the ring-3 `user` program — closes the Month-4
//! follow-up (real user programs instead of the hand-encoded byte stub).
//!
//! The user program is a static, non-PIE ELF linked at a fixed low-canonical
//! base (`USER_BASE`, 1 TiB). We parse its `PT_LOAD` segments and the entry
//! point; the kernel-target loader maps those segments into the ring-3 address
//! space with the right U/S + permissions and returns the entry for the
//! ring-3 descent. The pure parse helpers are host-tested.

use alloc::vec;
use alloc::vec::Vec;

/// The fixed base the `user` crate is linked at (`user/linker.ld`).
pub const USER_BASE: u64 = 0x1_0000_0000_0; // 0x10000000000

pub const SEG_EXEC: u32 = 1; // PF_X
pub const SEG_WRITE: u32 = 2; // PF_W

/// One `PT_LOAD` segment to place in the user address space.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Segment {
    pub vaddr: u64,
    pub file_off: usize,
    pub filesz: usize,
    pub memsz: usize,
    pub flags: u32,
}

impl Segment {
    /// True if this is executable code (vs. read/write data).
    pub fn exec(&self) -> bool {
        self.flags & SEG_EXEC != 0
    }
    /// True if this is writable data (should be mapped No-Execute).
    pub fn writable(&self) -> bool {
        self.flags & SEG_WRITE != 0
    }
}

/// The ELF64 entry point (file offset 24).
pub fn entry_point(elf: &[u8]) -> Option<u64> {
    if elf.len() < 64 || &elf[0..4] != b"\x7fELF" || elf[4] != 2 || elf[5] != 1 {
        return None; // not ELF64 LSB
    }
    Some(u64::from_le_bytes(elf[24..32].try_into().ok()?))
}

/// Collect every `PT_LOAD` segment into `out`. Returns the number found.
pub fn load_segments(elf: &[u8], out: &mut Vec<Segment>) -> usize {
    if elf.len() < 64 || &elf[0..4] != b"\x7fELF" {
        return 0;
    }
    let phoff = u64::from_le_bytes(elf[32..40].try_into().unwrap()) as usize;
    let phentsize = u16::from_le_bytes([elf[54], elf[55]]) as usize;
    let phnum = u16::from_le_bytes([elf[56], elf[57]]) as usize;
    let mut n = 0;
    for i in 0..phnum {
        let off = phoff + i * phentsize;
        if off + 56 > elf.len() {
            break;
        }
        let p_type = u32::from_le_bytes(elf[off..off + 4].try_into().unwrap());
        if p_type != 1 {
            // PT_LOAD
            continue;
        }
        let flags = u32::from_le_bytes(elf[off + 4..off + 8].try_into().unwrap());
        let p_offset = u64::from_le_bytes(elf[off + 8..off + 16].try_into().unwrap()) as usize;
        let p_vaddr = u64::from_le_bytes(elf[off + 16..off + 24].try_into().unwrap());
        let p_filesz = u64::from_le_bytes(elf[off + 32..off + 40].try_into().unwrap()) as usize;
        let p_memsz = u64::from_le_bytes(elf[off + 40..off + 48].try_into().unwrap()) as usize;
        out.push(Segment { vaddr: p_vaddr, file_off: p_offset, filesz: p_filesz, memsz: p_memsz, flags });
        n += 1;
    }
    n
}

pub const PT_LOAD: u32 = 1;

#[cfg(test)]
mod tests {
    use super::*;

    fn minimal_elf() -> Vec<u8> {
        // A 64-byte EHDR with one PT_LOAD at the tail.
        let mut e = vec![0u8; 64 + 56];
        e[0..4].copy_from_slice(b"\x7fELF");
        e[4] = 2; // 64-bit
        e[5] = 1; // LSB
        e[0x18..0x20].copy_from_slice(&0x10000000020u64.to_le_bytes()); // e_entry
        e[0x20..0x28].copy_from_slice(&64u64.to_le_bytes()); // e_phoff = 64
        e[0x36] = 56; // e_phentsize = 56
        e[0x38] = 1; // e_phnum = 1
        // PHDR
        e[64..68].copy_from_slice(&PT_LOAD.to_le_bytes());
        e[68..72].copy_from_slice(&(SEG_EXEC as u32).to_le_bytes()); // flags R E
        e[72..80].copy_from_slice(&0x1000u64.to_le_bytes()); // p_offset
        e[80..88].copy_from_slice(&0x10000000000u64.to_le_bytes()); // p_vaddr
        e[96..104].copy_from_slice(&0x72u64.to_le_bytes()); // p_filesz
        e[104..112].copy_from_slice(&0x72u64.to_le_bytes()); // p_memsz
        e
    }

    #[test]
    fn parses_entry() {
        let e = minimal_elf();
        assert_eq!(entry_point(&e), Some(0x10000000020));
        assert_eq!(entry_point(&[0; 4]), None);
    }

    #[test]
    fn parses_load_segments() {
        let e = minimal_elf();
        let mut segs = Vec::new();
        assert_eq!(load_segments(&e, &mut segs), 1);
        assert_eq!(segs[0].vaddr, 0x10000000000);
        assert!(segs[0].exec());
        assert_eq!(segs[0].filesz, 0x72);
    }
}