//! LionOS disk-image builder — host helper.
//!
//! The bootable BIOS image is produced by `build.rs` (via the bootloader 0.11
//! `BiosBoot` disk-image builder) and copied to the repo-root `target/bios.img`.
//! This binary keeps the package buildable and prints where the image landed so
//! CI/launcher tooling can reference it.

fn main() {
    println!("bios image: {}", option_env!("BIOS_PATH_STABLE").unwrap_or("<unknown>"));
}
