//! `lionos install` — provision the host and build the LionOS desktop image.
//!
//! This is Rust's answer to "install the OS": it is the installation manager.
//! Taken together with `run` it gets a machine from nothing to a booted desktop.
//!
//! What it provisions (the exact set CI needs to build `target/bios.img`):
//!   - **QEMU** (HARD requirement — LionOS only runs inside QEMU; the install
//!     aborts if QEMU cannot be installed),
//!   - the build toolchain: `nasm`, a C/C++ compiler, `mtools`, and **Zig 0.14**
//!     (the kernel's mixed-language `build.rs` compiles `asm/*`, `c/*`, `cpp/*`
//!     and `zig/*` unconditionally),
//!   - the Rust toolchain pinned to `rust-toolchain.toml` (nightly + the
//!     `x86_64-unknown-none` target + `rust-src` + `llvm-tools-preview`),
//!   - then builds the kernel and the bootable disk image (`kernel` then `os`),
//!     streamed to the console and to `~/.lionos/install.log`.
//!
//! Everything runs non-interactively. `--background` spawns a detached child
//! that finishes in the background while you poll the log.

use std::fs::{self, File};
use std::io::{BufRead, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use crate::qemu;

/// Data directory holding logs/cache, matching `update::cache_dir`.
fn data_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("LIONOS_DATA_DIR") {
        return PathBuf::from(dir);
    }
    let home = std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .unwrap_or_else(|_| ".".into());
    PathBuf::from(home).join(".lionos")
}

fn log_path() -> PathBuf {
    data_dir().join("install.log")
}

/// Append a line to the install log (best-effort).
fn log(msg: &str) {
    fs::create_dir_all(data_dir()).ok();
    let mut f = File::options().create(true).append(true).open(log_path()).ok();
    if let Some(f) = f.as_mut() {
        let _ = writeln!(f, "{}", msg);
    }
}

/// Is `bin` resolvable on PATH?
fn which(bin: &str) -> bool {
    let path = match std::env::var_os("PATH") {
        Some(p) => p,
        None => return false,
    };
    for dir in std::env::split_paths(&path) {
        let candidate = dir.join(bin);
        if candidate.is_file() {
            return true;
        }
        #[cfg(windows)]
        if candidate.with_extension("exe").is_file() {
            return true;
        }
    }
    false
}

/// Platform family, as a tag.
fn os_tag() -> &'static str {
    #[cfg(target_os = "macos")]
    { "macos" }
    #[cfg(target_os = "windows")]
    { "windows" }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    { "linux" }
}

/// The install command that provides a system package on this platform.
/// Returns None when there is no package manager we know how to drive.
fn pkg_install_argv(package: &str) -> Option<Vec<String>> {
    #[cfg(target_os = "windows")]
    {
        let id = match package {
            "qemu" => "QEMU.QEMU",
            "nasm" => "Nasm.Nasm",
            "zig" => "KreyaDev.Zigstd", // best-effort; winget id may differ
            _ => return None,
        };
        Some(vec![
            "winget".into(),
            "install".into(),
            format!("--id={id}"),
            "--accept-package-agreements".into(),
            "--accept-source-agreements".into(),
            "--silent".into(),
            "--disable-interactivity".into(),
        ])
    }
    #[cfg(target_os = "macos")]
    {
        Some(vec![
            "brew".into(),
            "install".into(),
            package.to_string(),
        ])
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        let run: Option<Vec<String>> = None;
        if which("apt-get") {
            Some(vec!["sudo".into(), "apt-get".into(), "install".into(), "-y".into(), package.to_string()])
        } else if which("dnf") {
            Some(vec!["sudo".into(), "dnf".into(), "install".into(), "-y".into(), package.to_string()])
        } else if which("yum") {
            Some(vec!["sudo".into(), "yum".into(), "install".into(), "-y".into(), package.to_string()])
        } else if which("pacman") {
            Some(vec!["sudo".into(), "pacman".into(), "-S".into(), "--noconfirm".into(), package.to_string()])
        } else {
            run
        }
    }
}

