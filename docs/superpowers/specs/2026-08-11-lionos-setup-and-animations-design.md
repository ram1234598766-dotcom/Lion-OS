# LionOS `setup` installation manager + OS animations — Design

- **Date:** 2026-08-11
- **Status:** Approved (brainstorming complete; user directed "proceed")
- **Scope:** two subsystems — (A) a standalone interactive installer
  (`lionos setup`) and (B) richer kernel animations.
- **Build constraints:** honored as in prior months — build `kernel` then `os`
  in Kali (`wsl -d kali-linux`); host test `cargo test --target
  x86_64-unknown-linux-gnu`; deterministic `LIONOS_` boot markers grepped by CI;
  kernel hardware/`ffi::`/mmio behind `#[cfg(target_os="none")]`; pure logic
  host-tested; commit in Kali (pre-commit gitleaks) push from Windows; CRLF via
  `tr -d '\r'`; never `$VAR` in Bash-tool commands.

---

## Subsystem A — `lionos setup`: the standalone installation manager

The Rust launcher (`lionos.exe`) becomes *the* one double-clickable installer.
A new interactive `setup` subcommand is the installation manager; the existing
non-interactive `install`/`doctor`/`run`/`update` subcommands remain as the
scripted path. Inno Setup is demoted to a convenience shim (Start-menu, PATH,
double-click → `lionos setup`).

### The wizard (one TUI, dependency-free)

A small dependency-free terminal UI over the existing `install::` plumbing —
ANSI cursor/clear + raw-mode key reading, checked with arrow keys + Space,
Enter to continue. Pages:

1. **Welcome.** Banner + the OS's multilingual component list
   (Rust · NASM · C · C++17 · Zig) and a one-line "what this installs" blurb.
2. **Page 1 — Host toolchain (all 🔒 compulsory, no un-ticking).** Fixed list of
   6 required tools, each tagged with the language it compiles:
   QEMU (VM target, **hard fail**), Rust nightly + `x86_64-unknown-none`
   (Rust), nasm (NASM asm), g++/clang++ (C/C++17), Zig (Zig), mtools (FAT
   tooling). Row is display-only; the cursor passes through it.
3. **Page 2 — LionOS components.** A real picker with compulsory vs recommended:
   **compulsory** (🔒 locked): kernel core, scheduler, syscall/ring-3, IPC,
   serial. **recommended** (pre-ticked, un-tickable): editor, explorer, AI stub,
   theme, dock, virtio-blk, ATA/IDE, PCI, Graphics. Selection is stored in the
   runtime component manifest (below).
4. **Provision & build.** Writes `.lionos/config.toml`; provisions selected
   host tools through a fallback ladder; builds `kernel` + `os` → `target/bios.img`;
   streams progress; offers `[Boot in QEMU?]`.
5. **Done screen.** Image path + `lionos run` hint.

### Provisioning that does not fail on any online host

All 6 host tools are compulsory and provisioned through a **fallback ladder** so
a missing/misbehaving package manager never sinks the install:

| Tool       | Rung 1                    | Rung 2                          | Rung 3 |
|------------|---------------------------|---------------------------------|--------|
| QEMU       | winget/brew/apt/dnf/pacman| direct signed portable download  | —      |
| Rust       | rustup                    | standalone rustup-init download | —      |
| nasm/g++/zig/mtools | package manager   | direct download+sha256 verify into `~/.lionos/toolchain/<name>/bin`, staged on the build PATH | — |

Key design — **self-contained toolchain dir.** Each required tool is staged
into `~/.lionos/toolchain/bin/`, verified (already-on-PATH → `which`; downloaded
→ sha256 against a pinned hash), and that dir is prepended to PATH **for the
build only**. Package managers become an optimization, not a dependency.

**Guarantee by planning, not retry:**
1. **Probe first.** Before any write, detect which tools are usable and compute
   the full plan up front.
2. **Fail at plan-time, not mid-install.** If, pre-install, a tool's rungs are
   all impossible (no network **and** nothing cached), the *welcome screen*
   says so before the install commits — never a mid-build death.
3. **Verify after.** A second `which`/fingerprint confirms each stage.

