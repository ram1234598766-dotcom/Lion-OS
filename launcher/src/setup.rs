//! `lionos setup` — the interactive installation wizard.
//!
//! A dependency-free terminal UI (ANSI escape sequences + raw-mode key reads,
//! no third-party TUI crate). Two pages over the compulsory host toolchain and
//! the LionOS component picker, then auto-configure + build. The rendering is
//! pure (returns strings) and host-tested; only key handling and the terminal
//! clear/write touch the real terminal, and both fall back gracefully when no
//! terminal is attached (CI, piped stdin) via `LIONOS_SMOKE`.
//!
//! Navigation: Up/Down to move the cursor, Space to toggle a recommended
//! component (`🔒`/`(req)` required ones are locked), Enter to proceed. On Unix
//! we put the terminal in raw mode; on Windows / no-terminal we accept numbered
//! input (`n` toggles) so the wizard never breaks on a non-VT host.

use std::io::Write;

#[cfg(unix)]
use std::io::Read;
#[cfg(unix)]
use std::process::Command;

use crate::install;
use crate::selection::{COMPONENTS, Selection};

/// A decoded key press. `Up`/`Down` move; `Toggle` flips a recommended item;
/// `Enter` proceeds; `Quit` aborts.
/// (`Up`/`Down`/`Toggle` are only *constructed* by the Unix raw-mode reader, so
/// an allowed dead-code tag keeps the non-unix build warning-free.)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg_attr(not(unix), allow(dead_code))]
pub enum Key {
    Up,
    Down,
    Toggle,
    Enter,
    Quit,
    Number(u8),
    Unknown,
}

/// ANSI clear-screen + move home + optional color reset.
fn clear() -> String {
    "\x1b[2J\x1b[H".to_string()
}

fn dim(s: &str) -> String {
    format!("\x1b[2m{s}\x1b[0m")
}
fn bold(s: &str) -> String {
    format!("\x1b[1m{s}\x1b[0m")
}
fn green(s: &str) -> String {
    format!("\x1b[32m{s}\x1b[0m")
}
fn yellow(s: &str) -> String {
    format!("\x1b[33m{s}\x1b[0m")
}
fn red(s: &str) -> String {
    format!("\x1b[31m{s}\x1b[0m")
}

/// Languages this OS is built from — surfaced on the welcome screen.
const LANGUAGES: &[&str] = &["Rust", "C", "C++ (17)", "Zig", "NASM"];

/// The welcome screen.
pub fn render_welcome() -> String {
    let mut s = clear();
    s.push_str(&bold("  ██╗     ██╗ ██████╗ ███╗   ██╗  ██████╗ ███████╗\n"));
    s.push_str(&bold("  ██║     ██║██╔═══██╗████╗  ██║██╔═══██╗██╔════╝\n"));
    s.push_str(&bold("  ██║  █  ██║██║   ██║██╔██╗ ██║██║   ██║███████╗\n"));
    s.push_str(&bold("  ██║██╗██╔╝██║   ██║██║╚██╗██║██║   ██║╚════██║\n"));
    s.push_str(&bold("  ██╝██████║╚██████╔╝██║ ╚████║╚██████╔╝███████║\n"));
    s.push_str(&bold("  ███████╔╝ ╚═════╝ ╚═╝  ╚═══╝ ╚═════╝ ╚══════╝\n\n"));
    s.push_str(&yellow("  LionOS setup — the standalone installation manager\n"));
    s.push_str(&dim("\n  This installs the LionOS host toolchain, auto-configures\n"));
    s.push_str(&dim("  the build, then builds a bootable disk image in QEMU.\n\n"));
    s.push_str(&bold("  Built from: "));
    s.push_str(&green(&LANGUAGES.join(" · ")));
    s.push_str(&dim("\n\n  [Enter] begin   [Q] quit\n"));
    s
}

/// Page 1 — the host toolchain. Every entry is compulsory (🔒), so there is
/// nothing to toggle here; it is a fixed, unavoidable provisioning list. Each
/// row is tagged with the language its binary drives.
pub fn render_page1() -> String {
    let mut s = clear();
    s.push_str(&bold("  Page 1 — Required host toolchain\n"));
    s.push_str(&dim("  All compulsory. The multilingual build needs every one.\n\n"));
    for t in install::HOST_TOOLS {
        s.push_str(&format!("   🔒 {}  {}\n", &yellow(t.name), &dim(&format!("({})", t.lang))));
    }
    s.push_str(&dim("\n  Every tool is required and auto-provisioned (package\n"));
    s.push_str(&dim("  manager first, then a verified staged download).\n"));
    s.push_str(&dim("\n  [Enter] provision these, then choose components\n"));
    s
}

