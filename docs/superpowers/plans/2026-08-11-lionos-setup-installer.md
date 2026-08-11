# `lionos setup` — Interactive Install Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `lionos.exe` into a one-binary standalone installation manager: an interactive terminal wizard (`lionos setup`) that auto-configures the host, hard-fails never on any online host, lets the user pick recommended vs compulsory LionOS components, builds the disk, and communicates the component selection to the kernel as a runtime manifest.

**Architecture:** A dependency-free terminal TUI (ANSI + raw-mode key reads) in a new `launcher/src/setup.rs`, driving the existing `install::*` plumbing refactored into reusable primitives (`probe_plan`, `rung_ladder`, `staged_toolchain`, `provision`). Page 1 (host toolchain) is all-compulsory display-only; Page 2 (LionOS components) is the real picker. Selection serializes to `.lionos/config.toml`, flows through `build_disk` to the kernel build via `LIONOS_COMPONENTS`, and the kernel embeds + prints a `LIONOS_MANIFEST` boot marker.

**Tech Stack:** Rust (launcher = host std/crates; kernel = nightly `x86_64-unknown-none`). No new launcher dependencies (dependency-free TUI — clap/hex/sha2 only, as today). Kali for build/commit; Git Bash (Windows) for read/edit/push.

## Global Constraints
- Build launcher: `cd launcher && cargo build` (host target). Kernel: `cd kernel && cargo build`; `cd ../os && cargo build` → `target/bios.img`. Host tests: `cargo test --target x86_64-unknown-linux-gnu` (kernel) / plain `cargo test` (launcher).
- Every boot marker starts `LIONOS_` and is deterministic; add new ones to `.github/workflows/ci.yml` positive-boot step.
- `#[cfg(target_os="none")]` for kernel hardware/ffi/mmio; pure logic host-tested.
- Commit in Kali (gitleaks pre-commit); push from Windows. Never `$VAR` in Bash-tool commands. CRLF: `tr -d '\r'`. `cargo` invoked with `.current_dir(root.join(cwd))` and `.env("LIONOS_COMPONENTS", …)`.
- Keep kernel `.bss` modest; MMIO through `paging::phys_offset()`.

---

### Task 1: Reusable provisioning primitives in `install.rs`

**Files:**
- Modify: `launcher/src/install.rs` (extract; keep existing `run_inner`, `ensure_qemu`, `ensure_build_tools`, `ensure_rust`, `build_disk`, `which`, `pkg_install_argv`, `stream`, `find_repo_root` intact — reads in this plan match them)
- Test: `launcher/src/install.rs` `#[cfg(test)] mod tests`

**Interfaces:**
- Consumes: existing `which(bin)->bool`, `pkg_install_argv(package)->Option<Vec<String>>`, `stream(program,args)->Result<(),String>`, `qemu::find_qemu()->Option<PathBuf>`.
- Produces: `pub struct Tool { name: &'static str, lang: &'static str, required: bool }`; `pub const HOST_TOOLS: &[Tool]` (QEMU, rust, nasm, g++, zig, mtools — all `required`); `pub enum Rung { PkgMgr, Direct }`; `pub fn probe_tool(name:&str)->bool` (already-on-path); `pub fn rung_ladder(name:&str)->Vec<Rung>`; `pub fn staged_toolchain_dir()->PathBuf` (`~/.lionos/toolchain/bin`); `pub fn provision_one(name:&str)->Result<(),String>` (walks rungs; Direct downloads into staged dir + sha256-verifies + `which(&dir)` check); `pub fn data_dir()` already exists.

- [ ] **Step 1: Write the failing tests** — `HOST_TOOLS` all `required`; `probe_tool("cargo")` true on a Rust host; `staged_toolchain_dir` ends `toolchain\bin`; `rung_ladder` for `qemu` on a `which("apt-get")` stub includes `PkgMgr`; `provision_one` for an already-present tool is `Ok`.
- [ ] **Step 2: Run to verify failures** — `cd launcher && cargo test`; expected FAIL (symbols not defined).
- [ ] **Step 3: Implement** the `Tool`/`Rung` types, `HOST_TOOLS`, `probe_tool`, `rung_ladder`, `staged_toolchain_dir`, `provision_one` (Direct rung: `curl -L <pinned url> -o <staged>` + `sha2` verify + chmod/x bit). Reuse existing `which`/`stream`/`data_dir`.
- [ ] **Step 4: Run to verify pass** — `cargo test`.
- [ ] **Step 5: Commit** in Kali: `feat(launcher): provisioning primitives (all-compulsory tool ladder + staged toolchain)`.

---

### Task 2: Component selection model + config serialization

**Files:**
- Create: `launcher/src/selection.rs`
- Modify: `launcher/src/main.rs` (`mod selection;`)
- Test: `launcher/src/selection.rs` `#[cfg(test)]`

**Interfaces:**
- Consumes: (none from Task 1 yet).
- Produces: `pub struct Component { key: &'static str, label: &'static str, required: bool, recommended: bool }`; `pub const COMPONENTS: &[Component]` (required: core,sched,syscall,ipc,servo/serial; recommended: editor,explorer,ai,theme,dock,virtio_blk,ide,pci,gfx); `pub struct Selection { pub enabled: Vec<&'static str> }`; `impl Default` = all recommended pre-ticked + all required; `pub fn toggle(&mut self, key:&str)` (ignores required); `pub fn is_required(&self,key)->bool`; `pub fn csv(&self)->String` (comma-joined); `pub fn to_toml(&self)->String`; `pub fn from_toml(s:&str)->Result<Self,String>`.

