# LionOS

A from-scratch operating system for x86_64, built in Rust. This repository is
driven by a six-month plan (see `docs/ARCHITECTURE.md`); work proceeds week by
week and each week's deliverables must meet its "Done when" criterion.

## Status

- **Month 1, Week 1 — Toolchain, bootloader placeholder, CI smoke test** *(this week)*
  - Rust nightly + freestanding target + non-PIE 1 MiB link              — **done**
  - Repo skeleton (`/bootloader /kernel /launcher /docs /tests`)       — **done**
  - `gitleaks` secret-scanning pre-commit hook (blocks fake secrets)    — **done**
  - Kernel stub boots under QEMU and prints `LIONOS_INIT_OK` over serial — **done**
  - CI smoke test boots headless and asserts the marker                  — **done**

The old Python desktop-OS release line (v1.0.0-v2.0.7) was removed from this
repo to begin the from-scratch kernel; its history is preserved in this repo's
git history and mirrored privately for reference.

## Layout

| Path          | Purpose                                       | Active from |
|---------------|-----------------------------------------------|-------------|
| `kernel/`     | Bare-metal x86_64 kernel (freestanding)       | M1W1        |
| `bootloader/` | Custom bootloader (UEFI handoff, paging)      | M1W3        |
| `launcher/`   | Host-side CLI to run LionOS in QEMU           | M1W2        |
| `docs/`       | Architecture / dev-setup / syscall docs       | always      |
| `tests/`      | QEMU integration tests                        | M1W4        |

## Quick start

See `docs/DEV_SETUP.md` for prerequisites and one-time setup.

```sh
cargo bootimage --manifest-path kernel/Cargo.toml
qemu-system-x86_64 -drive format=raw,file=target/x86_64-unknown-none/debug/bootimage-lionos-kernel.bin -serial stdio
# expect: LIONOS_INIT_OK
```