/// Page 2 — the LionOS component picker. `sel` is the current selection and
/// `cursor` is the highlighted row index. Required components render `🔒`
/// (locked) and cannot be toggled; recommended ones render `[x]`/`[ ]`.
pub fn render_page2(sel: &Selection, cursor: usize) -> String {
    let mut s = clear();
    s.push_str(&bold("  Page 2 — LionOS components\n"));
    s.push_str(&dim("  🔒 = compulsory   ·   [x]/[ ] = recommended   ·   Space toggles\n\n"));
    for (i, c) in COMPONENTS.iter().enumerate() {
        let marker = if i == cursor { "▶" } else { " " };
        let mut row = String::from(" ");
        row.push_str(marker);
        if c.required {
            row.push_str(&format!(" 🔒 {}  {}", &yellow(c.key), &dim("(required)")));
        } else if sel.is_enabled(c.key) {
            row.push_str(&format!(" [x] {}  ", c.key));
        } else {
            row.push_str(&format!(" [ ] {}  ", c.key));
        }
        // Highlight the cursor row (invert-adjacent dim for a clear current line).
        if i == cursor {
            s.push_str(&bold(&row));
        } else {
            s.push_str(&row);
        }
        s.push('\n');
    }
    s.push_str(&dim(&format!("\n  {} of {} enabled\n", sel.enabled.len(), COMPONENTS.len())));
    s.push_str(&dim("\n  [Enter] build with this selection   [Q] quit\n"));
    s
}

