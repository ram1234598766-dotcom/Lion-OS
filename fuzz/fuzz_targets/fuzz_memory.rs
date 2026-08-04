//! Fuzz target for `lionos_kernel::memory::validate_regions`.
//!
//! Feeds arbitrary bytes decoded as `(start_frame, end_frame, kind)` triples.
//! The parser must never panic or hang on malformed input — it must return
//! `Ok(n)` or a validation `Err`.

#![no_main]

use libfuzzer_sys::fuzz_target;

use lionos_kernel::memory::{validate_regions, Region, RegionKind, MAX_REGIONS};

const KINDS: [RegionKind; 3] = [RegionKind::Usable, RegionKind::Reserved, RegionKind::NonUsable];

fuzz_target!(|data: &[u8]| {
    // Decode 17-byte chunks into (start_frame, end_frame, kind) triples;
    // ignore the ragged tail.
    let triples: Vec<(u64, u64, RegionKind)> = data
        .chunks_exact(17)
        .map(|c| {
            let start = u64::from_le_bytes(c[0..8].try_into().unwrap());
            let end = u64::from_le_bytes(c[8..16].try_into().unwrap());
            let kind = KINDS[(c[16] as usize) % 3];
            (start, end, kind)
        })
        .collect();

    let mut out = [Region::empty(); MAX_REGIONS];
    let _ = validate_regions(&triples, &mut out);
});
