//! `lionos doctor` — check the host toolchain and print install help.

use crate::qemu;

/// Install command for QEMU, chosen at compile time for the build target.
pub fn install_tip() -> &'static str {
    if cfg!(target_os = "macos") {
        "brew install qemu"
    } else if cfg!(target_os = "windows") {
        "winget install QEMU"
    } else {
        "sudo apt install qemu-system-x86"
    }
}

/// Returns Ok(()) if QEMU is present; otherwise prints the missing-tool
/// diagnostic and returns Err (the CLI maps that to a non-zero exit).
pub fn run() -> Result<(), String> {
    match qemu::find_qemu() {
        Some(path) => {
            println!("OK  qemu-system-x86_64 found at {}", path.display());
            println!("    `lionos run` will use this binary.");
            Ok(())
        }
        None => {
            println!("MISSING  qemu-system-x86_64 is not on PATH.");
            println!();
            println!("LionOS needs QEMU to boot the kernel. Install it with:");
            println!("    {}", install_tip());
            println!();
            println!("After installing, re-run `lionos doctor` to confirm.");
            Err("qemu-system-x86_64 not found".to_string())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn install_tip_matches_an_expected_os() {
        let tip = install_tip();
        assert!(
            tip.starts_with("brew ") || tip.starts_with("winget ") || tip.starts_with("sudo apt "),
            "unexpected install tip: {tip}"
        );
    }
}