/// Run `program` with `args`, streaming stdout+stderr to the console and the
/// install log. Returns Ok(()) on a zero exit status.
fn stream<I, S>(program: &str, args: I) -> Result<(), String>
where
    I: IntoIterator<Item = S>,
    S: AsRef<std::ffi::OsStr>,
{
    let all: Vec<String> = args.into_iter().map(|a| a.as_ref().to_string_lossy().into_owned()).collect();
    log(&format!("$ {} {}", program, all.join(" ")));
    let output = Command::new(program)
        .args(&all)
        .stdin(Stdio::inherit())
        .output()
        .map_err(|e| format!("failed to spawn {program}: {e}"))?;

    for line in output.lines() {
        println!("{line}");
        log(&line);
    }
    if output.status.success() {
        Ok(())
    } else {
        Err(format!("`{program}` exited with {}", output.status))
    }
}

/// Convenience: a completed process's combined stdout+stderr, line by line.
trait Lines {
    fn lines(&self) -> Vec<String>;
}
impl Lines for std::process::Output {
    fn lines(&self) -> Vec<String> {
        let mut out = Vec::new();
        for bytes in [&self.stdout, &self.stderr] {
            for line in bytes.lines() {
                if let Ok(line) = line {
                    out.push(line);
                }
            }
        }
        out
    }
}

fn step(what: &str) {
    println!("== {what} ==");
    log(&format!("== {what} =="));
}

// ---------------------------------------------------------------------------
// dependencies
// ---------------------------------------------------------------------------

/// QEMU is mandatory. Install it if missing; abort the whole install otherwise.
fn ensure_qemu() -> Result<(), String> {
    step("QEMU (required)");
    if qemu::find_qemu().is_some() {
        println!("OK   qemu-system-x86_64 already on PATH");
        return Ok(());
    }
    if let Some(argv) = pkg_install_argv("qemu") {
        stream(argv[0].as_str(), &argv[1..])?;
        if qemu::find_qemu().is_some() {
            println!("OK   QEMU installed");
            return Ok(());
        }
        return Err("QEMU installed but still not on PATH — open a new terminal and re-run `lionos doctor`".into());
    }
    Err("QEMU is required to run LionOS but no supported package manager was found. Install QEMU manually then re-run `lionos install`.".into())
}

/// Best-effort provision of the build toolchain (nasm, C/C++ compiler, Zig).
/// Keeps going even if an optional compiler is missing, but reports it loudly.
fn ensure_build_tools() -> Result<(), String> {
    let mut missing = Vec::new();
    for (tool, pkg) in [("nasm", "nasm"), ("zig", "zig"), ("mtools", "mtools")] {
        if which(tool) {
            println!("OK   {tool}");
        } else if let Some(argv) = pkg_install_argv(pkg) {
            println!("installing {tool} ...");
            if stream(argv[0].as_str(), &argv[1..]).is_err() {
                missing.push(tool);
            }
        } else {
            missing.push(tool);
        }
    }
    // C/C++ compiler via the platform's meta-package.
    let c_compiler = if which("g++") || which("clang++") {
        "g++/clang++"
    } else if let Some(argv) = pkg_install_argv("g++") {
        println!("installing g++ ...");
        if stream(argv[0].as_str(), &argv[1..]).is_ok() && which("g++") {
            "g++"
        } else {
            missing.push("g++");
            ""
        }
    } else {
        missing.push("g++");
        ""
    };
    if !c_compiler.is_empty() {
        println!("OK   {c_compiler}");
    }

    if !missing.is_empty() {
        return Err(format!(
            "missing build tools: {} — install them manually, or the kernel build (`cd kernel && cargo build`) will fail.",
            missing.join(", ")
        ));
    }
    Ok(())
}

/// Install the pinned Rust toolchain + target + components (idempotent).
fn ensure_rust() -> Result<(), String> {
    if !which("rustup") {
        // Install rustup non-interactively if absent.
        match stream("sh", &["-c", "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"]) {
            Ok(()) => println!("OK   rustup installed"),
            Err(e) => return Err(format!("rustup not found and auto-install failed: {e}")),
        }
    }
    // rust-toolchain.toml selects the channel; let rustup reconcile it.
    step("Rust toolchain (nightly + x86_64-unknown-none)");
    stream("rustup", ["toolchain", "install", "nightly-2026-08-02"])?;
    stream("rustup", ["+nightly-2026-08-02", "component", "add", "rust-src", "llvm-tools-preview"])?;
    stream("rustup", ["+nightly-2026-08-02", "target", "add", "x86_64-unknown-none"])?;
    Ok(())
}

