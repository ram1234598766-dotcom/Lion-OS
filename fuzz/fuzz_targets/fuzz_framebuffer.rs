//! Fuzz target for `lionos_kernel::framebuffer::validate`.
//!
//! Feeds arbitrary bytes decoded as a framebuffer descriptor. The validator
//! must never panic or hang on malformed input — it must return `Ok` or a
//! validation `Err`.

#![no_main]

use libfuzzer_sys::fuzz_target;

use lionos_kernel::framebuffer::{validate, FramebufferInfo};

fuzz_target!(|data: &[u8]| {
    if data.len() < 21 {
        return;
    }
    let fb = FramebufferInfo {
        address: u64::from_le_bytes(data[0..8].try_into().unwrap()),
        width: u32::from_le_bytes(data[8..12].try_into().unwrap()),
        height: u32::from_le_bytes(data[12..16].try_into().unwrap()),
        bpp: data[16],
        pitch: u32::from_le_bytes(data[17..21].try_into().unwrap()),
    };
    let _ = validate(&fb);
});
