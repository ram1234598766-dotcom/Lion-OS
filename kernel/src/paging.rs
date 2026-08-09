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
/// No-Execute (bit 63) — with EFER.NXE set, a page with this bit is not
/// executable. Used on user *data* pages (stacks) so ring-3 code can't run
/// from them. Bit 63 lies above `ADDR_MASK`, so it never disturbs the frame.
pub const NX: u64 = 1 << 63;

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

// ---------------------------------------------------------------------------
// Page-table TAKEOVER (M2W3c unblock).
//
// How this is no longer blocked: bootloader 0.11 with `mappings.physical_memory`
// enabled (see main.rs `BOOT_CONFIG`) exposes `BootInfo.physical_memory_offset`
// — a virtual window over the WHOLE physical address space. So any physical
// frame `P` (including the bootloader's own table frames, which were previously
// virt-inaccessible) is reachable at `P + offset`. We can now:
//   • read the bootloader's live PML4 (at phys CR3) to inherit its mappings;
//   • write a fresh PML4 frame (allocated from `frames::`) at its phys address,
//     so `mov cr3` gets a real physical root — no more `mov cr3, <&arena>` fault.
//
// Takeover strategy (keeps all live translations valid so execution continues):
//   1. allocate one frame for the kernel's OWN PML4 (phys = frame /* 4096);
//   2. copy the bootloader's 512 top-level PML4 entries into it through the
//      physical window (preserves kernel image, boot stack, boot info, the
//      physical-memory window, device MMIO — everything currently mapped);
//   3. `mov cr3` to our frame's PHYSICAL address + TLB flush (write_cr3 does it);
//   4. now the kernel owns CR3. New mappings are added through the same window.
//
// This is deliberately *incremental*: we copy the top level and share the
// bootloader's lower tables at first. It lets the kernel map/unmap new pages
// and (later months) replace the lower tables wholesale with fully-owned ones.
//---------------------------------------------------------------------------

/// Error from a page-table operation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MapError {
    /// The frame allocator returned `None` (out of physical frames).
    OutOfFrames,
}

// --- physical-memory window primitives (kernel target) ----------------------

/// The physical-memory window offset, recorded by [`takeover`] so later callers
/// (heap, GDT) don't need to thread it through every call. Single-CPU boot.
#[cfg(target_os = "none")]
static mut PHYS_OFFSET: u64 = 0;

/// The physical window offset (recorded by the takeover).
#[cfg(target_os = "none")]
pub fn phys_offset() -> u64 {
    // SAFETY: single-CPU boot; PHYS_OFFSET is set once by takeover, read-only here.
    unsafe { PHYS_OFFSET }
}

/// Convert a physical address to its virtual address via the bootloader's
/// physical-memory window (`phys + offset`). All header reads/writes below route
/// through here so the kernel can touch any physical frame, incl. page tables.
#[cfg(target_os = "none")]
fn phys_to_virt(phys: u64, offset: u64) -> u64 {
    phys.wrapping_add(offset)
}

/// Read one page-table entry (8 bytes) at physical `table_phys` + `index`,
/// through the physical window.
///
/// # Safety
/// `table_phys` must be the physical address of a present page table; `index`
/// must be < 512; `offset` must be the (valid, mapped) physical window offset.
#[cfg(target_os = "none")]
unsafe fn table_read(table_phys: u64, offset: u64, index: usize) -> u64 {
    // SAFETY: caller guarantees `table_phys` is a present, mapped table frame.
    unsafe { *(phys_to_virt(table_phys, offset) as *const u64).add(index) }
}

/// Write a page-table entry at a physical table frame (through the window).
///
/// # Safety
/// Same contract as [`read_p`]; $table_phys must be writable.
#[cfg(target_os = "none")]
unsafe fn table_write(table_phys: u64, offset: u64, index: usize, e: u64) {
    // SAFETY: caller guarantees `table_phys` is a present, writable table.
    unsafe { *(phys_to_virt(table_phys, offset) as *mut u64).add(index) = e }
}

/// PAGE_TAKEOVER — build the kernel's own PML4 (copying the bootloader's
/// top level through the physical window) and load it into CR3. Returns the new
/// physical CR3. After this, the kernel owns the page tables.
///
/// # Safety
/// `offset` must be the valid physical window offset (from `BootInfo`). Must be
/// called once, single-CPU, before any other map/unmap.
#[cfg(target_os = "none")]
pub unsafe fn takeover(offset: u64) -> Result<u64, MapError> {
    // Record the window offset so later callers (heap, GDT) can map frames.
    // SAFETY: single-CPU boot; PHYS_OFFSET set once here.
    unsafe { PHYS_OFFSET = offset }

    // 1. Allocate the kernel's own PML4 frame.
    let frame = crate::frames::allocate_frame().ok_or(MapError::OutOfFrames)?;
    let new_cr3 = frame * 4096;

    // 2. Copy the bootloader's 512 top-level entries into ours. The top level
    //    itself is written through the window. `current_cr3()` is the physical
    //    address of the bootloader's PML4 — reachable via the window.
    let old_cr3 = current_cr3() & ADDR_MASK;
    for i in 0..512 {
        let e = unsafe { table_read(old_cr3, offset, i) };
        unsafe { table_write(new_cr3, offset, i, e) };
    }

    // 3. Switch CR3 to our new physical root (flushes the TLB).
    // SAFETY: `new_cr3` is the physical address of a valid, present PML4 we
    // just populated (it is a mirror of the bootloader's, so all live
    // translations survive).
    unsafe { crate::ffi::write_cr3(new_cr3) };
    Ok(new_cr3)
}

