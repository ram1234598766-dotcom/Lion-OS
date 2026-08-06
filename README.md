# LionOS

[![License: MIT](https://img.shields.io/badge/license-MIT-brightgreen.svg)](LICENSE)
[![Build Status](https://img.shields.io/github/actions/workflow/status/ram1234598766-dotcom/Lion-OS/ci.yml?branch=main&label=CI)](.github/workflows/ci.yml)
[![Platform](https://img.shields.io/badge/platform-x86__64-blue.svg)](docs/ARCHITECTURE.md)
[![Language](https://img.shields.io/badge/language-Rust%2FC%2Fasm-orange.svg)](kernel/)
[![Version](https://img.shields.io/github/v/release/ram1234598766-dotcom/Lion-OS)](https://github.com/ram1234598766-dotcom/Lion-OS/releases)
[![Contributors](https://img.shields.io/github/contributors/ram1234598766-dotcom/Lion-OS)](https://github.com/ram1234598766-dotcom/Lion-OS/graphs/contributors)
[![Last Commit](https://img.shields.io/github/last-commit/ram1234598766-dotcom/Lion-OS)](https://github.com/ram1234598766-dotcom/Lion-OS/commits/main)
[![Issues](https://img.shields.io/github/issues/ram1234598766-dotcom/Lion-OS)](https://github.com/ram1234598766-dotcom/Lion-OS/issues)
[![Pull Requests](https://img.shields.io/github/issues-pr/ram1234598766-dotcom/Lion-OS)](https://github.com/ram1234598766-dotcom/Lion-OS/pulls)

> A from-scratch operating system for x86_64, written in Rust with a C and
> assembly support layer, that boots in a virtual machine with one command.

> Built week-by-week against a six-month plan. Month 1 is complete: it boots a
> real bootloader → kernel handoff inside QEMU, validates the memory map, and is
> shipped as `v0.1.0`.

---

## Table of Contents

- [About](#about)
- [Motivation](#motivation)
- [Features](#features)
- [Screenshots & Demos](#screenshots--demos)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Environment Setup](#environment-setup)
- [Installation](#installation)
- [Building](#building)
- [Running](#running)
- [Debugging](#debugging)
- [Testing](#testing)
- [Architecture Overview](#architecture-overview)
- [Memory Layout](#memory-layout)
- [Boot Process](#boot-process)
- [Kernel Design](#kernel-design)
- [Driver Model](#driver-model)
- [System Calls](#system-calls)
- [File System](#file-system)
- [Roadmap](#roadmap)
- [Changelog](#changelog)
- [Performance](#performance)
- [Known Issues](#known-issues)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)
- [API Reference](#api-reference)
- [Coding Standards](#coding-standards)
- [Resources & References](#resources--references)
- [Contributing](#contributing)
- [Security](#security)
- [Authors & Maintainers](#authors--maintainers)
- [Support](#support)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## About

### What Is This

LionOS is a real operating-system kernel and bootloader being written **from
scratch** for x86_64, primarily in Rust, with a guarded slice of freestanding
C (`kernel/c/`) and assembly (`kernel/asm/`) for low-level support. It boots
inside QEMU via the upstream `bootloader` 0.11.17 crate wrapped into a disk
image by the `os/` builder crate. It is **not** a desktop
application and **not yet** something you install on real hardware.

### Why This Project

The goal is an honest, from-scratch OS built against a detailed six-month
plan, one "Done when" criterion at a time — not a hollow demo. Working from
scratch means owning the full chain: toolchain, boot provider, kernel, and
eventually memory management, interrupts, a filesystem, user mode, and
graphics.

### Who Is This For

- Kernel/OS developers learning x86_64, Rust `no_std`, and low-level systems.
- Anyone who wants to read a clean, documented, testable freestanding kernel
  and boot it with a single command.
- Not consumers — LionOS has no user-facing OS features yet.

### What Problem It Solves

It demystifies what actually has to happen between power-on and a running
kernel: firmware → bootloader → long-mode/page-tables → validated `BootInfo`
handoff → serial output — with CI, unit tests, and fuzzing around it rather
than hoping it works.

### How It Is Different

- **Test + fuzz first.** The memory-map and framebuffer parsers are pure,
  host-testable functions (`16` unit tests) and `cargo-fuzz` targets, run with
  no QEMU session. A regression in Month 1 fails loudly instead of silently 3
  weeks later.
- **Mixed-language from day one.** A freestanding C + assembly layer
  (`kernel/c`, `kernel/asm`) links into the Rust kernel and is exercised at
  boot, so the C/asm toolchain is real — not added later as a retrofit.
- **CI boots the real thing.** CI boots the kernel headless in QEMU and greps
  the serial output (positive and negative marker tests), and the e2e job
  boots from a clean downloaded launcher artifact.

### Goals

- Boot a verified bootloader → kernel handoff inside QEMU (Month 1 — done).
- Cross-platform `lionos` launcher CLI (`run` / `doctor` / `update`).
- Kernels with memory management, interrupts, and a scheduler (Months 2–3).
- Filesystem, user mode + syscalls, graphics/windowing (Months 3–5).
- An honest six-month path to a usable early OS (Month 6, Path A or B).

### Non-Goals

- No claim of usability on real hardware yet — bare-metal boot is a planned
  future milestone, not current reality.
- No described-but-unbuilt features: the docs and this README say explicitly
  what is *actually* working.
- No password cracking, exploitation frameworks, or pen-test tooling — this is
  a defensive/educational kernel project.

---

## Motivation

### Background

Writing an OS is the lowest layer of software. Most of us never see what lives
before `main()`. LionOS replaces the abstraction with the real thing, one small
verifiable step at a time, Rust-first with C/asm where those are the cleaner
tool.

### Inspiration

The classic `blog_os`-style "write your own OS" communities, plus the
discipline of treating every subsystem as untrusted input to be validated,
unit-tested, and fuzzed.

### Learning Objectives

- Understand BIOS/UEFI → bootloader → long-mode → kernel handoff.
- Read and validate firmware-provided data structures (memory map, eventually
  the GOP framebuffer).
- Build a `no_std`/freestanding mixed Rust+C+asm freestanding binary.
- Operate real CI against a QEMU-booted kernel (not just a unit-test binary).

---

## Features

### Completed

- [x] Rust nightly toolchain + `x86_64-unknown-none` freestanding target
- [x] Non-PIE kernel linked at 1 MiB (page-aligned LOAD segments)
- [x] Repo skeleton + `gitleaks` secret-scan pre-commit hook
- [x] Kernel boots under QEMU and prints `LIONOS_INIT_OK` over serial
- [x] CI smoke test boots headless and asserts the marker (positive + negative)
- [x] `lionos` launcher CLI: `run` / `doctor` / `update`
  - [x] `run` builds the QEMU argv as a real argument vector (no shell)
  - [x] `doctor` detects QEMU and prints per-OS install help
  - [x] `update` SHA-256-verifies downloads; corrupted disks are refused
- [x] Cross-platform launcher matrix (Linux / Windows / macOS-arm64) + Linux e2e
- [x] Bootloader handoff: kernel consumes validated `BootInfo` memory map
- [x] Memory-map + framebuffer parsers (16 host unit tests)
- [x] Paging verified via gdb (`CR3` + page-table walk, identity-mapped kernel)
- [x] `cargo-fuzz` on both parsers (millions of runs, no crashes)
- [x] C + assembly integration (freestanding C utilities + CPU stubs), exercised
      at boot and asserted in CI (`[ffi]` line)
- [x] `v0.1.0` release + GHCR container image

### In Progress

- [x] Framebuffer (GOP) handoff — **shipped** (bootloader 0.11.17)
  - [x] `kernel/src/framebuffer.rs` validator (pure, tested, fuzzed)
  - [x] bootloader 0.9.35 → 0.11.17 upgrade; `LIONOS_FB_OK` at boot
  - [x] C framebuffer drawing layer (`kernel/c/fb.c`) — `LIONOS_FB_DRAW_OK`
  - [x] `core::fmt` (`writeln!`) via `Serial` — `LIONOS_FMT_OK`

### Planned

- [ ] Month 2 (in progress): IDT/PIC/timer/keyboard + heap + frame allocator done; paging-mapped heap growth + GDT/TSS next
- [ ] Month 3: drivers, scheduler, read-only FAT32 filesystem
- [ ] Month 4: syscalls, ring separation, ELF loader, minimal shell
- [ ] Month 5: graphics, compositor, wallpaper
- [ ] Month 6: Path A (shell + AI stub) or Path B (hardening)
- [ ] Bare-metal boot / installer (post-6-month stretch)

### Feature Matrix

| Feature | Status | Version | Notes |
|---------|--------|---------|-------|
| Boot to kernel + serial marker | ✅ | v0.1.0 | handoff validated |
| Bootloader memory-map handoff | ✅ | v0.1.0 | re-validated in-kernel |
| Launcher CLI (run/doctor/update) | ✅ | v0.1.0 | cross-platform |
| Parser unit tests + fuzzing | ✅ | v0.1.0 | 16 tests, no crashes |
| C + asm integration | ✅ | v0.1.0 | `[ffi]` boot diagnostic + CI |
| GHCR container image | ✅ | v0.1.0 | `ghcr.io/.../lion:v0.1.0` |
| Framebuffer (GOP) handoff | 🔧 | v0.2.0 | contract scaffolded |
| Memory mgmt / heap / interrupts | 📋 | v0.2.0 | Month 2 |
| Drivers / scheduler / FAT32 | 📋 | v0.3.0 | Month 3 |
| Syscalls / user mode / shell | 📋 | v0.4.0 | Month 4 |
| Graphics / compositor | 📋 | v0.5.0 | Month 5 |
| Shell + AI stub / hardening | 🔮 | v1.0.0 | Month 6 |

> Legend: ✅ Complete | 🔧 In Progress | 📋 Planned | 🔮 Future

---

## Screenshots & Demos

### Screenshot 1 — Headless serial boot

```
Screenshot placeholder
```

Boot is terminal-only today (`-nographic -serial stdio`); CI and the container
consume the same serial stream. Expect:

```
LIONOS_MEM_MAP regions=15 usable=2
  usable 0x0000000000277000 len=1609728
  usable 0x000000000041a000 len=129785856
LIONOS_HANDOFF_OK
[ffi] cr3=0000000000001000 cpuid=0000000000060fb1 memset=abababababababab memcpy_ok=1 vendor=AuthenticAMD
LIONOS_INIT_OK
```

### Demo

```
Demo link placeholder
```

QEMU is the only renderer today — no graphical kernel output yet (that is
Month 5). Grab the latest release and `lionos run` to see the serial boot.

---

## Project Structure

```
lion-os/
│
├── kernel/                      # Bare-metal x86_64 kernel (Rust + C + asm)
│   ├── .cargo/config.toml       # freestanding target + non-PIE link flags
│   ├── Cargo.toml              # lib+bin crate: parsers (lib) + entry (bin)
│   ├── build.rs                 # compiles C/asm -> static lib, boot-marker rebuild
│   ├── linker.ld               # 1 MiB non-PIE layout, page-aligned segments
│   ├── c/support.c              # freestanding C: memset/memcpy/memcmp
│   ├── asm/cpu.s                # GAS stubs: hlt/cli/sti/pause/read_cr3/cpuid
│   └── src/
│       ├── lib.rs               # no_std lib: the pure, testable parsers
│       ├── main.rs              # `_start` entry + boot diagnostic
│       ├── ffi.rs               # C/asm FFI bridge (safe wrappers)
│       ├── serial.rs            # minimal COM1 driver
│       ├── memory.rs            # memory-map validator (host-tested, fuzzed)
│       └── framebuffer.rs       # framebuffer descriptor validator (scaffold)
│
├── bootloader/                  # Boot provider config (upstream bootloader crate)
├── launcher/                    # Host-side `lionos` CLI (clap)
│   └── src/{main,run,doctor,update}.rs
│
├── docs/                        # Architecture / dev-setup / syscall docs
│   ├── ARCHITECTURE.md
│   ├── DEV_SETUP.md
│   └── SYSCALLS.md
│
├── fuzz/                        # cargo-fuzz crate
│   └── fuzz_targets/{fuzz_memory.rs, fuzz_framebuffer.rs}
│
├── packaging/                   # GHCR container definition
│   └── Dockerfile
│
├── tests/                       # QEMU integration-test scaffolding (M2W4+)
├── .github/workflows/           # ci.yml, fuzz.yml, publish.yml
├── Cargo.toml                  # workspace (kernel member)
├── LICENSE
└── README.md
```

### Folder Descriptions

| Folder | Description |
|--------|-------------|
| `kernel/` | Freestanding x86_64 kernel. Rust core + freestanding C (`c/`) + assembly (`asm/`). |
| `kernel/src/` | Kernel source: entry, FFI bridge, serial, memory/framebuffer validators. |
| `kernel/c/` | Freestanding C (`support.c`, `fb.c`) — memory ops, C→asm CPUID, framebuffer drawing. |
| `kernel/asm/` | GAS assembly CPU stubs (`cpu.s`) — hlt/cli/sti, cr3, cpuid, msr, port I/O, spinlock. |
| `os/` | Disk-image builder (bootloader 0.11 `BiosBoot`) → `target/bios.img`. |
| `bootloader/` | Boot-provider notes (upstream `bootloader` 0.11.17 + `bootloader_api`). |
| `launcher/` | Cross-platform `lionos` CLI: boot, doctor, update. |
| `docs/` | `ARCHITECTURE.md`, `DEV_SETUP.md`, `SYSCALLS.md`. |
| `fuzz/` | `cargo-fuzz` targets for the kernel parsers. |
| `packaging/` | GHCR Dockerfile (QEMU + kernel image, headless). |
| `tests/` | QEMU integration-test scaffolding. |
| `.github/workflows/` | CI, fuzzing, and publish pipelines. |

### Key Files

| File | Description |
|------|-------------|
| `kernel/src/main.rs` | `_start` entry point + `[ffi]` boot diagnostic. |
| `kernel/src/memory.rs` | Untrusted-input memory-map validator (defense in depth). |
| `kernel/src/ffi.rs` | Safe wrappers over the C/asm objects. |
| `kernel/linker.ld` | Non-PIE 1 MiB layout with `DISCARD` for C/native sections. |
| `kernel/build.rs` | Compiles C/asm into the kernel; forces marker-rebuild. |
| `launcher/src/main.rs` | `clap` CLI: `run` / `doctor` / `update`. |
| `.github/workflows/ci.yml` | Boot smoke tests + cross-platform launcher matrix + e2e. |
| `packaging/Dockerfile` | GHCR container packaging. |

---

## Prerequisites

### Required Tools

| Tool | Min Version | Recommended | Purpose |
|------|-------------|-------------|---------|
| Rust nightly (`rustup`) | nightly-2026-08-02 | latest nightly | Compile the kernel (`no_std`) |
| Cargo (`bootloader` 0.11.17 + `bootloader_api`) | — | pinned | Build the bootable image (`os/`) |
| `rust-src` / `llvm-tools-preview` components | — | present | Freestanding target build |
| QEMU (`qemu-system-x86_64`) | 6.x | 10.x | Boot/test the kernel |
| A C compiler + `ar` (`cc` / `gcc` / `clang`) | 11+ | 15+ | Compile `kernel/c` + `kernel/asm` |
| `gdb-multiarch` / `gdb` | 12+ | 13+ | Kernel debugging via QEMU stub |

### Optional Tools

| Tool | Version | Purpose |
|------|---------|---------|
| `cargo-fuzz` / `cargo +nightly fuzz` | nightly | Fuzz the parsers |
| `gitleaks` | 8.x | Secret scanning (pre-commit + CI) |
| `mtools` | 6.x | Build FAT32 test images (Month 3) |
| `valgrind` | 3.x | Host-side memory-safety pass on shared logic |
| Docker | 24+ | Run the GHCR container image |

### Hardware Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| Host OS | Any (Linux/macOS/Windows) | Linux with KVM |
| RAM | 1 GB | 4 GB |
| CPU | 1 core / x86_64 | 2+ cores |
| Disk | 2 GB free | 10 GB free |
| Virtualization | none (TCG fallback) | KVM (nested virt, optional) |

### Supported Host Platforms

| Platform | Status | Notes |
|----------|--------|-------|
| Linux (x86_64) | ✅ | CI `ubuntu-latest`; apt install QEMU |
| macOS Apple Silicon | ✅ | CI `macos-14`; `brew install qemu` |
| Windows | ✅ | CI `windows-latest`; `winget install QEMU` |
| macOS Intel (x64) | ⚠️ | CI `macos-13` — runner pool can queue |
| WSL2 (Linux inside Windows) | ✅ | Use the distro's gcc + QEMU; KVM needs nested-virt |

---

## Environment Setup

See `docs/DEV_SETUP.md` for the authoritative walkthrough.

### Linux (Debian/Ubuntu)

```bash
rustup toolchain install nightly-2026-08-02
rustup component add rust-src llvm-tools-preview --toolchain nightly-2026-08-02
rustup target add x86_64-unknown-none --toolchain nightly-2026-08-02
sudo apt install -y qemu-system-x86 gcc binutils
```

### macOS

```bash
brew install qemu
# + the same rustup steps as Linux
```

### Windows

```bash
winget install QEMU
# + the same rustup steps as Linux
```

### WSL2

```bash
# Inside the Linux distro, run the Linux steps above.
# For KVM, enable nested virtualization in the Windows-host BIOS/UEFI AND add
# to .wslconfig:  [wsl2]  nestedVirtualization=true
# The TCG fallback (-accel tcg) works with no special setup.
```

### Cross-Compiler Setup

The kernel's freestanding C/asm is compiled by `kernel/build.rs` using the
system C compiler (`CC`, default `cc`). The required flags are wired in
automatically:

```text
-m64 -ffreestanding -fno-builtin -fno-stack-protector -mno-red-zone
-mcmodel=kernel -fno-pie -nostdlib -nostdinc -O2
```

#### Verify Setup

```bash
cd kernel && cargo build && cd ../os && cargo build
timeout 20 qemu-system-x86_64 -accel tcg -drive format=raw,file=target/bios.img -nographic
```

Expected output:

```
LIONOS_HANDOFF_OK
[ffi] cr3=… cpuid=… memset=abababababababab memcpy_ok=1 vendor=…
LIONOS_INIT_OK
```

### Environment Variables

| Variable | Value | Description |
|----------|-------|-------------|
| `LIONOS_BOOT_MARKER` | string | Overrides the boot marker at build (CI negative test). |
| `LIONOS_CACHE_DIR` | path | Overrides the `lionos update` cache directory. |
| `CC` | compiler | C compiler used by `kernel/build.rs` (default `cc`). |
| `AR` | archiver | Archiver used by `kernel/build.rs` (default `ar`). |

### Docker Alternative

```bash
docker run --rm ghcr.io/ram1234598766-dotcom/lion-os/lion:v0.1.0
```

(Uses QEMU inside the container and streams serial output to the terminal.)

---

## Installation

You normally get LionOS in one of two ways: the `lionos` launcher CLI, or the
container image.

### Method 1 — `lionos` launcher CLI

Download the latest `lionos` binary for your OS from the
[Releases page](https://github.com/ram1234598766-dotcom/Lion-OS/releases), then:

```bash
lionos doctor     # confirms QEMU and prints install help if missing
lionos run        # boots the kernel in QEMU
```

### Method 2 — Containers (GHCR)

```bash
docker run --rm ghcr.io/ram1234598766-dotcom/lion-os/lion:v0.1.0
```

### Method 3 — From source

```bash
git clone https://github.com/ram1234598766-dotcom/Lion-OS.git
cd Lion-OS
# follow Environment Setup, then:
cd kernel && cargo build && cd ../os && cargo build && cd ..
cd launcher && cargo build
./launcher/target/debug/lionos run --headless
```

### Verify Installation

```bash
./launcher/target/debug/lionos doctor
# OK  qemu-system-x86_64 found at …
```

---

## Building

### Quick Build

```bash
cd kernel && cargo build && cd ../os && cargo build
```

Produces the bootable image at
`target/bios.img`.

### Full Build

```bash
cargo build --workspace              # kernel (freestanding target)
cd kernel && cargo test --target x86_64-unknown-linux-gnu   # host unit tests
cd ../../../launcher && cargo build  # host `lionos` CLI
cargo fuzz build                     # fuzz harnesses (in fuzz/)
```

### Build Targets

| Command | Description |
|---------|-------------|
| `cargo build` (in `kernel/`) | Build the kernel object (freestanding). |
| `cd ../os && cargo build` (in `kernel/`) | Produce the bootable `.bin` image. |
| `cargo test --target x86_64-unknown-linux-gnu` (in `kernel/`) | Run pure-parser unit tests on the host. |
| `cargo build` (in `launcher/`) | Build the `lionos` CLI. |
| `cargo fuzz run fuzz_memory` (in `fuzz/`) | Fuzz the memory-map parser. |
| `cargo fuzz run fuzz_framebuffer` (in `fuzz/`) | Fuzz the framebuffer parser. |

### Build Options / Flags

| Option | Default | Description |
|--------|---------|-------------|
| `LIONOS_BOOT_MARKER` | `LIONOS_INIT_OK` | Boot checkpoint string (CI negative test). |
| `CC` / `AR` | `cc` / `ar` | C toolchain for `kernel/build.rs`. |
| `--release` | off | Optimization profile. |
| `--target x86_64-unknown-none` | set by `kernel/.cargo/config.toml` | Freestanding target. |

### Build Configurations

#### Configuration 1 — Debug (default)

```bash
cd kernel && cargo build && cd ../os && cargo build
```

#### Configuration 2 — Boot marker override (CI negative test)

```bash
LIONOS_BOOT_MARKER=LIONOS_NEGATIVE cargo build && (cd ../os && LIONOS_BOOT_MARKER=LIONOS_NEGATIVE cargo build)
```

### Build Output

Plain ELF: `target/x86_64-unknown-none/debug/lionos-kernel`
Bootable image: `target/bios.img`

| Output File | Description |
|-------------|-------------|
| `lionos-kernel` | The freestanding kernel ELF (linked at 1 MiB, non-PIE). |
| `bios.img` | The BIOS-bootable disk image (kernel + bootloader). |

### Clean Build

```bash
cargo clean && rm -rf fuzz/target
```

---

## Running

The canonical command is `lionos run` (or the manual QEMU command below).

### Method 1 — `lionos` launcher

```bash
./launcher/target/debug/lionos run
```

#### Options

| Flag / Option | Description |
|---------------|-------------|
| `--kernel PATH` | Path to the bootable image (default `target/…/bios.img`). |
| `--headless` | No window; route serial to stdout (CI/scripts). |

### Method 2 — Manual QEMU

```bash
timeout 45 qemu-system-x86_64 -accel tcg \
  -drive format=raw,file=target/bios.img \
  -nographic
```

#### Options

| Flag / Option | Description |
|---------------|-------------|
| `-accel tcg` | Portable software emulation (no KVM required). |
| `-nographic` | Serial to stdio, no window. |
| `-no-reboot` | Stop on triple-fault (remember: `-no-reboot` + `-d int` shows the fault). |
| `-s -S` | gdb stub (see Debugging). |

### Method 3 — Container

```bash
docker run --rm ghcr.io/ram1234598766-dotcom/lion-os/lion
```

### Method 4 — `lionos update` (verified image)

```bash
./launcher/target/debug/lionos update            # fetch + SHA-256 verify
./launcher/target/debug/lionos run --kernel <verified>
```

### Running on Real Hardware

Not yet supported. A bare-metal boot attempt is a planned Month-6 Path-B
milestone; today the kernel runs only under QEMU. There is no installer.

> ⚠️ **Warning:** Do not flash any LionOS artifact to physical media expecting
> it to boot — that path is not built or tested.

> 📝 **Note:** The container and the CLI are the only supported run paths.

### Boot Options

| Option | Description |
|--------|-------------|
| Default (windowed) | `-serial stdio`; serial visible in terminal. |
| Headless | `-nographic`; serial to stdout, no window. |
| gdb | `-s -S`; wait for a debugger on `tcp:1234`. |

---

## Debugging

### Method 1 — QEMU + gdb

The kernel debug-friendly option is to pause and single-step through real
boot code.

#### Setup

```bash
# Terminal 1 — QEMU, paused, gdb stub on tcp:1234
qemu-system-x86_64 -s -S -accel tcg \
  -drive format=raw,file=target/bios.img \
  -nographic
```

```bash
# Terminal 2 — gdb
gdb target/x86_64-unknown-none/debug/lionos-kernel
(gdb) target remote localhost:1234
(gdb) b _start
(gdb) continue
```

#### Common Commands

| Command | Description |
|---------|-------------|
| `target remote localhost:1234` | Attach to the QEMU stub. |
| `b _start` | Break at the kernel entry. |
| `info registers` / `p $cr3` | Inspect CPU state / page-table root. |
| `x/16gx $cr3` | Dump P4 page table. |
| `bt` | Backtrace (when symbols present). |
| `layout asm` | Interactive disassembly. |

### Method 2 — QEMU fault log (no debugger)

```bash
# Stop on the first fault and log exceptions
qemu-system-x86_64 -accel tcg -no-reboot -d int,cpu_reset -D /tmp/q.log \
  -drive format=raw,file=target/bios.img \
  -nographic
grep -aE "check_exception|v=" /tmp/q.log
```

This is how the Month-1 `cpuid` triple-fault was diagnosed: a `#PF` writing
`CR2=…` at a known `RIP`, then `#DF`, then reset.

### Method 3 — Disassembly

```bash
objdump -d -Mintel target/x86_64-unknown-none/debug/lionos-kernel | grep -B4 -A4 "<symbol>:"
nm -n target/x86_64-unknown-none/debug/lionos-kernel | grep lion_
```

### Debug Output

```
[ffi] cr3=0000000000001000 cpuid=0000000000060fb1 memset=abababababababab memcpy_ok=1 vendor=AuthenticAMD
LIONOS_INIT_OK
```

### Debug Symbols

Debug builds retain full symbols. Point gdb at the **plain ELF**
(`target/…/debug/lionos-kernel`), not the `.bin`, for names and line info.

### Serial Console Debugging

All kernel diagnostics go over COM1 (UART at `0x3F8`). `-nographic` maps it to
stdout; `-serial file:path` captures it to a file (what CI does).

### Logging

#### Log Levels

| Level | Description |
|-------|-------------|
| Boot | `LIONOS_*` boot checkpoint lines. |
| Diagnostic | `[ffi]` hardware/bridge line. |
| Panic | `PANIC` over serial. |

#### Enabling Logs

All existing output is unconditional on serial at this stage (Month 1). A
leveled kernel logger lands around Month 2.

---

## Testing

### Running Tests

```bash
# Kernel pure-parser unit tests (host, no QEMU)
cd kernel && cargo test --target x86_64-unknown-linux-gnu

# Fuzzing
cd fuzz && cargo +nightly fuzz run fuzz_memory && cargo +nightly fuzz run fuzz_framebuffer
```

### Test Categories

| Category | Command | Description |
|----------|---------|-------------|
| Kernel unit (host) | `cargo test --target x86_64-unknown-linux-gnu` (in `kernel/`) | Parser validation (16 tests). |
| Boot smoke (CI) | qemu + grep in `.github/workflows/ci.yml` | Positive + negative markers. |
| Fuzz | `cargo fuzz run fuzz_{memory,framebuffer}` | Untrusted-input parsers. |
| QEMU integration | `tests/` (M2W4) | Planned boot-level integration suite. |

### Writing Tests

Kernel logic is kept **pure** (no I/O) so it can run on the host under the
`x86_64-unknown-linux-gnu` target. Add a `#[cfg(test)]` module in the same
file; the CI job runs them with no QEMU.

### Test Coverage

Coverage tooling is not wired yet (Month 4+). The main guardrail today is the
combination of host unit tests + boot smoke tests + fuzzing.

---

## Architecture Overview

### High Level Design

```
Host CLI (launcher) ──builds QEMU argv──▶ QEMU (BIOS/SeaBIOS)
                                              │
                                              ▼
        upstream `bootloader` crate ──reads memory map, long mode, page tables──▶ BootInfo
                                              │
                                              ▼
        kernel `_start(BootInfo)` ──validates map──▶ serial diagnostics ──▶ park
```

The plan's scope grows leftward and upward each month: memory manager,
interrupts, scheduler, drivers, filesystem, user mode, graphics.

| Component | Description | Depends On |
|-----------|-------------|------------|
| `launcher` | Host QEMU boot CLI (`run`/`doctor`/`update`) | Host tools |
| `bootloader` | Upstream `bootloader` crate: long mode, paging, `BootInfo` | QEMU/BIOS |
| `kernel(_start)` | Entry + boot diagnostics | `bootloader` |
| `serial` | COM1 driver | — |
| `memory` | Memory-map validator (pure) | — |
| `framebuffer` | FB descriptor validator (pure, scaffold) | future bootloader |
| `ffi` | C/asm bridge | `build.rs` objects |

### Layer Model

```
+---------------------------+
|    launcher (host CLI)    |   cross-platform std Rust
+---------------------------+
|    bootloader crate       |   long mode, paging, BootInfo
+---------------------------+
|    kernel (Rust core)     |   entry, serial, validators
+---------------------------+
|    kernel (C + asm)       |   mem* utilities, CPU stubs
+---------------------------+
|    hardware / QEMU        |   x86_64, COM1, (future) GOP
+---------------------------+
```

| Layer | Description |
|-------|-------------|
| Host CLI | Boot/diagnose/update from the host OS. |
| Boot strap | Bootloader crate: into long mode with paging. |
| Kernel core | Rust: validators, serial, entry. |
| Kernel support | C + asm: memcpy/memset/cpuid/read_cr3, etc. |
| Hardware | x86_64 under QEMU (TCG or KVM). |

### Privilege Levels

| Ring | Description | Components |
|------|-------------|------------|
| Ring 0 | Kernel (all current code) | kernel, this entire boot path |
| Ring 1/2 | Unused | — |
| Ring 3 | User mode | Planned — Month 4 |

---

## Memory Layout

Derived from a real boot (`objdump` + serial + gdb). Kernel is identity-mapped
at its link address; the bootloader's page-table root is `CR3 = 0x1000`.

### Physical Memory Map (reference QEMU boot)

```
0x0000000000000000  reserved/firmware
0x0000000000277000  usable (len 1 609 728)   <- the bootloader placed memory
0x000000000041a000  usable (len 129 785 856) <- main physical RAM block
…                  (15 regions total, 2 usable; validated by the kernel)
```

| Start Address | End Address | Size | Description |
|---------------|-------------|------|-------------|
| `0x0000000000100000` | — | — | Kernel link base (1 MiB) |
| `0x0000000000277000` | +1 609 728 | usable | small usable region |
| `0x000000000041a000` | +129 785 856 | usable | main usable block |

### Virtual Memory Map

Early boot is **identity-mapped** (virtual ≈ physical). Higher-half kernel
mapping is a Month-1+ paging topic still owned by the bootloader.

| Start Address | Description |
|---------------|-------------|
| `0x0000000000100000` | Kernel `.text` (identity-mapped) |
| `0x000000000010c000` | Kernel `.data` (→ physical `0x40d000`) |

### Kernel Memory Regions

| Region | Address | Description |
|--------|---------|-------------|
| `.text` | ~`0x100000` | Code (Rust + C + asm) |
| `.rodata` | after text | Constants |
| `.data` | ~`0x10c000` | Mutable data (incl. folded `.got`) |
| `.bss` | after data | Zero-initialized |

### Stack Layout

A stack is provided by the bootloader before `_start`. Kernel-owned stacks and
IST (interrupt stack tables) land in Month 2.

### Heap Management

None yet. No `#[global_allocator]` — validators use fixed-size stack buffers.
The heap allocator is a Month-2 deliverable.

---

## Boot Process

### Overview

```
Firmware (SeaBIOS) → bootloader crate → long mode + paging → `_start(BootInfo)`
                                   → validate memory map → serial diagnostics → park
```

### Stage 1 — Firmware (SeaBIOS / BIOS)

BIOS loads the disk image produced by the `os/` builder (bootloader 0.11.17
`BiosBoot`). (UEFI/OVMF is not yet in the boot path; UEFI via `UefiBoot` is a
later-month addition — the framebuffer handoff already ships on the BIOS path.)

#### Responsibilities

- Load the image, transfer to bootloader.

#### Limitations

- BIOS path only today; no UEFI, no SecureBoot, no framebuffer handoff yet.

### Stage 2 — Bootloader crate (v0.11.17)

Reads the BIOS memory map, sets up initial 4-level page tables, enters long
mode, provides a stack, and hands a structured `BootInfo` to the kernel.

#### Responsibilities

- Long-mode transition, page tables, memory map, stack.
- Call `_start` with `BootInfo *` in RDI.

### Stage 3 — Kernel `_start`

Re-validates the memory map (defense in depth), prints diagnostics, exercises
the C/asm FFI bridge, then parks the CPU.

#### Responsibilities

- Adapt + validate the memory map (untrusted input).
- Print `LIONOS_MEM_MAP`, `LIONOS_HANDOFF_OK`, `[ffi]`, `LIONOS_INIT_OK`.
- Park via the asm `hlt` stub.

### Stage 4 — Month-2+ (planned)

GDT/TSS/IDT, exceptions, memory manager, heap, interrupts.

#### Responsibilities

- CPU initialization, real memory management, interrupt handling.

### Boot Sequence Diagram

```
SeaBIOS ──▶ bootloader ──▶ long mode ──▶ _start(BootInfo)
                                           ├─ validate memory map
                                           ├─ [ffi] cr3/../memset/../vendor
                                           └─ LIONOS_INIT_OK ──▶ hlt(park)
```

---

## Kernel Design

### Overview

A small, defensively-written freestanding kernel. Rust-first; pure logic is
extracted into the lib crate so it is host-testable and fuzzable. Low-level C
and assembly cover the byte/CPU layer.

### Kernel Type

Freestanding **monolithic** kernel in spirit (one privileged binary), built as
a `lib + bin` so the pure parts are unit-testable. No user mode yet (Month 4).

### Component 1 — Serial driver (`serial.rs`)

Minimal COM1 (UART `0x3F8`) driver — no `core::fmt`, no locking yet.

#### Sub-component 1.1 — `write_hex` / `write_dec`

Raw port-based number printers (avoids a `core::fmt` triple-fault tracked in
`ARCHITECTURE.md` §1).

### Component 2 — Memory-map validator (`memory.rs`)

Treats `BootInfo.memory_map` as untrusted input and validates it.

#### Sub-component 2.1 — `validate_regions`

Rejects >64 entries, zero-length, u64 overflow, and overlapping **usable**
regions; sorts by address.

### Component 3 — Framebuffer validator (`framebuffer.rs`)

GBP/stride checks for a future GOP descriptor (scaffolded, tested, fuzzed).

### Component 4 — FFI bridge (`ffi.rs`)

Safe wrappers over the C/asm objects (`memset`, `memcpy`, `memcmp`, `hlt`,
`cli`, `sti`, `pause`, `read_cr3`, `cpuid`).

#### Sub-component 4.1 — `kernel/c/support.c`

Freestanding C: `lion_memset`, `lion_memcpy`, `lion_memcmp`.

#### Sub-component 4.2 — `kernel/asm/cpu.s`

GAS stubs: `lion_hlt/cli/sti/pause/read_cr3/cpuid`.

### Component 5 — Launcher (`launcher/`)

Host-side CLI that builds the QEMU arg vector and runs it.

### Kernel Data Structures

| Structure | Purpose | Location |
|-----------|---------|----------|
| `Region` | A validated memory region (start/len/kind) | `memory.rs` |
| `RegionKind` | `Usable` / `Reserved` / `NonUsable` | `memory.rs` |
| `MapError` | Why a map was rejected (stable code) | `memory.rs` |
| `FramebufferInfo` | FB descriptor (addr/wh/bpp/pitch) | `framebuffer.rs` |
| `FbError` | Why a descriptor was rejected | `framebuffer.rs` |

---

## Driver Model

### Overview

No driver framework yet — Month-3 territory. Today the only "driver" is the
COM1 serial block in `serial.rs` plus hardware access via the assembly/C layer.

### Driver Categories

| Category | Description | Examples |
|----------|-------------|----------|
| Serial | N/A (row) | COM1 (`serial.rs`) |
| CPU support | N/A (asm layer) | `read_cr3`, `cpuid` |
| Framebuffer | planned (Month 3/5) | validator scaffold |
| Input / storage | planned (Months 3–5) | — |

### Supported Drivers

| Driver | Status | Description |
|--------|--------|-------------|
| COM1 Serial | ✅ | Minimal, raw |
| CPU (cr3/cpuid/hlt/cli/sti) | ✅ | asm stubs |
| Framebuffer | 📋 | validator scaffold only |
| PS/2 / virtio-blk | 📋 | planned |

---

## System Calls

### Overview

**Not yet implemented** — this is the Month-4 deliverable. `docs/SYSCALLS.md`
is scaffolded to track the design as it lands.

### Adding a System Call

Defined in the Month-4 plan (calling convention, `STAR`/`LSTAR`/`SFMASK` MSRs,
`syscall`/`sysret`, entry/exit path), then each syscall is documented the same
day it is implemented.

---

## File System

### Overview

**Not yet implemented** — a read-only FAT32 filesystem is the Month-3
deliverable. The plan calls for a block-device abstraction, `mtools`-built test
images, and VALGRIND/`cargo-fuzz` validation of the parser on the host before
kernel integration.

### Supported File Systems

| File System | Status | Read | Write | Notes |
|-------------|--------|------|-------|-------|
| FAT32 | 📋 | planned | ❌ (read-only) | Month 3 |

---

## Roadmap

### Version 0.1 — Foundation *(shipped)*

**Target:** Month 1

- [x] Toolchain, repo skeleton, `gitleaks`
- [x] Kernel boots + `LIONOS_INIT_OK`, CI smoke test
- [x] `lionos` launcher (`run`/`doctor`/`update`), cross-platform builds
- [x] Bootloader handoff + paging verification
- [x] Parser unit tests (16) + fuzzing, no crashes
- [x] C + asm integration (`[ffi]`)
- [x] `v0.1.0` release + GHCR image

### Version 0.2 — Kernel core

**Target:** Month 2

- [x] IDT + PIC remap + PIT timer + PS/2 keyboard + deferred work queue (boots; `LIONOS_IRQ_FLAGS`/`LIONOS_TIMER_TICKS`/`LIONOS_IRQ_OK`)
- [x] Kernel heap: `#[global_allocator]` free-list allocator + accounting (boots; `LIONOS_HEAP_OK`, `Vec`/`Box` exercised)
- [x] Physical frame allocator over validated usable regions (pure accounting; boots `LIONOS_FRAMES total=…`, alloc/free exercised)
- [x] Page-table helpers + tests (`paging.rs`; boots `LIONOS_PML4 cr3=…`)
- [ ] Paging: build/own the kernel's page tables (bootloader 0.11 doesn't map its table frames, so in-place extension is impossible) → grow the heap from frames
- [ ] CPU init: custom GDT + TSS/IST (needs the kernel's own page tables)
- [ ] QEMU integration tests (GDT/IDT, allocator stress, keyboard)

### Version 0.3 — Scheduler, drivers, filesystem

**Target:** Month 3

- [ ] Drivers (serial+lock, framebuffer primitives, text)
- [ ] Cooperative + preemptive scheduler
- [ ] Read-only FAT32 (block abstraction, mtools images, fuzz)

### Version 0.4 — Userland foundations

**Target:** Month 4

- [ ] `syscall`/`sysret` + entry/exit path
- [ ] Ring 3 + ELF loader + first user-mode run
- [ ] IPC + minimal shell
- [ ] `SECURITY.md` + `checksec`/`ropper` audits

### Version 0.5 — Graphics

**Target:** Month 5

- [ ] Double buffering, mouse, input routing
- [ ] Compositor (z-order, clipping, move/resize)
- [ ] Wallpaper (static then animated)

### Version 1.0 — Month 6

**Target:** Month 6

- [ ] Path A: dock, theming, file explorer, editor, AI stub
- [ ] (or) Path B: deepen fuzzing, bare-metal attempt, CI matrix, docs

### Long Term Goals

- Real memory manager + interrupts (0.2)
- Scheduler + filesystem (0.3)
- User mode + syscalls (0.4)
- Graphics/compositor (0.5)
- A genuinely honest early-OS release (1.0)
- Stretch: bare-metal installer, web playground, SMP, SecureBoot, reproducibles

---

## Changelog

### [Unreleased]

#### Added

- C + assembly integration into the kernel (`c/support.c`, `asm/cpu.s`,
  `build.rs`, `src/ffi.rs`), exercised at boot and asserted in CI.
- `[ffi]` boot diagnostic (cr3/cpuid/memset/memcpy/vendor).
- **Month 2 interrupt bring-up:** 256-gate IDT (hand-rolled gates,
  `extern "x86-interrupt"` handlers, structured `LIONOS_FAULT` diagnostics),
  8259 PIC remap to vectors 0x20+, 8254 PIT timer (100 Hz), PS/2 keyboard
  IRQ, and a bounded deferred-work queue drained from the idle loop.
  Boot markers: `LIONOS_IRQ_FLAGS=…` (IF=1), `LIONOS_TIMER_TICKS=…`,
  `LIONOS_IRQ_OK`. CI asserts all three.
- **Month 2 heap:** hand-rolled first-fit free-list allocator backing
  `#[global_allocator]` (`Vec`/`Box`/`String` now work in the kernel), with
  allocation accounting; 42 host unit tests. Boot marker `LIONOS_HEAP_OK
  cap=… used=… sum=… box=…`; CI asserts the `Vec` sum + `Box` value.
- **Month 2 frame allocator:** `kernel/src/frames.rs` — pure-accounting
  physical frame allocator over the validated usable regions (free-list of
  frame runs, split/merge, `_end`-based floor so kernel/bootloader frames are
  never handed out); 49 host unit tests. Boot markers `LIONOS_FRAMES total=…`
  and `LIONOS_FRAME_ALLOC phys=…`; CI asserts both.
- **Month 2 paging foundation:** `kernel/src/paging.rs` — pure 4-level page-index
  + PTE encoding helpers (53 host tests), CR3 register read at boot
  (`LIONOS_PML4 cr3=…`). Established the constraint that bootloader 0.11 does
  not map its own page-table frames, so a writable map requires building the
  kernel's own page tables (the next increment).

#### Fixed

- `cpuid` stub destroyed the `%rdx` `out` pointer (CPUID clobbers `EDX`) —
  triple-fault; staged the base in `%r8`.

### [v0.1.0] — Month 1

#### Added

- Kernel boots via real bootloader → kernel handoff inside QEMU.
- Memory-map + framebuffer validators (16 host unit tests).
- `cargo-fuzz` targets for both parsers (millions of runs, no crashes).
- Cross-platform `lionos` launcher (`run`/`doctor`/`update`).
- CI: boot smoke (positive + negative), launcher matrix, e2e.
- `gitleaks` secret scanning.
- GHCR container image + `v0.1.0` release.

---

## Performance

Not yet benchmarked (baselines land in Month 2 memory/stress work). What we do
measure today is fuzz throughput / parser robustness:

### Benchmarks

| Benchmark | Result | Target | Notes |
|-----------|--------|--------|-------|
| `fuzz_memory` runs | ~37M, 0 crashes | no crashes | cargo-fuzz (M1W4) |
| `fuzz_framebuffer` runs | ~126M, 0 crashes | no crashes | cargo-fuzz (M1W4) |
| Host unit tests | 16 pass | all pass | `cargo test` linux target |
| Boot time (QEMU TCG) | seconds | — | serial markers appear |

### Memory Usage

| Component | Usage | Notes |
|-----------|-------|-------|
| Kernel | ~130 KB image | small freestanding kernel |
| Heap | none | no allocator yet (Month 2) |

### Optimization Notes

- Optimization is deliberately deferred — correctness, tests, and fuzzing come
  first (Months 1 behavior). Consistent with the plan.

---

## Known Issues

| # | Issue | Severity | Status | Workaround |
|---|-------|----------|--------|------------|
| 1 | Framebuffer (GOP) handoff not wired (bootloader 0.11.17 field absent) | Medium | Open | Scaffold validator; upgrade bootloader at M2/M3 |
| 2 | `core::fmt` at boot historically triple-faulted | High (historical) | Fixed | Raw port printing (`serial.rs`) |
| 3 | `macos-13` Intel CI runners can queue long | Low | Open | Intel job kept separate; consider dropping Intel |
| 4 | No heap / alloc / interrupts yet | By design | — | Planned Month 2 |

---

## Troubleshooting

### Problem 1 — QEMU "cannot use stdio by multiple character devices"

**Symptom:** QEMU refuses to start with serial.

**Cause:** `-nographic` already routes serial to stdio; adding a second
`-serial stdio` collides.

**Solution:**

```bash
qemu-system-x86_64 … -nographic        # drop the extra -serial stdio
```

### Problem 2 — Boots but nothing after "second stage"

**Symptom:** Silent hang/reset after `Booting (second stage)…`.

**Cause:** Usually a paging/segment layout issue (a misaligned LOAD segment, or
a triple-fault resetting the machine).

**Solution:** Capture the fault:

```bash
qemu-system-x86_64 -accel tcg -no-reboot -d int,cpu_reset -D /tmp/q.log … -nographic
grep -aE "check_exception|v=" /tmp/q.log
```

### Problem 3 — A new `cpuid`-style stub resets the machine

**Symptom:** Reset right after calling an asm stub.

**Cause:** The stub clobbers a register the ABI parks an argument in (CPUID
clobbers `EDX`, which holds a pointer).

**Solution:** Stage the argument into a register the instruction does **not**
clobber (e.g. `%r8`) before executing.

### Problem 4 — KVM not available in WSL2

**Symptom:** `-accel kvm` fails.

**Cause:** Nested virtualization disabled at host BIOS/UEFI or in `.wslconfig`.

**Solution:** Enable nested virtualization, or use the TCG fallback
(`-accel tcg`), which needs no setup.

### General Tips

- Keep every LOAD segment 4 KiB-aligned (the bootloader maps by page headers).
- Validate firmware data as untrusted input — do not assume it.
- Put the faulting instruction's `RIP` in `-d int` output, then
  `objdump` that address.

---

## FAQ

### General Questions

#### What is LionOS right now?

A Month-1 kernel: it boots a real bootloader → kernel handoff inside QEMU,
prints validated memory-map + a C/asm diagnostic over serial, and parks.

#### Is it a usable OS?

Not yet — no user mode, filesystem, or GUI. Those are Months 2–6.

#### Can I install it on real hardware?

No. Bare-metal boot is a planned milestone, not current reality.

### Technical Questions

#### What toolchain makes the bootable image?

The `bootloader` 0.11.17 crate (`BiosBoot::new(&kernel).create_disk_image`)
against an `x86_64-unknown-none` target with a non-PIE link at 1 MiB.

#### Why is there C and assembly in a Rust kernel?

For the handful of low-level jobs where they are the cleaner tool (memory
helpers, `cpuid`/`cr3` etc.), while Rust stays the default. The bridge is
`kernel/src/ffi.rs`.

#### How is the kernel tested without QEMU?

The parsers are pure functions, extracted into the lib crate and run as host
unit tests (and fuzzed).

### Development Questions

#### How do I add a boot marker assertion to CI?

Print it over serial in `_start`, then `grep` it in `.github/workflows/ci.yml`.

#### How do I debug a triple-fault?

`-no-reboot -d int,cpu_reset` to log the fault's `RIP`/`CR2`, then objdump that
address (see Troubleshooting).

---

## API Reference

### Kernel library (`lionos_kernel`)

`#![no_std]` lib crate exposing the pure parsers and the FFI bridge. Documented
in-source; the primary API surface is the module layout:

```
pub mod ffi;         // C/asm safe wrappers
pub mod memory;      // validate_regions, Region, RegionKind, MapError
pub mod framebuffer; // validate, FramebufferInfo, FbError
pub mod serial;      // COM1 write helpers
```

### Register-level "API" (asm)

| Function | C ABI | Purpose |
|----------|-------|---------|
| `lion_memset` | `void* (void*, int, size_t)` | fill bytes |
| `lion_memcpy` | `void* (void*, const void*, size_t)` | copy |
| `lion_memcmp` | `int (const void*, const void*, size_t)` | compare |
| `lion_hlt` | `void ()` | park CPU |
| `lion_read_cr3` | `u64 ()` | page-table root |
| `lion_cpuid` | `void (u32,u32,u32[4])` | CPUID leaf/subleaf |

### Error Codes

| Code | Name | Description |
|------|------|-------------|
| 1 | `TooManyRegions` | >64 map entries |
| 2 | `ZeroLength` | empty/reversed region |
| 3 | `EndOverflow` | frame→byte overflow |
| 4 | `Overlap` | overlapping usable regions |

---

## Coding Standards

### Language Style

#### Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Crates/modules | `snake_case` | `memory`, `framebuffer` |
| Functions | `snake_case` | `validate_regions` |
| Types | `UpperCamelCase` | `FramebufferInfo` |
| C/asm symbols | `lion_` prefix | `lion_cpuid` |
| Constants | `SCREAMING_SNAKE` | `MAX_REGIONS`, `COM1` |

#### Formatting Rules

- `rustfmt` for Rust; comment-dense modules explain "why", not "what".
- Freestanding: no `std`, no `core::fmt` in the boot path.
- Never a `sh -c` shell string for QEMU argv — real argument vectors only.

#### File Organization

Parse logic lives in modules that are pure (host-testable); I/O lives in
`main.rs`; C/asm under `kernel/c` and `kernel/asm`; bridge in `ffi.rs`.

#### Comment Style

`//!` module docs, `///` item docs, `// SAFETY:` on every `unsafe`.

### Assembly Style

- AT&T/GAS for `kernel/asm/cpu.s`.
- Preserve callee-saved regs; watch for instructions that clobber arg registers
  (e.g. `cpuid` clobbers `%rdx`).

### Documentation Standards

- Update docs the same day you build the feature (plan rule).
- Keep docs honest: never describe a planned feature as working.

### Code Review Checklist

- [ ] Any `unsafe` has a `// SAFETY:` comment.
- [ ] Any firmware data parsed as untrusted input is validated.
- [ ] The CI boot smoke test + host unit tests still pass.
- [ ] Docs updated (`ARCHITECTURE.md`, README status).
- [ ] No new dependency for something a few lines does.

---

## Resources & References

### Official Documentation

- [The Rust `async`/embedded Reference](https://doc.rust-lang.org/) — freestanding `no_std`
- [blog_os](https://os.phil-opp.com/) — classic OS-dev reference
- [QEMU docs](https://www.qemu.org/docs/master/) — machine/device options

### Books

- *Operating Systems: Design and Implementation (Minix)* — A.S. Tanenbaum
- *x86-64 and x32 ABI* (System V) — calling convention reference

### Tutorials & Articles

- [`bootloader` crate (0.11 DiskImageBuilder)](https://github.com/rust-osdev/bootloader)
- [cargo-fuzz](https://github.com/rust-fuzz/cargo-fuzz) — parser fuzzing

---

## Contributing

### How to Contribute

1. Fork and `git clone` the repo.

   ```bash
   git clone https://github.com/ram1234598766-dotcom/Lion-OS.git
   ```

2. Create a branch.

   ```bash
   git checkout -b feat/my-change
   ```

3. Build + test before pushing.

   ```bash
   cd kernel && cargo build && cargo test --target x86_64-unknown-linux-gnu
   ```

4. Run the pre-commit checks (`gitleaks` blocks leaked secrets).

5. Open a pull request.

### Branch Naming Convention

| Prefix | Usage |
|--------|-------|
| `feat/` | New feature / subsystem |
| `fix/` | Bug fix |
| `chore/` | Tooling, CI, docs |
| `docs/` | Documentation |

### Commit Message Format

Conventional-style (`type(scope): summary`). Examples:

```
feat(kernel): add freestanding C + asm support layer
fix(asm): stage cpuid out-base in r8 (CPUID clobbers rdx)
chore(ci): assert C/asm FFI output in boot smoke test
```

#### Types

| Type | Description |
|------|-------------|
| `feat` | New capability |
| `fix` | Bug fix |
| `chore` | Tooling / CI |
| `docs` | Documentation |
| `refactor` | No behavior change |

### Pull Request Guidelines

- One logical change per PR.
- CI must be green (boot smoke + tests).
- Update `docs/` and README status in the same PR.

### Pull Request Template

Fill in: What / Why / Screens-or-serial-output / Testing performed / Docs updated.

### Reporting Bugs

Include: host OS + version, QEMU version, the exact run command, the full
serial output, and what you expected vs. saw.

### Feature Requests

Include: the month-priority it serves, expected behavior, and an acceptance
criterion (a "Done when" line).

### Development Workflow

Week-based against the six-month plan in `docs/ARCHITECTURE.md`; each week's
deliverables must meet their "Done when" criterion before moving on.

### Code of Conduct

Be constructive, keep secrets out of commits, respect the security-first
posture of the project.

---

## Security

### Reporting Vulnerabilities

Open a private issue or contact the maintainers; the project is
security-first (fuzzing, validation, secret scanning) by design.

### Security Features

| Feature | Status | Description |
|---------|--------|-------------|
| Secret scanning | ✅ | `gitleaks` pre-commit + CI |
| Untrusted-input validation | ✅ | memory/framebuffer parsers reject bad input |
| Fuzzing | ✅ | both parsers fuzzed (no crashes) |
| `no_std` / no user mode | ✅ | current kernel has minimal attack surface |

### Security Considerations

- Firmware data is validated as untrusted.
- QEMU argv built without shell interpolation.
- Downloads SHA-256-verified before boot.
- Syscall permission model documented at Month 4 (`SECURITY.md`).

---

## Authors & Maintainers

### Core Team

| Name | Role | GitHub | Contact |
|------|------|--------|---------|
| Mrityunjay | Maintainer | [@ram1234598766-dotcom](https://github.com/ram1234598766-dotcom) | via GitHub |

### Contributors

| Name | Contributions | GitHub |
|------|---------------|--------|
| *You?* | File an issue or PR | — |

---

## Support

### Getting Help

- Open a [GitHub issue](https://github.com/ram1234598766-dotcom/Lion-OS/issues).
- Read `docs/DEV_SETUP.md` and `docs/ARCHITECTURE.md`.

### Communication Channels

| Channel | Link | Description |
|---------|------|-------------|
| Issues | [Issues](https://github.com/ram1234598766-dotcom/Lion-OS/issues) | Bugs + questions |
| Releases | [Releases](https://github.com/ram1234598766-dotcom/Lion-OS/releases) | Binaries + containers |

### Sponsorship

No sponsorship program at this time.

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE)
file for details.

```
MIT License
Copyright (c) 2026 Mrityunjay
```

### Third-Party Licenses

| Component | License | Link |
|-----------|---------|------|
| `bootloader` crate (+ `bootloader_api`) | MIT/Apache-2.0 | [rust-osdev/bootloader](https://github.com/rust-osdev/bootloader) |
| Rust toolchain (`rustc`) | MIT/Apache-2.0 | [rust-lang/rust](https://github.com/rust-lang/rust) |

---

## Acknowledgements

### People

- The Rust OS-dev community (`blog_os`, `redox`, `rust-osdev`) — the path this
  kernel follows.

### Projects

- `bootloader` (0.11 DiskImageBuilder) + `bootloader_api` — the boot provider.
- `cargo-fuzz` — parser fuzzing.

### Communities

- `/r/rust`, the Rust OS-dev community.

### Special Thanks

To everyone writing an OS and documenting it honestly.

---

<div align="center">

**⭐ If LionOS is interesting, give it a star ⭐**

[![GitHub stars](https://img.shields.io/github/stars/ram1234598766-dotcom/Lion-OS)](https://github.com/ram1234598766-dotcom/Lion-OS/stargazers)

*A from-scratch x86_64 OS in Rust — C and assembly where it earns its keep.*

*Month 1 done: boots, validates, fuzzes, ships.*

[Architecture](docs/ARCHITECTURE.md) · [Dev Setup](docs/DEV_SETUP.md) · [Releases](https://github.com/ram1234598766-dotcom/Lion-OS/releases)

</div>
