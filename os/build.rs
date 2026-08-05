//! LionOS disk-image build.
//!
//! The kernel crate's own build.rs cannot produce the bootable image: build
//! scripts run *before* rustc links the bin, so the finished kernel ELF does
//! not exist there, and a build script in the same package as the bin gets no
//! `CARGO_BIN_FILE_*` var. So this standalone crate takes the kernel bin as a
//! build **artifact** dependency (`CARGO_BIN_FILE_KERNEL_lionos-kernel`) and
//! wraps it with the bootloader 0.11 `DiskImageBuilder` into a BIOS-bootable
//! image. Cargo re-runs this script whenever the kernel artifact changes, which
//! is exactly what CI's negative boot-marker test relies on.

use std::path::PathBuf;

fn main() {
    // bindeps artifact: dep key "lionos-kernel" + bin "lionos-kernel".
    let kernel = PathBuf::from(
        std::env::var_os("CARGO_BIN_FILE_LIONOS_KERNEL_lionos-kernel")
            .expect("CARGO_BIN_FILE_LIONOS_KERNEL_lionos-kernel (kernel bin artifact)"),
    );
    let out_dir = PathBuf::from(std::env::var_os("OUT_DIR").expect("OUT_DIR"));
    let bios_img = out_dir.join("bios.img");

    // BIOS image (MBR). UEFI/GPT via UefiBoot is a later-month addition.
    bootloader::BiosBoot::new(&kernel)
        .create_disk_image(&bios_img)
        .expect("failed to create BIOS disk image");

    // Stable path for CI/launcher at the repo root (target/ is gitignored).
    // There is NO default output path in 0.11 — the caller chooses it.
    let repo_target = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("os is one level under the repo root")
        .join("target");
    std::fs::create_dir_all(&repo_target).unwrap();
    let stable = repo_target.join("bios.img");
    std::fs::copy(&bios_img, &stable).unwrap();

    println!("cargo:rustc-env=BIOS_PATH={}", bios_img.display());
    println!("cargo:rustc-env=BIOS_PATH_STABLE={}", stable.display());
}
