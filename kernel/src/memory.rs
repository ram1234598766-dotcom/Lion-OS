//! Physical memory-map validation.
//!
//! The bootloader hands the kernel a `BootInfo` memory map that it has already
//! sorted and de-duplicated, but this module treats it as **untrusted input**
//! (defense in depth — see the Month-1 plan's malformed-input rule) and
//! re-validates it with pure, `no_std`, host-testable functions. `_start` in
//! `main.rs` adapts the bootloader's regions into the raw triples this parser
//! consumes; the same functions back the `cargo-fuzz` target.
//!
//! bootloader 0.11 hands **byte-address** regions (`MemoryRegion { start, end,
//! kind }`), so `_start` uses [`validate_regions_bytes`]. The older frame-based
//! [`validate_regions`] is kept for the fuzz/host-test path that models the
//! 0.9.35 frame-number shape.

/// Physical memory region kind (a subset of the bootloader's `MemoryRegionType`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RegionKind {
    /// Free memory the kernel may use.
    Usable,
    /// Reserved by firmware/hardware or already in use.
    Reserved,
    /// ACPI reclaimable / NVS / bad memory — not usable by the kernel.
    NonUsable,
}

/// A validated physical memory region in **bytes** (bootloader 0.11 passes byte
/// addresses directly; the 0.9.35 frame-based path converted frame numbers).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Region {
    pub start: u64,
    pub len: u64,
    pub kind: RegionKind,
}

impl Region {
    /// A zero-length placeholder usable region (for stack output buffers).
    pub const fn empty() -> Self {
        Region { start: 0, len: 0, kind: RegionKind::Usable }
    }

    /// Exclusive end address.
    pub const fn end(self) -> u64 {
        self.start + self.len
    }
}

/// Why a memory map was rejected.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MapError {
    /// More than [`MAX_REGIONS`] regions supplied.
    TooManyRegions,
    /// A region had zero length (start frame not below end frame).
    ZeroLength,
    /// Converting a frame number to a byte address overflowed `u64`.
    EndOverflow,
    /// Two USABLE regions overlap (double-handout hazard).
    Overlap,
}

impl MapError {
    /// Stable numeric code for serial logging (the kernel avoids `core::fmt`).
    pub const fn code(self) -> u64 {
        match self {
            MapError::TooManyRegions => 1,
            MapError::ZeroLength => 2,
            MapError::EndOverflow => 3,
            MapError::Overlap => 4,
        }
    }
}

/// Maximum number of memory-map regions the kernel accepts (matches the
/// bootloader crate's `MemoryMap` capacity).
pub const MAX_REGIONS: usize = 64;

const FRAME_SIZE: u64 = 4096;

/// Convert a bootloader frame-number region `(start_frame, end_frame, kind)` to
/// a byte-`Region`, rejecting the malformed cases we care about.
fn region_from_frames(
    start_frame: u64,
    end_frame: u64,
    kind: RegionKind,
) -> Result<Region, MapError> {
    if start_frame >= end_frame {
        return Err(MapError::ZeroLength);
    }
    let start = start_frame.checked_mul(FRAME_SIZE).ok_or(MapError::EndOverflow)?;
    let end = end_frame.checked_mul(FRAME_SIZE).ok_or(MapError::EndOverflow)?;
    Ok(Region { start, len: end - start, kind })
}

/// Validate a memory map given as `(start_frame, end_frame, kind)` triples —
/// the shape the bootloader provides — writing the validated (sorted,
/// byte-address) regions into `out` and returning how many were written.
///
/// Validation performed:
/// - at most [`MAX_REGIONS`] entries (and `out` must be large enough);
/// - no zero-length regions (`start_frame < end_frame`);
/// - no `u64` overflow converting frame numbers to byte addresses;
/// - no **USABLE** region overlaps (double-handout hazard). Non-usable regions
///   may overlap freely — only what we will hand out must be disjoint;
/// - output sorted by start address.
pub fn validate_regions(
    input: &[(u64, u64, RegionKind)],
    out: &mut [Region],
) -> Result<usize, MapError> {
    if input.len() > MAX_REGIONS || out.len() < input.len() {
        return Err(MapError::TooManyRegions);
    }

    for (i, &(start, end, kind)) in input.iter().enumerate() {
        out[i] = region_from_frames(start, end, kind)?;
    }

    let count = input.len();
    let regions = &mut out[..count];
    // sort_unstable_by (rather than sort_by_key): the plain key closure form was
    // not resolving on the pinned 2026 nightly.
    regions.sort_unstable_by(|a, b| a.start.cmp(&b.start));

    // Sorted by start, so region j overlaps region i (i < j) exactly when j's
    // start falls before i's end. Check only USABLE pairs.
    for i in 0..count {
        if regions[i].kind != RegionKind::Usable {
            continue;
        }
        for j in (i + 1)..count {
            if regions[j].kind == RegionKind::Usable && regions[j].start < regions[i].end() {
                return Err(MapError::Overlap);
            }
        }
    }

    Ok(count)
}