/// Walk the CURRENT (post-takeover) tables and return the leaf PTE controlling
/// `virt` (raw; callers check `PRESENT`). Reads through the physical window, so
/// it works regardless of identity-mapping. 1 GiB / 2 MiB huge pages are passed
/// through.
///
/// # Safety
/// `offset` must be the window offset; tables reachable from `current_cr3()`
/// must be valid.
#[cfg(target_os = "none")]
pub unsafe fn translate(offset: u64, virt: u64) -> u64 {
    let pml4 = current_cr3() & ADDR_MASK;
    let pml4e = unsafe { table_read(pml4, offset, index4(virt)) };
    if pml4e & PRESENT == 0 {
        return 0;
    }
    let pdpt = pml4e & ADDR_MASK;
    let pdpte = unsafe { table_read(pdpt, offset, index3(virt)) };
    if pdpte & PRESENT == 0 {
        return 0;
    }
    if pdpte & (1 << 7) != 0 {
        return pdpte;
    }
    let pd = pdpte & ADDR_MASK;
    let pde = unsafe { table_read(pd, offset, index2(virt)) };
    if pde & PRESENT == 0 {
        return 0;
    }
    if pde & (1 << 7) != 0 {
        return pde;
    }
    let pt = pde & ADDR_MASK;
    unsafe { table_read(pt, offset, index1(virt)) }
}

/// Map a single 4 KiB frame at `virt` (writable; not user), allocating any
/// intermediate table frames via `frames::`. Roots are the current CR3 (post-
/// takeover). Returns `Err(OutOfFrames)` if a table page can't be allocated.
///
/// # Safety
/// `offset` must be the window offset; `virt` must be page-aligned and not
/// already mapped; the allocator must have spare frames.
#[cfg(target_os = "none")]
/// Allocate one physical frame, returning its PHYSICAL ADDRESS (frame * 4096),
/// or `MapError::OutOfFrames` when exhausted.
#[cfg(target_os = "none")]
fn frame_phys() -> Result<u64, MapError> {
    crate::frames::allocate_frame()
        .map(|f| f * 4096)
        .ok_or(MapError::OutOfFrames)
}

/// Zero a freshly-allocated table frame through the physical window.
///
/// # Safety
/// `phys` must be a valid, writable, freshly-allocated frame; `offset` valid.
#[cfg(target_os = "none")]
unsafe fn zero_table(phys: u64, offset: u64) {
    let v = phys_to_virt(phys, offset) as *mut u64;
    for i in 0..512 {
        // SAFETY: `phys` is a fresh writable frame mapped via the window.
        unsafe { *v.add(i) = 0 };
    }
}

/// Allocate a zeroed table frame and return its physical address.
#[cfg(target_os = "none")]
fn alloc_table(offset: u64) -> Result<u64, MapError> {
    let p = frame_phys()?;
    unsafe { zero_table(p, offset) };
    Ok(p)
}

/// Map a single 4 KiB frame at `virt` (present + writable, not user), allocating
/// any intermediate table frames via `frames::`. Roots are the current CR3
/// (post-takeover). Returns `Err(OutOfFrames)` if a table page can't be made.
///
/// # Safety
/// `offset` must be the window offset; `virt` must be page-aligned and not
/// already mapped; the allocator must have spare frames.
#[cfg(target_os = "none")]
pub unsafe fn map_page(offset: u64, virt: u64, phys: u64) -> Result<(), MapError> {
    unsafe { map_page_impl(offset, virt, phys, false, false) }
}

/// Map a single 4 KiB frame at `virt` with the **user (U/S)** bit set, so
/// ring-3 code can access/execute it. Intermediate table entries stay
/// supervisor-only; only the leaf carries U/S. Used for the user code + stack
/// pages of a ring-3 process.
///
/// # Safety
/// Same contract as [`map_page`] (`offset` valid, `virt` page-aligned and
/// unmapped, allocator has frames).
#[cfg(target_os = "none")]
pub unsafe fn map_user_page(offset: u64, virt: u64, phys: u64) -> Result<(), MapError> {
    unsafe { map_page_impl(offset, virt, phys, true, false) }
}