- [ ] **Step 1: Write failing tests** — default has all recommended enabled and all required; `toggle("editor")` removes it; `toggle("sched")` is a no-op (required); `csv` round-trips through `from_toml`.
- [ ] **Step 2: Run (fail)** — `cargo test`.
- [ ] **Step 3: Implement** `selection.rs`. Pure data — no env, no IO.
- [ ] **Step 4: Run (pass)** — `cargo test`.
- [ ] **Step 5: Commit** in Kali: `feat(launcher): component selection model + TOML config` .

---

### Task 3: The TUI — `launcher/src/setup.rs`

**Files:**
- Create: `launcher/src/setup.rs`
- Modify: `launcher/src/main.rs` (add `Setup` subcommand + arg: `--no-color` for CI)
- Modify: `launcher/src/install.rs` (add `run_setup(&Selection)`: writes `config.toml`, provisions host tools, builds with `LIONOS_COMPONENTS`, streams)
- Test: host `cargo test` for the pure bits (`render_page2` returns a string given a `Selection`); terminal interaction is smoke-tested locally.

**Interfaces:**
- Consumes: `selection::{Selection, COMPONENTS}`, `install::{provision_one, HOST_TOOLS, run_setup, find_repo_root}`.
- Produces: `pub fn run() -> Result<(),String>` (main entry); `cfg(windows)` uses raw console + virtual-terminal mode; `pub fn read_key() -> u8`; `pub fn render_page1() -> String`; `pub fn render_page2(&Selection) -> String`; `pub fn run_wizard(sel:&mut Selection) -> Result<(),String>`.

- [ ] **Step 1: Write failing test** for `render_page2` — given a `Selection` with `editor` disabled, output contains `[ ] editor` and a `[x]` for `explorer` and `🔒` for `sched`.
- [ ] **Step 2: Run (fail)**.
- [ ] **Step 3: Implement** the dependency-free TUI: `render_welcome`, `render_page1` (all rows `🔒 REQUIRED`), `render_page2` (arrow-key navigation over `COMPONENTS`, Space toggles via `Selection::toggle`, required locked, Enter→provision). Raw-mode key reading with `ANSI`/windows console set. Color via ANSI SGR (disabled with `--no-color`).
- [ ] **Step 4: Run (pass)** + local smoke (`LIONOS_SMOKE=1` env runs wizard non-interactively through both pages and a stub build) — prints `LIONOS_SETUP_PAGES_OK`.
- [ ] **Step 5: Commit** in Kali: `feat(launcher): lionos setup wizard (welcome + 2 pages + provisioning)`.

---

### Task 4: Wire `build_disk` → kernel manifest; boot marker

**Files:**
- Modify: `launcher/src/install.rs` — `build_disk(root, comp_csv)`: add `.env("LIONOS_COMPONENTS", comp_csv)` to both `cargo build` invocations.
- Create: `kernel/src/component_manifest.rs` (generated at build)
- Modify: `kernel/build.rs` (read `LIONOS_COMPONENTS`, write `component_manifest.rs` with `pub const ENABLED: &[&str] = &[…]; pub const CSV: &str = "…";`)
- Modify: `kernel/src/lib.rs` (`pub mod component_manifest;`), `kernel/src/main.rs` (print `LIONOS_MANIFEST components=… list=…` merging required+CSV)
- Modify: `.github/workflows/ci.yml` (grep `LIONOS_MANIFEST`)
- Test: `kernel/src/main.rs` host build compiles with a default `ENABLED` when `LIONOS_COMPONENTS` unset.

**Interfaces:**
- Consumes: `Selection::csv`.
- Produces: kernel `component_manifest::ENABLED: &[&str]`, `component_manifest::CSV: &str`.

- [ ] **Step 1: Write failing test (kernel)** — `build.rs` with `LIONOS_COMPONENTS=editor,explorer` emits `ENABLED` containing exactly those + required set; with var unset emits the required default. Host-testable by running the generator logic.
- [ ] **Step 2: Implement** `build.rs` generator (from the existing 210-line build.rs — add a `generate_manifest(env)` fn) + embed via `include!`.
- [ ] **Step 3: Implement** `main.rs` manifest print (`LIONOS_MANIFEST components=… list=…`).
- [ ] **Step 4: Build + host test** — `cd kernel && cargo test --target x86_64-unknown-linux-gnu`.
- [ ] **Step 5: Commit** in Kali: `feat(kernel): LIONOS_MANIFEST component manifest from build env export`.

---

### Task 5: Inno Setup shim + CI grep + smoke

**Files:**
- Modify: `installer/LionOS-Desktop.iss` — `[Run]` `Parameters: "setup"`; add `[Files]` stage carries new `lionos.exe`.
- Modify: `.github/workflows/ci.yml` — add positive-boot grep for `LIONOS_MANIFEST`.
- Modify: `tests/` host suite if a manifest assertion belongs there.

- [ ] **Step 1:** regenerate `installer/stage/lionos.exe` from the release build.
- [ ] **Step 2:** update `.iss` `[Run]` line + version string; recompile is skipped if ISCC unavailable (CI only).
- [ ] **Step 3:** update CI grep; run kernel host tests + launcher tests.
- [ ] **Step 4:** Commit in Kali.

---

## Release ritual (only if the user asks)
Bring README (Roadmap/feature-matrix/Docker refs) + Changelog to the next version, tag in Kali → push (publish.yml → GHCR) → `gh release create`. License stays All-Rights-Reserved.