**Honest ceiling:** offline-and-empty is the one irreducible failure; we surface
it early instead of mid-install. No network-independent bundling (the setup file
would balloon 200–400 MB across three OSes). Decision made, recorded.

### Component gating — hybrid (approved)

- **Host tools:** real gating — only selected tools provisioned on Page 1
  (here: all).
- **LionOS components:** runtime manifest — components are always compiled, but
  which ones **register/print at boot** is driven by the manifest. `setup` writes
  the selection into `.lionos/config.toml`; `build_disk` passes it to the kernel
  build via env `LIONOS_COMPONENTS=editor,explorer,…`; kernel `build.rs` embeds
  it (a generated `component_manifest.rs` `include!`); at boot
  `main.rs` registers enabled components and prints
  `LIONOS_MANIFEST components=… list=…`. Dropping a tick disables it at boot,
  does not shrink the binary.

### Files touched (Subsystem A)

- `launcher/src/main.rs` — add `Setup` subcommand + arg parsing.
- `launcher/src/setup.rs` *(new)* — the TUI (pages 1–5) + selection model.
- `launcher/src/install.rs` — refactor into reusable primitives: `find_qemu`,
  `pkg_install_argv`, `stream`, `ensure_*` already exist; add: `probe_plan()`,
  `staged_toolchain()`, `rung_ladder(tool)`, `provision(plan)`; thread a
  `ComponentSelection` through `build_disk` → env.
- `kernel/build.rs` — read `LIONOS_COMPONENTS`, emit `component_manifest.rs`.
- `kernel/src/main.rs` — consume manifest, register/print with
  `LIONOS_MANIFEST`.
- `installer/LionOS-Desktop.iss` — launch `lionos setup` on install (shim).

### Error handling (Subsystem A)

- Host-tool failure after all rungs → the only hard stop; message names the
  tool + its rung-3 remedy and never fires mid-build.
- Network/offline detected pre-install → welcome screen warning, graceful exit.
- Any provisioned tool that still isn't usable post-stage → exact remedy.
- Fatal errors are strings (`Result<_, String>`) consistent with existing code.

### Testing (Subsystem A)

- Launcher: `probe_plan` computes correct rungs for a stubbed environment;
  manifest `config.toml` serialization round-trips; `ComponentSelection`
  default/expand/required logic.
- Kernel build.rs: given a `LIONOS_COMPONENTS` value, `component_manifest.rs`
  contains exactly those + the compulsory set.
- Boot smoke: `LIONOS_MANIFEST components=… list=…` in CI's positive-boot grep.

---

## Subsystem B — OS animations

Enhance the existing `gfx::Canvas`/compositor animation beyond the current
animated gradient wallpaper (`gradient_fill(canvas, tick)`, `gfx.rs:179`). Two
pure, host-testable pieces plus a boot marker:

1. **`gfx::wallpaper`** — richer animated wallpaper: the existing vertical
   gradient gained a horizontal phase so the bands *drift* diagonally with
   `tick` (replaces the single-axis scroll). Pure math on `(w,h,tick)`.
2. **`gfx::dock_pop`** — a small ease/pop animation for the dock app bar and
   window focus: `pop(t, ease)` bounces a target's scale/offset over a short
   composition. Pure, host-tested (time → value easing, bounds safe).
3. Boot marker `LIONOS_GFX_ANIM tick=… drift=… pop=…` printed once at boot;
   add to CI positive-boot grep.

Files (Subsystem B): `kernel/src/gfx.rs`, `kernel/src/main.rs`,
`.github/workflows/ci.yml` (grep).

---

## Sequencing

Phase 1 — Subsystem A (launcher + manifest hook), host-tested, still boots.
Phase 2 — Subsystem B (animations), boots.
Phase 3 — release ritual (version bump + tag/GHCR) only if the user asks.

## Out of scope (noted, deliberately skipped)

- Bundling toolchains inside the setup exe (rejected — size across 3 OS).
- A native GUI wizard (Tauri/webview) — the dependency-free Rust TUI is chosen;
  a GUI would be a separate future effort.
- Shrinking the kernel binary by dropping compiled components (hybrid chose
  runtime manifest, not feature-gating).