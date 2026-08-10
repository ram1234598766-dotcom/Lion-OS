//! `lionos` — host-side launcher CLI for LionOS.
//!
//! Month 1 Week 2: `run` (boot the kernel in QEMU), `doctor` (check the host
//! toolchain), `update` (checksum-verified disk download).

mod doctor;
mod install;
mod qemu;
mod update;

use std::path::PathBuf;
use std::process::ExitCode;

use clap::{Parser, Subcommand};

/// LionOS host launcher.
#[derive(Parser)]
#[command(name = "lionos", version, about, long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Boot the kernel in QEMU.
    Run {
        /// Path to the bootable disk image (bootloader 0.11 image built by the
        /// `os/` crate and copied to the repo-root `target/bios.img`).
        #[arg(long, default_value = "target/bios.img")]
        kernel: PathBuf,
        /// Headless run (no window) — for CI and scripted use.
        #[arg(long)]
        headless: bool,
    },
    /// Check the host environment and print install help if QEMU is missing.
    Doctor,
    /// Install LionOS: provision QEMU + build deps + the Rust toolchain, then
    /// build the bootable disk image. QEMU is a hard requirement — install
    /// aborts if it cannot be installed.
    Install {
        /// Skip the kernel build (provision deps only).
        #[arg(long)]
        skip_build: bool,
        /// Run the install as a detached background job, then return.
        #[arg(long)]
        detach: bool,
    },
    /// Download a LionOS disk image and verify its SHA-256 checksum before use.
    Update {
        /// Source: a local directory path or an http(s):// base URL containing
        /// `lionos-disk.bin` and `checksums.txt`.
        #[arg(long, default_value = "https://github.com/ram1234598766-dotcom/Lion-OS/releases/latest/download")]
        source: String,
    },
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let result = match cli.command {
        Command::Run { kernel, headless } => qemu::run(&kernel, headless)
            .map(|_| ())
            .map_err(|e| e.to_string()),
        Command::Doctor => doctor::run().map_err(|e| e.to_string()),
        Command::Install { skip_build, detach } => {
            install::run(skip_build, detach).map_err(|e| e.to_string())
        }
        Command::Update { source } => update::run(&source).map_err(|e| e.to_string()),
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(msg) => {
            eprintln!("lionos: error: {msg}");
            ExitCode::FAILURE
        }
    }
}
