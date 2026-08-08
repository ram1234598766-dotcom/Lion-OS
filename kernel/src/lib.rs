//! LionOS kernel library.
//!
//! `#![no_std]` library crate so the kernel's pure logic — the memory-map and
//! framebuffer validators — can be unit-tested on the host
//! (`cargo test --target x86_64-unknown-linux-gnu`) and fuzzed (`cargo-fuzz`)
//! without a QEMU session. The freestanding boot entry point lives in
//! `main.rs` and depends on this crate.

#![no_std]
// The `extern "x86-interrupt"` ABI used by the IDT handlers (Month 2). The
// handlers are `target_os="none"`-gated, so the host test build never uses the
// feature — allow the "declared but not used" lint for that build.
#![feature(abi_x86_interrupt)]
#![allow(unused_features)]

// The kernel heap (Month 2): `Vec`/`Box`/`String` from the `alloc` crate. The
// `#[global_allocator]` in `heap.rs` provides the backing store on the kernel
// target; the host test build links `std` (which supplies its own allocator).
extern crate alloc;

// Make `std` available to the unit-test build (the test harness links it), but
// leave the kernel itself freestanding.
#[cfg(test)]
extern crate std;

pub mod drivers;
pub mod ffi;
pub mod frames;
pub mod fs;
pub mod framebuffer;
pub mod gdt;
pub mod heap;
pub mod idt;
pub mod interrupts;
pub mod memory;
pub mod paging;
pub mod sched;
pub mod serial;
pub mod spinlock;