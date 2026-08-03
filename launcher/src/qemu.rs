//! QEMU discovery and launch.
//!
//! The QEMU command line is built as a real argument vector and passed to
//! `Command` directly — never through a shell string. User-supplied flags (the
//! `--kernel` path, for example) are therefore never shell-interpreted.

use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus, Stdio};

#[cfg(windows)]
const QEMU_NAMES: &[&str] = &["qemu-system-x86_64.exe", "qemu-system-x86.exe"];
#[cfg(not(windows))]
const QEMU_NAMES: &[&str] = &["qemu-system-x86_64", "qemu-system-x86"];

/// Locate a QEMU binary on `PATH`.
pub fn find_qemu() -> Option<PathBuf> {
    let path = std::env::var_os("PATH")?;
    for dir in std::env::split_paths(&path) {
        for name in QEMU_NAMES {
            let candidate = dir.join(name);
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }
    None
}

/// Build the QEMU argv for a given disk image. Exposed for testing.
pub fn build_argv(kernel: &Path, headless: bool) -> Vec<String> {
    let mut argv = vec![
        "-machine".into(),
        "accel=tcg".into(), // portable fallback; no hard dependency on KVM
        "-no-reboot".into(),
    ];
    if headless {
        // -nographic already routes serial to stdio; a second -serial stdio
        // would be rejected ("cannot use stdio by multiple character devices").
        argv.push("-nographic".into());
    } else {
        argv.push("-serial".into());
        argv.push("stdio".into());
    }
    argv.push("-drive".into());
    argv.push(format!("format=raw,file={}", kernel.display()));
    argv
}

/// Launch QEMU to boot `kernel` and wait for it to exit.
///
/// `headless` adds `-nographic` so serial output goes to stdout (used by CI to
/// grep for the boot marker). In an interactive terminal, omit it for the same
/// windowed behaviour as the manual Week-1 command.
pub fn run(kernel: &Path, headless: bool) -> std::io::Result<ExitStatus> {
    let qemu = find_qemu().ok_or_else(|| {
        std::io::Error::other("qemu-system-x86_64 not found on PATH — run `lionos doctor` for install help")
    })?;

    if !kernel.is_file() {
        return Err(std::io::Error::other(format!(
            "kernel image not found at {} — build it with `cargo bootimage` in the repo root",
            kernel.display()
        )));
    }

    let mut cmd = Command::new(qemu);
    cmd.args(build_argv(kernel, headless));
    cmd.stdin(Stdio::inherit());
    cmd.stdout(Stdio::inherit());
    cmd.stderr(Stdio::inherit());

    let mut child = cmd.spawn()?;
    child.wait()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn argv_is_a_plain_vector_without_shell_interpolation() {
        // A kernel path containing shell metacharacters must appear literally
        // in the argv (one argument), never be re-parsed by a shell.
        let sneaky = Path::new("disk image; rm -rf /");
        let argv = build_argv(sneaky, true);
        assert!(argv.contains(&format!("format=raw,file={}", sneaky.display())));
        assert!(argv.contains(&"-nographic".to_string()));
        assert!(!argv.iter().any(|a| a.contains("sh") && a.contains("-c")));
    }
}
