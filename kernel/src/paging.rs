//! Page tables — Month 2, kernel-core.
//!
//! Page tables — Month 2, kernel-core.
//!
//! Constraints learned the hard way under bootloader 0.11.17:
//!   • the kernel boots identity-mapped; CR3 = the bootloader's PML4.
//!   • the bootloader does **not** identity-map its own page-table frames —
//!     reading the frame that CR3 points at (#PF CR2 == CR3) faults. So the
//!     kernel cannot read **or** write the bootloader's tables from virtual
//!     memory to extend the map in place.
//!
//! Consequence: true paging means building and switching to the kernel's **own**
//! page tables (a fresh PML4 covering the kernel image + a frame-backed heap +
//! the framebuffer), then managing them from the `frames::` allocator. That full
//! "take over paging" step is the next increment.
//!
//! This module today provides the pure, host-tested building blocks for it:
//!   • `index4…index1` — 4-level page-index extraction;
//!   • `entry_pointer`/`entry_page`/`flags_of` — PTE encoding;
//!   • `current_cr3()` — safe register read.
//!
//! `probe`/`probe_pml4` (read-only table walkers) exist for after the kernel
//! owns its tables; they are NOT safe on the bootloader's tables (their frames
//! are unmapped) and are never called on the current boot path.

/// PML4 index (bits 39..47).
pub fn index4(v: u64) -> usize {
    ((v >> 39) & 0x1FF) as usize
}

/// PDPT index (bits 30..38).
pub fn index3(v: u64) -> usize {
    ((v >> 30) & 0x1FF) as usize
}

/// Page-directory index (bits 21..29).
pub fn index2(v: u64) -> usize {
    ((v >> 21) & 0x1FF) as usize
}

/// Page-table index (bits 12..20).
pub fn index1(v: u64) -> usize {
    ((v >> 12) & 0x1FF) as usize
}

/// Physical-address mask (bits 12..51).
pub const ADDR_MASK: u64 = 0x000F_FFFF_FFFF_F000;

/// Page flags we use.
pub const PRESENT: u64 = 1 << 0;
pub const WRITABLE: u64 = 1 << 1;
pub const USER: u64 = 1 << 2;

/// Encode a page-table entry that points at the table/frame `addr`.
/// `addr` must be a physical address (already page-aligned; lower bits masked).
pub fn entry_pointer(addr: u64, present: bool, writable: bool) -> u64 {
    let mut e = addr & ADDR_MASK;
    if present {
        e |= PRESENT;
    }
    if writable {
        e |= WRITABLE;
    }
    e
}

/// Encode a leaf entry mapping `frame` (physical) as the page at the virtual
/// address being indexed.
pub fn entry_page(frame: u64, present: bool, writable: bool, user: bool) -> u64 {
    let mut e = frame & ADDR_MASK;
    if present {
        e |= PRESENT;
    }
    if writable {
        e |= WRITABLE;
    }
    if user {
        e |= USER;
    }
    e
}

/// Encode a 2 MiB huge-page leaf entry (PS bit set). `addr` must be 2 MiB
/// aligned.
pub fn entry_huge(addr: u64, present: bool, writable: bool) -> u64 {
    let mut e = addr & ADDR_MASK;
    if present {
        e |= PRESENT;
    }
    if writable {
        e |= WRITABLE;
    }
    e | (1 << 7) // page-size bit
}

/// Return the present + writable bits of an entry (the subset we generally set).
pub fn flags_of(entry: u64) -> u16 {
    (entry & (PRESENT | WRITABLE | USER)) as u16
}

// ---------------------------------------------------------------------------
// kernel-target helpers
// ---------------------------------------------------------------------------

/// Read the current PML4 physical address (CR3).
#[cfg(target_os = "none")]
pub fn current_cr3() -> u64 {
    crate::ffi::read_cr3()
}

/// Read only the top-level PML4 entry for `virt` (no deeper walk). This is
/// safe on the boot path: the bootloader's PML4 (at CR3) is identity-mapped and
/// readable, whereas its *descendant* table frames are not (they sit in the
/// kernel image's data/bss gap), so a full walk would #PF. Used to document the
/// live top-level layout before owning the tables.
///
/// # Safety
/// Read-only; `current_cr3()` must be valid and mapped.
#[cfg(target_os = "none")]
pub unsafe fn probe_pml4(virt: u64) -> u64 {
    let pml4_addr = current_cr3() & ADDR_MASK;
    *(pml4_addr as *const u64).add(index4(virt))
}