/// Validate a memory map given as `(start, end, kind)` triples in **bytes** —
/// the bootloader 0.11 `MemoryRegion` shape. Identical checks to
/// [`validate_regions`] but inputs are already byte addresses, so there is no
/// frame→byte conversion (and no `EndOverflow` possible: `start < end` and
/// `end <= u64::MAX` make `end - start` overflow-free).
pub fn validate_regions_bytes(
    input: &[(u64, u64, RegionKind)],
    out: &mut [Region],
) -> Result<usize, MapError> {
    if input.len() > MAX_REGIONS || out.len() < input.len() {
        return Err(MapError::TooManyRegions);
    }

    for (i, &(start, end, kind)) in input.iter().enumerate() {
        if start >= end {
            return Err(MapError::ZeroLength);
        }
        out[i] = Region { start, len: end - start, kind };
    }

    let count = input.len();
    let regions = &mut out[..count];
    regions.sort_unstable_by(|a, b| a.start.cmp(&b.start));

    // Sorted by start, so region j overlaps region i (i < j) exactly when j's
    // start falls before i's end. Check only USABLE pairs.
    for i in 0..count {
        if regions[i].kind != RegionKind::Usable {
            continue;
        }
        for j in (i + 1)..count {
            if regions[j].kind == RegionKind::Usable && regions[j].start < regions[i].end() {
                return Err(MapError::Overlap);
            }
        }
    }

    Ok(count)
}

#[cfg(test)]
mod tests {
    use super::*;

    const BUFFER_CAP: usize = MAX_REGIONS;

    fn usable(start: u64, end: u64) -> (u64, u64, RegionKind) {
        (start, end, RegionKind::Usable)
    }

    fn run(input: &[(u64, u64, RegionKind)]) -> Result<usize, MapError> {
        let mut out = [Region::empty(); BUFFER_CAP];
        validate_regions(input, &mut out)
    }

    #[test]
    fn empty_map_validates() {
        assert_eq!(run(&[]), Ok(0));
    }

    #[test]
    fn single_usable_region_converts_frames_to_bytes() {
        let mut out = [Region::empty(); BUFFER_CAP];
        let n = validate_regions(&[usable(1, 5)], &mut out).unwrap();
        assert_eq!(n, 1);
        assert_eq!(out[0], Region { start: 4096, len: 4096 * 4, kind: RegionKind::Usable });
    }

    #[test]
    fn too_many_regions_is_rejected() {
        let input = [usable(0, 1); MAX_REGIONS + 1];
        assert_eq!(run(&input), Err(MapError::TooManyRegions));
    }

    #[test]
    fn zero_length_region_is_rejected() {
        assert_eq!(run(&[usable(10, 10)]), Err(MapError::ZeroLength));
    }

    #[test]
    fn reversed_region_is_rejected() {
        assert_eq!(run(&[usable(10, 5)]), Err(MapError::ZeroLength));
    }

    #[test]
    fn frame_number_overflow_is_rejected() {
        assert_eq!(
            run(&[usable(u64::MAX / FRAME_SIZE + 1, u64::MAX / FRAME_SIZE + 2)]),
            Err(MapError::EndOverflow)
        );
    }

    #[test]
    fn overlapping_usable_regions_are_rejected() {
        assert_eq!(run(&[usable(4, 8), usable(6, 12)]), Err(MapError::Overlap));
    }

    #[test]
    fn touching_but_not_overlapping_is_ok() {
        // [4..8) and [8..12) share only a boundary — no overlap.
        assert_eq!(run(&[usable(4, 8), usable(8, 12)]), Ok(2));
    }

    #[test]
    fn nonusable_region_may_overlap_usable() {
        // A reserved region overlapping a usable one is fine (only usable/usable
        // must be disjoint).
        let input = [usable(4, 8), (4, 8, RegionKind::Reserved)];
        assert_eq!(run(&input), Ok(2));
    }

    #[test]
    fn output_is_sorted_by_start() {
        let input = [usable(30, 40), usable(10, 20), usable(50, 60)];
        let mut out = [Region::empty(); BUFFER_CAP];
        let n = validate_regions(&input, &mut out).unwrap();
        assert_eq!(n, 3);
        assert_eq!(out[0].start, 10 * FRAME_SIZE);
        assert_eq!(out[1].start, 30 * FRAME_SIZE);
        assert_eq!(out[2].start, 50 * FRAME_SIZE);
        assert_eq!(out[0].len, 10 * FRAME_SIZE);
    }

    // --- validate_regions_bytes (bootloader 0.11 byte-address shape) ---

    fn run_bytes(input: &[(u64, u64, RegionKind)]) -> Result<usize, MapError> {
        let mut out = [Region::empty(); BUFFER_CAP];
        validate_regions_bytes(input, &mut out)
    }

    #[test]
    fn bytes_regions_use_addresses_directly() {
        let mut out = [Region::empty(); BUFFER_CAP];
        let n = validate_regions_bytes(&[usable(0x1000, 0x5000)], &mut out).unwrap();
        assert_eq!(n, 1);
        assert_eq!(out[0], Region { start: 0x1000, len: 0x4000, kind: RegionKind::Usable });
    }

    #[test]
    fn bytes_zero_length_rejected() {
        assert_eq!(run_bytes(&[usable(0x1000, 0x1000)]), Err(MapError::ZeroLength));
    }

    #[test]
    fn bytes_overlap_rejected() {
        assert_eq!(run_bytes(&[usable(0x1000, 0x2000), usable(0x1800, 0x2800)]),
                   Err(MapError::Overlap));
    }

    #[test]
    fn bytes_touching_is_ok() {
        assert_eq!(run_bytes(&[usable(0x1000, 0x2000), usable(0x2000, 0x3000)]), Ok(2));
    }
}