/// Map a user *data* page with the **No-Execute** bit set, so ring-3 code
/// cannot jump into it (e.g. the ring-3 stack). Executable user code still uses
/// [`map_user_page`].
///
/// # Safety
/// Same contract as [`map_user_page`].
#[cfg(target_os = "none")]
pub unsafe fn map_user_data(offset: u64, virt: u64, phys: u64) -> Result<(), MapError> {
    unsafe { map_page_impl(offset, virt, phys, true, true) }
}

/// Shared implementation: walk/populate the 4-level tables and write the leaf
/// with the requested U/S bit.
#[cfg(target_os = "none")]
unsafe fn map_page_impl(offset: u64, virt: u64, phys: u64, user: bool, nx: bool) -> Result<(), MapError> {
    // IMPORTANT (x86 Intel SDM 23.6): a page is accessible to user mode only if
    // the U/S bit is set in EVERY leaf AND in every upper-level page-table entry
    // that maps it. If the PDPT/PD/PT entries stay supervisor (U/S=0), a user
    // fetch/write faults #PF e=0x15. So when mapping a user page we propagate
    // USER onto the intermediate entries we create.
    let ptr = |e: u64| -> u64 { e | if user { USER } else { 0 } };

    let pml4 = current_cr3() & ADDR_MASK;

    // Level 4 → PDPT.
    let e4 = unsafe { table_read(pml4, offset, index4(virt)) };
    let pdpt = if e4 & PRESENT != 0 {
        e4 & ADDR_MASK
    } else {
        let t = alloc_table(offset)?;
        unsafe { table_write(pml4, offset, index4(virt), ptr(entry_pointer(t, true, true))) };
        t
    };

    // Level 3 → PD.
    let e3 = unsafe { table_read(pdpt, offset, index3(virt)) };
    let pd = if e3 & PRESENT != 0 {
        e3 & ADDR_MASK
    } else {
        let t = alloc_table(offset)?;
        unsafe { table_write(pdpt, offset, index3(virt), ptr(entry_pointer(t, true, true))) };
        t
    };

    // Level 2 → PT.
    let e2 = unsafe { table_read(pd, offset, index2(virt)) };
    let pt = if e2 & PRESENT != 0 {
        e2 & ADDR_MASK
    } else {
        let t = alloc_table(offset)?;
        unsafe { table_write(pd, offset, index2(virt), ptr(entry_pointer(t, true, true))) };
        t
    };

    // Leaf — U/S follows the caller's intent; NX marks non-executable data.
    let mut leaf = entry_page(phys, true, true, user);
    if nx {
        leaf |= NX;
    }
    unsafe { table_write(pt, offset, index1(virt), leaf) };
    unsafe { crate::ffi::invlpg(virt) };
    Ok(())
}

/// Find the lowest PML4 index whose entry is `PRESENT == 0` in the CURRENT
/// post-takeover tables — a free 512 GiB region index usable for a fresh map.
///
/// # Safety
/// `offset` must be the window offset; tables reachable from the live CR3.
#[cfg(target_os = "none")]
pub unsafe fn find_free_top_index(offset: u64) -> Option<usize> {
    let pml4 = current_cr3() & ADDR_MASK;
    for i in 0..512 {
        let e = unsafe { table_read(pml4, offset, i) };
        if e & PRESENT == 0 {
            return Some(i);
        }
    }
    None
}

/// Map `count` contiguous 4 KiB frames at contiguous virtual pages starting at
/// `virt_base` (must be page-aligned). Frames are drawn from `frames::` and
/// mapped present+writable. Used by the frame-backed heap to back the allocator.
///
/// # Safety
/// `virt_base` must be page-aligned, in a region that is currently unmapped, and
/// the allocator must have `count` spare frames.
#[cfg(target_os = "none")]
pub unsafe fn map_range(offset: u64, virt_base: u64, count: u64) -> Result<(), MapError> {
    for i in 0..count {
        let phys = frame_phys()?;
        unsafe { map_page(offset, virt_base + i * 4096, phys) }?;
    }
    Ok(())
}

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
    fn nx_bit_is_above_addr_mask() {
        assert_eq!(NX, 1 << 63);
        assert_eq!(NX & ADDR_MASK, 0); // NX never disturbs the frame bits
        // A user data leaf has U/S but NX; a code leaf has U/S with no NX.
        assert!(entry_page(0x1000, true, true, true) & NX == 0);
    }

    #[test]
    fn entry_page_user_sets_user_bit() {
        let frame: u64 = 0x0000_08B0_2000;
        // User leaf: U bit (bit 2) must be set; supervisor leaf must not.
        let user = entry_page(frame, true, true, true);
        assert!(user & USER != 0);
        let sup = entry_page(frame, true, true, false);
        assert_eq!(sup & USER, 0);
        assert_eq!(flags_of(user), (PRESENT | WRITABLE | USER) as u16);
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