/// Walk the 4-level tables and return the leaf PTE controlling `virt`
/// (raw entry; callers check `PRESENT`). Never writes. Handles 1 GiB / 2 MiB
/// huge pages by returning the huge entry directly.
///
/// # Safety
/// Read-only. `virt` must be a canonical address range; `current_cr3()` and the
/// tables it points at must be valid.
#[cfg(target_os = "none")]
pub unsafe fn probe(virt: u64) -> u64 {
    let pml4_addr = current_cr3() & ADDR_MASK;
    let pml4e = *(pml4_addr as *const u64).add(index4(virt));
    if pml4e & PRESENT == 0 {
        return 0;
    }
    let pdpt_addr = pml4e & ADDR_MASK;
    let pdpte = *(pdpt_addr as *const u64).add(index3(virt));
    if pdpte & PRESENT == 0 {
        return 0;
    }
    if pdpte & (1 << 7) != 0 {
        return pdpte; // 1 GiB huge page
    }
    let pd_addr = pdpte & ADDR_MASK;
    let pde = *(pd_addr as *const u64).add(index2(virt));
    if pde & PRESENT == 0 {
        return 0;
    }
    if pde & (1 << 7) != 0 {
        return pde; // 2 MiB huge page
    }
    let pt_addr = pde & ADDR_MASK;
    *(pt_addr as *const u64).add(index1(virt))
}

// NOTE: the `takeover` (owning page tables) is DEFERRED. Bootloader 0.11 does
// not expose its virtual↔physical mapping, so the *physical* address of a fresh
// PML4 (what CR3 needs) cannot be derived from the arena's virtual address —
// `mov cr3, <&arena>` faults. The index/entry helpers below are the tested
// building blocks for the eventual takeover.

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn indices_reconstruct_page_address() {
        // The four indices must recombine to the page-aligned address.
        for v in [
            0x0000_0000_0116_4000u64,
            0x0000_0000_07FE_0000,
            0x0000_0000_8000_0000,
            0x0000_0000_1164_0000,
        ] {
            let page = v & ADDR_MASK;
            let recombined = (index4(v) as u64) << 39
                | (index3(v) as u64) << 30
                | (index2(v) as u64) << 21
                | (index1(v) as u64) << 12;
            assert_eq!(recombined, page, "indices must reconstruct {page:#x}");
        }
    }

    #[test]
    fn indices_are_in_range() {
        for v in [0u64, 1 << 30, 1 << 39, u64::MAX - 0x1000] {
            assert!(index4(v) < 0x200);
            assert!(index3(v) < 0x200);
            assert!(index2(v) < 0x200);
            assert!(index1(v) < 0x200);
        }
    }

    #[test]
    fn entry_pointer_masks_and_sets_flags() {
        let addr: u64 = 0x0000_08A0_0000;
        let e = entry_pointer(addr, true, true);
        assert_eq!(e & ADDR_MASK, addr & ADDR_MASK);
        assert!(e & PRESENT != 0 && e & WRITABLE != 0);
        // Entry is never misaligned/low-bits contaminated.
        assert_eq!(e & 0xFFF, 0x3);
    }

    #[test]
    fn entry_page_encodes_flags() {
        let frame: u64 = 0x0000_08B0_1000;
        let e = entry_page(frame, true, true, false);
        assert_eq!(e & ADDR_MASK, frame);
        assert_eq!(flags_of(e), (PRESENT | WRITABLE) as u16);
    }

    #[test]
    fn huge_entry_sets_ps_bit_and_masks() {
        let addr: u64 = 0x0000_fd00_0000; // 2 MiB aligned
        let e = entry_huge(addr, true, true);
        assert_eq!(e & ADDR_MASK, addr);
        assert!(e & (1 << 7) != 0, "PS bit must be set");
        assert!(e & PRESENT != 0 && e & WRITABLE != 0);
    }

    #[test]
    fn huge_entry_masks_to_page_alignment() {
        // entry_huge masks to ADDR_MASK (4 KiB granularity); the *caller*
        // (takeover) aligns to 2 MiB before calling. Verify the low 4 KiB are
        // dropped and present/write/PS bits survive.
        let addr: u64 = 0x0000_fd02_0000;
        let e = entry_huge(addr, true, true);
        assert_eq!(e & 0xFFF, 0x3 | (1 << 7)); // present + rw + PS
        assert_eq!(e & 0xFFFFF000, addr & 0xFFFFF000);
    }

    }