# LionOS Month 5 (Graphics) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or executing-plans. Checkboxes = tracking.

**Goal:** Ship Month-5 graphics (v0.5.0): a double-buffered drawing `Canvas`, a real compositor (z-order, clipping, move/resize), and a wallpaper (static → animated) — all still booting in QEMU with the suite green. Month 4 gave us ring-3 + syscalls; Month 5 stays ring-0 framebuffer-first (the user-mode compositor is a Month-6 clean-up).

**Architecture:** extends `0c14390` (M4: syscall ABI, ring-3, IPC mailbox + shell). The kernel already owns a validated framebuffer (`framebuffer::validate`), draws via the C `fb_*` lib and `drivers/fbtext`. Month 5 wraps drawing in a safe **`Canvas`** (host-tested rect/line/pixel with bounds), introduces a **`BackBuffer`** (a heap-held pixel surface that `present`s by blitting to the real frame), then a **compositor** that orders/draws a set of `Window`s onto the back buffer with clipping.

**Tech Stack:** Rust (nightly `x86_64-unknown-none`), the C fb layer, qemu 10.2.2 (`-vga std` gives a real framebuffer; 0.11 hands its mapped virt base). Git Bash (Windows) for read/edit/push; Kali for build/commit (gitleaks).

## Global Constraints
- Build in Kali (`cd kernel && cargo build`, `cd ../os && cargo build` → `target/bios.img`); host tests `cargo test --target x86_64-unknown-linux-gnu`. Boot `qemu … -vga std -serial file:…`.
- Every boot marker starts `LIONOS_` and is deterministic; add new ones to `.github/workflows/ci.yml`.
- Hardware/`ffi::`/mmio code is `#[cfg(target_os="none")]`; pure draw/bounds logic is host-tested.
- **Heap is small (~64 KiB, bootloader-bss headroom)** — a full-screen back buffer (~1–3 MB) does **not** fit the heap. So `BackBuffer` sizes are either small test surfaces or mapped straight from the frame allocator via `paging::map_range` (that mapped region is writable). Prefer frame-allocated buffers for real screens; keep `#[test]`/demo surfaces small.
- Kernel `.bss` stays modest. `Canvas` state on the heap, not `.bss`.
- MMIO/VGA through the phys window; the framebuffer is the bootloader-mapped virt base.

### Task 1: `Canvas` + `BackBuffer` (the double-buffer foundation)
**Files:** `kernel/src/gfx.rs` (pure `Canvas`: `fill_rect`/`hline`/`pixel` with bounds; a `BackBuffer` that `present(s)` blits into a front). Register `mod gfx;` in lib.rs. 
- [ ] Step 1: `Canvas::new(buf, w, h, pitch, bpp)` + pure `set_pixel`, `fill_rect`, `clear`. Host tests: out-of-bounds x/y are clamped/rejected (never touch memory beyond pitch buffer); `fill_rect` color-bytes correct.
- [ ] Step 2: `BackBuffer` = an owned pixel plane (frame-allocated via `paging::map_range` when kernel target) + `present(&mut front)` that blits `min(w,h,pitch)` rows. Host test: blit into an equal-size front equals the back.
- [ ] Step 3: main.rs draws the `LIONOS v0.4.0` ROI and a test rectangle through `Canvas` into the real framebuffer; boot marker `LIONOS_GFX_CANVAS ok`, `LIONOS_GFX_DBLBUF present=` (bounds). CI greps them.

### Task 2: `compositor` — z-order + clipping
**Files:** `kernel/src/gfx/compositor.rs` (or `gfx.rs` + module). 
- [ ] a `Window {x,y,w,h, rgba, canvas?}`; `Composite::draw(windows: &[&Window])` renders low-z first (`z-order`), clips each to the view `Scan`, honors `move/resize` fields.
- [ ] bounds/clip logic host-tested (a window fully offscreen draws nothing; overlapping windows paint in ascending z).
- [ ] boot: composite a few fixed windows; `LIONOS_GFX_COMPOSITE nwins=…`.

### Task 3: wallpaper — static then animated
- [ ] a `WallpaperPattern` (e.g., the VGA-style 0x55/ternary gradient) fills the back; `animate(tick)` shifts rows by a PIT-count; `LIONOS_GFX_WALL fill=… anim=…`.

### Task 4: release `v0.5.0`
Reconcile versions in README (Roadmap/Changelog/feature-matrix/Docker refs), tag `v0.5.0` in Kali → push (publish.yml → GHCR) → `gh release create`. License stays All-Rights-Reserved.

---

Month 5 is fat-feature-light on syscall work but the compositor's clip/`z`
math is the "paging/takeover"-class hard part — yet it is pure and
host-testable (no risky `mov cr3`-class bugs like Month 4). The bigger risk is
graphics correctness at a given resolution — bind and print checked dims early
in the markers. Complete each task booted + CI-green before the next.