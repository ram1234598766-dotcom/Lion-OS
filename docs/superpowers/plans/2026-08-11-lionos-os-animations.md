# LionOS OS Animations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the kernel's framebuffer preview more "alive" without touching syscall safety: a drifting diagonal wallpaper and a dock/`Window` pop-ease animation, both pure and host-tested, with a deterministic `LIONOS_GFX_ANIM` boot marker.

**Architecture:** Extends `kernel/src/gfx.rs` (existing `Canvas`, `paint_scene`, `gradient_fill(canvas,tick)` at `gfx.rs:179`). Two pure functions replace/extend the single-axis gradient: a diagonal two-phase `wallpaper_drift(canvas, tick)`, and `dock_pop(t, ease)` returning a scale/offset by a bounded ease curve. Values stay in-bounds (clamped). Pure math is host-tested; only a one-line boot marker in `main.rs` is non-pure.

**Tech Stack:** Rust (nightly `x86_64-unknown-none`). qemu 10.2.2 `-vga std`. Kali build/commit; Git Bash (Windows) read/edit/push.

## Global Constraints
- Build `cd kernel && cargo build`; `cd ../os && cargo build` → `target/bios.img`; host tests `cargo test --target x86_64-unknown-linux-gnu`.
- Boot markers start `LIONOS_`; add `LIONOS_GFX_ANIM` to `.github/workflows/ci.yml` positive-boot grep.
- Hardware/framebuffer via the bootloader-mapped virt base; pure draw math host-tested.
- Keep kernel `.bss` modest; no heap growth in the hot frame loop.
- Commit in Kali (gitleaks); push from Windows.

---

### Task 1: Diagonal drifting wallpaper (`gfx::wallpaper_drift`)

**Files:**
- Modify: `kernel/src/gfx.rs`
- Test: `kernel/src/gfx.rs` `#[cfg(test)]`

**Interfaces:**
- Consumes: existing `Canvas::{write/read_pixel, cw(), ch()}` (as used by `gradient_fill`).
- Produces: `pub fn wallpaper_drift(canvas: &mut Canvas, tick: u32)` — the existing after-line style; color phase = `(row + (col + tick) % cw + tick) % 256`.

- [ ] **Step 1: Write failing tests** — `wallpaper_drift(a, 0)` differs from `wallpaper_drift(b, 7)` at some pixel (tick animates); a fill is bounded (no OOB write — assert the existing bounds-safe `read_pixel(0,0)` after writing a mid-size canvas holds); `wallpaper_drift` on a 200×200 canvas writes distinct rows (drift, not flat).
- [ ] **Step 2: Run (fail)** — `cd kernel && cargo test --target x86_64-unknown-linux-gnu gfx`.
- [ ] **Step 3: Implement** `wallpaper_drift` (two-phase: `h = ((row*2 + col + tick) as usize) % 256`; `write_pixel(row,col, [h, 255-h, (h*3)%256])`). Clamp via existing `Canvas` bounds.
- [ ] **Step 4: Run (pass)** + full `cargo test --target x86_64-unknown-linux-gnu`.
- [ ] **Step 5: Commit** in Kali: `feat(gfx): diagonal drifting wallpaper - wallpaper_drift(canvas, tick)`.

---

### Task 2: Dock/window pop-ease (`gfx::dock_pop`)

**Files:**
- Modify: `kernel/src/gfx.rs`
- Test: `kernel/src/gfx.rs` `#[cfg(test)]`

**Interfaces:**
- Consumes: none (pure fn on scalars).
- Produces: `pub fn ease_out_back(t: f32) -> f32` (bounded ease — starts 0, overshoots to ~1.1, settles 1); `pub fn dock_pop(t: f32, base: i32, mag: i32) -> i32` = `base + (mag * ease_out_back(t)) as i32`.

- [ ] **Step 1: Write failing tests** — `ease_out_back(0.0)==0.0`, `ease_out_back(1.0)==1.0`, `ease_out_back` is `>= 0` and `<= 1.2` for t in 0..1 (bounded); `dock_pop(1.0, 10, 5)==15`; `dock_pop(0.0, 10, 5)==10`.
- [ ] **Step 2: Run (fail)** — `cargo test gfx`.
- [ ] **Step 3: Implement** `ease_out_back(t)` = `1 + 2.70158*(t-1)^3 + 1.70158*(t-1)^2` (classic back-ease), clamp to `[0,1]`; `dock_pop` composes it.
- [ ] **Step 4: Run (pass)** + full host suite.
- [ ] **Step 5: Commit** in Kali: `feat(gfx): dock/window pop ease - ease_out_back + dock_pop`.

---

### Task 3: Boot marker + CI grep

**Files:**
- Modify: `kernel/src/main.rs` — call `gfx::wallpaper_drift(&mut canvas, tick)` (replacing single-axis in the frame loop) and print `LIONOS_GFX_ANIM tick=… drift=… pop=…` once (using `dock_pop(tick as f32 * 0.1, 0, 2)`).
- Modify: `.github/workflows/ci.yml` — add `LIONOS_GFX_ANIM` to the positive-boot grep.

- [ ] **Step 1:** wire the call + marker in `main.rs`.
- [ ] **Step 2:** add grep line in CI.
- [ ] **Step 3:** build (`cd kernel && cargo build`; `cd ../os && cargo build` → `target/bios.img`) and boot `qemu … -vga std -serial file:…`; confirm `LIONOS_GFX_ANIM` in the serial log; host suite green.
- [ ] **Step 4: Commit** in Kali: `feat(gfx): animated wallpaper drift + dock pop boot marker (LIONOS_GFX_ANIM)`.

---

## Release ritual (only if the user asks)
Version bump + tag/GHCR/release, license All-Rights-Reserved.