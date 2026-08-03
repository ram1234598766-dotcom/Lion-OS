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

The old Python desktop-OS release line (v1.0.0-v2.0.7) was removed from this
repo to begin the from-scratch kernel; its history is preserved in this repo's
git history and mirrored privately for reference.

## Package (GitHub Packages / GHCR)

LionOS is published as a container package on the repo's **Packages** tab
(`ghcr.io/ram1234598766-dotcom/lion-os/lion`). The image bundles QEMU + the
bootable kernel image and runs it headless, streaming the serial output:

```sh
docker run --rm ghcr.io/ram1234598766-dotcom/lion-os/lion
# expect: LIONOS_INIT_OK
```

Published by `.github/workflows/publish.yml` (a workflow push — not a manual
`docker push` — is what links the package to the repo and makes it public).

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
cd kernel && cargo build && cargo bootimage && cd ..   # build bootable kernel image
cd launcher && cargo build && cd ..                    # build the `lionos` CLI

./launcher/target/debug/lionos run --headless           # boot; expect LIONOS_INIT_OK
./launcher/target/debug/lionos doctor                   # host toolchain check
```