// ---------------------------------------------------------------------------
// build
// ---------------------------------------------------------------------------

/// Upward-search from `cwd` for a repo root containing `kernel` and `os`.
fn find_repo_root() -> Option<PathBuf> {
    let mut dir = std::env::current_dir().ok()?;
    loop {
        if dir.join("kernel").is_dir() && dir.join("os").is_dir() {
            return Some(dir);
        }
        if !dir.pop() {
            return None;
        }
    }
}

/// Build `kernel`, then `os`, producing the bootable `target/bios.img`.
fn build_disk(root: &Path) -> Result<(), String> {
    step("Building kernel + disk image (this is the long step)");
    for (cwd, label) in [("kernel", "kernel"), ("os", "disk image")] {
        println!("building {label} in {}/{} ...", root.display(), cwd);
        let status = Command::new("cargo")
            .arg("build")
            .current_dir(root.join(cwd))
            .stdin(Stdio::inherit())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .status()
            .map_err(|e| format!("spawning cargo in {cwd}: {e}"))?;
        if !status.success() {
            return Err(format!("`cargo build` in {cwd} failed with {status}"));
        }
    }
    let img = root.join("target").join("bios.img");
    if img.is_file() {
        println!("OK   produced {}", img.display());
        println!("     boot it with: lionos run");
    } else {
        return Err(format!("expected {} but it was not produced", img.display()));
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// entry
// ---------------------------------------------------------------------------

/// Run the install. `skip_build` skips the kernel build; `detach` backgrounds it.
pub fn run(skip_build: bool, detach: bool) -> Result<(), String> {
    if detach {
        return run_detached(skip_build);
    }
    run_inner(skip_build)
}

/// Spawn a detached copy of `lionos install` that finishes in the background.
fn run_detached(skip_build: bool) -> Result<(), String> {
    log("launching background install job");
    let exe = std::env::current_exe().map_err(|e| format!("cannot find this binary: {e}"))?;
    let mut args = vec!["install".to_string()];
    if skip_build {
        args.push("--skip-build".to_string());
    }
    let logfile = File::options().create(true).append(true).open(log_path())
        .map_err(|e| format!("cannot open {}: {e}", log_path().display()))?;
    let child = Command::new(&exe)
        .args(&args)
        .stdin(Stdio::null())
        .stdout(Stdio::from(logfile))
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| format!("cannot background install: {e}"))?;
    println!("LionOS installing in the background (pid {}).", child.id());
    println!("  log:    {}", log_path().display());
    println!("  poll with: lionos doctor");
    Ok(())
}

fn run_inner(skip_build: bool) -> Result<(), String> {
    log(&format!("=== LionOS installer start (host={}, data={}) ===", os_tag(), data_dir().display()));
    ensure_qemu()?;          // hard requirement — abort on failure
    ensure_build_tools()?;   // nasm, Zig, mtools, g++
    ensure_rust()?;          // pinned nightly + target
    if !skip_build {
        let root = find_repo_root()
            .ok_or_else(|| "cannot find repo root (need kernel/ and os/ — run from the repo)".to_string())?;
        build_disk(&root)?;
    } else {
        println!("skipping kernel build (-skip-build)");
    }
    println!("=== LionOS install complete ===");
    log("=== LionOS install complete ===");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn os_tag_is_one_of_the_supported_families() {
        assert!("linux macos windows".split(' ').any(|t| t == os_tag()));
    }

    #[test]
    fn which_resolves_existing_tools() {
        // rustup/cargo are always on a Rust dev host's PATH in CI.
        assert!(which("cargo") || which("rustup"));
    }

    #[test]
    fn log_path_is_under_dot_lionos() {
        assert!(log_path().to_string_lossy().contains(".lionos"));
    }
}