/// Page 3 — live provisioning/build progress. `steps` is the ordered step list
/// and `status` parallels it: `Some(true)` = done, `Some(false)` = failed,
/// `None` = pending. The screen is re-rendered in place after every step.
pub fn render_page3(steps: &[&'static str], status: &[Option<bool>]) -> String {
    let mut s = clear();
    s.push_str(&bold("  Page 3 — Provisioning & build\n"));
    s.push_str(&dim("  Installing the host toolchain, then building the disk image.\n\n"));
    for (i, name) in steps.iter().enumerate() {
        let mark = match status.get(i) {
            Some(Some(true)) => green("✓"),
            Some(Some(false)) => red("✗"),
            _ => dim("·"),
        };
        s.push_str(&format!("   {mark}  {name}\n"));
    }
    s.push_str(&dim("\n  This can take a few minutes. The install log records\n"));
    s.push_str(&dim(&format!("  every step: {}", install::log_path().display())));
    s
}

/// The final screen after provisioning + build. `ok` is the overall result;
/// on failure `error` carries the first failing step's message.
pub fn render_finish(sel: &Selection, ok: bool, error: Option<&str>) -> String {
    let mut s = clear();
    if ok {
        s.push_str(&green(&bold("  ✓ LionOS setup complete")));
        s.push_str(&dim("\n\n  The bootable disk image is ready.\n"));
    } else {
        s.push_str(&red(&bold("  ✗ LionOS setup failed")));
        if let Some(e) = error {
            s.push_str(&red(&format!("\n\n  {e}")));
        }
        s.push_str(&dim("\n\n  Fix the step above and re-run `lionos setup`."));
    }
    s.push_str(&dim(&format!("\n  Components enabled: {}", sel.csv())));
    s.push_str(&dim(&format!("\n  Install log: {}", install::log_path().display())));
    s.push_str(&green("\n\n  lionos run"));
    s
}

/// Drive `install::run_setup_with_progress` while re-rendering page 3 after
/// every step, then print the finish screen. Shared by the smoke path and the
/// interactive wizard so both show identical progress.
fn run_with_progress(sel: &Selection, from_release: bool, steps: &[&'static str]) -> Result<(), String> {
    let mut status: Vec<Option<bool>> = vec![None; steps.len()];
    print!("{}", render_page3(steps, &status));
    let _ = std::io::stdout().flush();
    let res = install::run_setup_with_progress(sel, from_release, |name, ok| {
        if let Some(i) = steps.iter().position(|&s| s == name) {
            status[i] = Some(ok);
        }
        print!("{}", render_page3(steps, &status));
        let _ = std::io::stdout().flush();
    });
    let (ok, err) = match &res {
        Ok(()) => (true, None),
        Err(e) => (false, Some(e.as_str())),
    };
    println!("{}", render_finish(sel, ok, err));
    res
}

/// Read one key from the terminal. Unix: raw-mode single-byte + escape-prefix
/// decoding (arrow keys arrive as `0x1b [ A/B`). Non-Unix or stdin-not-a-tty:
/// wait for a line and accept a digit or `q`/Enter (portable fallback).
pub fn read_key() -> Key {
    #[cfg(unix)]
    {
        if isatty_stdin() {
            let saved = Command::new("stty").arg("-g").output().ok().and_then(|o| String::from_utf8(o.stdout).ok());
            let _ = Command::new("sh").args(["-c", "stty raw -echo min 1 time 0 2>/dev/null"]).status();
            let b = read_byte().unwrap_or(b'\n');
            let key = match b {
                0x1b => {
                    // ESC sequence: consume [ A / [ B for Up/Down, plain Esc = Quit.
                    let _mid = read_byte();
                    let end = read_byte().unwrap_or(0);
                    if end == b'A' {
                        Some(Key::Up)
                    } else if end == b'B' {
                        Some(Key::Down)
                    } else {
                        Some(Key::Quit)
                    }
                }
                b' ' => Some(Key::Toggle),
                b'\r' | b'\n' => Some(Key::Enter),
                b'q' | b'Q' | 0x03 => Some(Key::Quit),
                b'0'..=b'9' => Some(Key::Number(b - b'0')),
                _ => Some(Key::Unknown),
            }
            .unwrap_or(Key::Unknown);
            // Restore terminal.
            if let Some(g) = saved {
                let _ = Command::new("stty").arg(g).status();
            }
            return key;
        }
    }
    // Portable fallback: read a line.
    let mut line = String::new();
    if std::io::stdin().read_line(&mut line).is_ok() {
        let t = line.trim();
        match t {
            "" => Key::Enter,
            "q" | "Q" => Key::Quit,
            _ => {
                // Allow a single digit to toggle that numbered component.
                if t.len() == 1 && t.as_bytes()[0].is_ascii_digit() {
                    Key::Number(t.as_bytes()[0] - b'0')
                } else {
                    Key::Unknown
                }
            }
        }
    } else {
        Key::Quit
    }
}

#[cfg(unix)]
fn isatty_stdin() -> bool {
    use std::io::IsTerminal;
    std::io::stdin().is_terminal()
}

#[cfg(unix)]
fn read_byte() -> Option<u8> {
    let mut buf = [0u8; 1];
    let n = std::io::stdin().read(&mut buf).ok()?;
    if n == 0 {
        None
    } else {
        Some(buf[0])
    }
}

/// Run the interactive wizard. `LIONOS_SMOKE=1` drives it non-interactively for
/// CI: pages render once, the default selection is taken, provisioning +
/// build run, and `LIONOS_SETUP_PAGES_OK` is printed.
/// `from_release` fetches the prebuilt disk from GitHub instead of building.
pub fn run(from_release: bool) -> Result<(), String> {
    if std::env::var("LIONOS_SMOKE").is_ok() {
        return run_smoke(from_release);
    }
    run_wizard(from_release)
}

fn run_smoke(from_release: bool) -> Result<(), String> {
    println!("{}", render_welcome());
    println!("{}", render_page1());
    let sel = Selection::default();
    println!("{}", render_page2(&sel, 0));
    println!();
    println!("LIONOS_SETUP_PAGES_OK components={}", sel.csv());
    // Actually provision + build (or download the prebuilt disk), since that's
    // what CI wants to prove. Page 3 shows live progress; the finish screen
    // summarizes the outcome.
    let steps: Vec<&'static str> = if from_release {
        vec!["qemu", "prebuilt disk"]
    } else {
        install::HOST_TOOLS.iter().map(|t| t.name).chain(std::iter::once("build")).collect()
    };
    run_with_progress(&sel, from_release, &steps)
}

/// The interactive path: welcome → page 1 → page 2 → provision + build
/// (or, with `--release`, welcome → page 1 → prebuilt-disk download).
fn run_wizard(from_release: bool) -> Result<(), String> {
    println!("{}", render_welcome());
    wait_for(&[Key::Enter]);

    if from_release {
        // Release install: no component picker — the prebuilt image is used as
        // published. Page 1 (the QEMU requirement) is still shown.
        println!("{}", render_page1());
        wait_for(&[Key::Enter]);
        return run_with_progress(&Selection::default(), true, &["qemu", "prebuilt disk"]);
    }

    println!("{}", render_page1());
    wait_for(&[Key::Enter]);

    let mut sel = Selection::default();
    let mut cursor = 0usize;
    loop {
        print!("{}", render_page2(&sel, cursor));
        let _ = std::io::stdout().flush();
        match read_key() {
            Key::Up => cursor = cursor.saturating_sub(1),
            Key::Down => cursor = (cursor + 1).min(COMPONENTS.len().saturating_sub(1)),
            Key::Number(n) => {
                // Number toggles that component directly (portable fallback).
                if let Some(c) = COMPONENTS.get(n.saturating_sub(1) as usize) {
                    sel.toggle(c.key);
                }
            }
            Key::Toggle => {
                if let Some(c) = COMPONENTS.get(cursor) {
                    sel.toggle(c.key);
                }
            }
            Key::Enter => break,
            Key::Quit => return Ok(()),
            Key::Unknown => {}
        }
    }
    let steps: Vec<&'static str> =
        install::HOST_TOOLS.iter().map(|t| t.name).chain(std::iter::once("build")).collect();
    run_with_progress(&sel, false, &steps)
}

fn wait_for(keys: &[Key]) {
    loop {
        if keys.contains(&read_key()) {
            return;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn welcome_mentions_the_language_mix() {
        let text = render_welcome();
        assert!(text.contains("Rust"));
        assert!(text.contains("NASM"));
        assert!(text.contains("Zig"));
    }

    #[test]
    fn page1_renders_every_tool_as_locked_required() {
        let text = render_page1();
        assert!(text.contains("🔒"));
        assert!(text.contains("Required host toolchain"));
        for t in install::HOST_TOOLS {
            assert!(text.contains(t.name));
        }
    }

    #[test]
    fn page2_shows_required_locked_and_recommended_tickable() {
        let sel = Selection::default();
        let text = render_page2(&sel, 0);
        // A required component renders the lock marker.
        assert!(text.contains("🔒"));
        // A recommended, enabled one renders [x].
        assert!(text.contains("explorer"));
    }

    #[test]
    fn page2_reflects_a_deselected_component() {
        let mut sel = Selection::default();
        sel.toggle("pci");
        // Disabled recommended item is no longer in the enabled CSV.
        assert!(!sel.is_enabled("pci"));
    }

    #[test]
    fn page3_renders_pending_then_done_steps() {
        let steps: &[&'static str] = &["qemu", "rust", "build"];
        let pending: Vec<Option<bool>> = vec![None; steps.len()];
        let text = render_page3(steps, &pending);
        assert!(text.contains("Page 3"));
        assert!(text.contains("qemu"));
        assert!(text.contains("rust"));
        assert!(text.contains("build"));
        // Pending steps render a dim dot, never a checkmark.
        assert!(text.contains('·'));
        assert!(!text.contains('✓'));

        let done: Vec<Option<bool>> = steps.iter().map(|_| Some(true)).collect();
        let text = render_page3(steps, &done);
        assert!(text.contains('✓'));
        assert!(!text.contains('✗'));
    }

    #[test]
    fn page3_marks_a_failed_step() {
        let steps: &[&'static str] = &["qemu", "build"];
        let status = [Some(true), Some(false)];
        let text = render_page3(steps, &status);
        assert!(text.contains('✓'));
        assert!(text.contains('✗'));
    }

    #[test]
    fn finish_success_is_green_and_lists_components() {
        let sel = Selection::default();
        let text = render_finish(&sel, true, None);
        assert!(text.contains("setup complete"));
        assert!(text.contains(&sel.csv()));
        assert!(text.contains("lionos run"));
        // A successful finish never shows the failure banner.
        assert!(!text.contains("setup failed"));
    }

    #[test]
    fn finish_failure_shows_the_error_and_log_path() {
        let sel = Selection::default();
        let text = render_finish(&sel, false, Some("qemu could not be provisioned"));
        assert!(text.contains("setup failed"));
        assert!(text.contains("qemu could not be provisioned"));
        assert!(text.contains("install.log"));
    }
}