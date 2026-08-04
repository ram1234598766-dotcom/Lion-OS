//! LionOS kernel library.
//!
//! `#![no_std]` library crate so the kernel's pure logic — the memory-map and
//! framebuffer validators — can be unit-tested on the host
//! (`cargo test --target x86_64-unknown-linux-gnu`) and fuzzed (`cargo-fuzz`)
//! without a QEMU session. The freestanding boot entry point lives in
//! `main.rs` and depends on this crate.

#![no_std]

// Make `std` available to the unit-test build (the test harness links it), but
// leave the kernel itself freestanding.
#[cfg(test)]
extern crate std;

pub mod framebuffer;
pub mod memory;
pub mod serial;