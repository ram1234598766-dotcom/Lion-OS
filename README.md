# LionOS

A from-scratch operating system for x86_64, built in Rust. This repository is
driven by a six-month plan (see `docs/ARCHITECTURE.md`); work proceeds week by
week and each week's deliverables must meet its "Done when" criterion.

## Status

- **Month 1, Week 1 — Toolchain, bootloader placeholder, CI smoke test**
  - Rust nightly + freestanding target + non-PIE 1 MiB link              — **done**
  - Repo skeleton (`/bootloader /kernel /launcher /docs /tests`)       — **done**
  - `gitleaks` secret-scanning pre-commit hook (blocks fake secrets)    — **done**
  - Kernel stub boots under QEMU and prints `LIONOS_INIT_OK` over serial — **done**
  - CI smoke test boots headless and asserts the marker                  — **done**
- **Month 1, Week 2 — Cross-platform launcher CLI** *(this week)*
  - `lionos run` / `doctor` / `update` (clap)                            — **done**
  - `doctor` detects QEMU and prints per-OS install help                  — **done**
  - `run --headless` boots the kernel end-to-end                          — **done**
  - `update` SHA-256-verifies downloads; corrupted ones are refused       — **done**
  - CI matrix (Linux/Windows/macOS-arm64) + Linux e2e boots via artifact   — **done**
  - macOS Intel Apple runner pending GitHub runner availability            — infra
- **Month 1, Week 3 — Bootloader handoff**
  - Kernel consumes `BootInfo` (memory map) and re-validates it              — **done**
  - Memory-map + framebuffer parsers unit-tested on the host (16 tests)      — **done**
  - Paging verified via gdb (`CR3` + page-table walk, identity-mapped kernel) — **done**
  - UEFI GOP framebuffer handoff (resolution/pixel-format)                    — **deferred**
    (bootloader 0.9.35 has no framebuffer field in `BootInfo`; contract
    scaffolded in `kernel/src/framebuffer.rs`, handoff lands with the
    bootloader 0.10/0.11 upgrade — see `docs/ARCHITECTURE.md` §1)
  - CI asserts the handoff marker + kernel unit tests                         — **done**
- **Month 1, Week 4 — Refinement** *(next)*
  - Malformed-input unit tests / `cargo-fuzz` on the parsers                  — pending
  - `gitleaks` full-history scan / `ARCHITECTURE.md` §1 with real addresses    — pending
  - Month-1 regression + `v0.1.0` release                                      — pending

The old Python desktop-OS release line (v1.0.0-v2.0.7) was removed from this
repo to begin the from-scratch kernel; its history is preserved in this repo's
git history and mirrored privately for reference.

## Package (GitHub Packages / GHCR)

LionOS is published as a container package on the repo's **Packages** tab
(`ghcr.io/ram1234598766-dotcom/lion-os/lion`). The image bundles QEMU + the
bootable kernel image and runs it headless, streaming the serial output:

```sh
docker run --rm ghcr.io/ram1234598766-dotcom/lion-os/lion
# expect: LIONOS_MEM_MAP … LIONOS_HANDOFF_OK … LIONOS_INIT_OK
```

Published by `.github/workflows/publish.yml` (a workflow push — not a manual
`docker push` — is what links the package to the repo and makes it public).

## Layout

| Path          | Purpose                                       | Active from |
|---------------|-----------------------------------------------|-------------|
| `kernel/`     | Bare-metal x86_64 kernel (freestanding; lib+bin) | M1W1      |
| `bootloader/` | Boot provider (upstream `bootloader` crate + `bootimage`) | M1W3 |
| `launcher/`   | Host-side CLI to run LionOS in QEMU           | M1W2        |
| `docs/`       | Architecture / dev-setup / syscall docs       | always      |
| `tests/`      | QEMU integration tests                        | M2W4        |

## Build & test

See `docs/DEV_SETUP.md` for prerequisites and one-time setup.

```sh
cd kernel && cargo build && cargo bootimage && cd ..   # build bootable kernel image

# Kernel unit tests (pure parsers, run on the host — no QEMU needed):
cd kernel && cargo test --target x86_64-unknown-linux-gnu && cd ..

cd launcher && cargo build && cd ..                    # build the `lionos` CLI

./launcher/target/debug/lionos run --headless           # boot; expect the handoff + LIONOS_INIT_OK
./launcher/target/debug/lionos doctor                   # host toolchain check
```
