# LionOS

[![License: All Rights Reserved](https://img.shields.io/badge/license-All%20Rights%20Reserved-lightgrey.svg)](LICENSE)
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

> **`v0.1.0` (foundation):** boots a real bootloader → kernel handoff inside
> QEMU, validating the memory map. **`v0.2.0` (kernel-core):** the kernel owns
> its CPU-core + memory primitives — interrupts (IDT/PIC/PIT/keyboard), a
> frame-backed heap, the **page-table takeover** (it builds and switches to its
> own PML4), and a custom GDT + TSS/IST with a double-fault stack.
> **`v0.3.x` (scheduler + drivers + filesystem):** a real driver layer
> (serial/framebuffer/text + keyboard/mouse/RTC/PCI/VGA/speaker + **10+ real
> standards: ATA PIO disk, AHCI/NVMe/e1000/RTL8139/UHCI/EHCI/HPET/IOAPIC/
> Bochs-VBE detect**), a cooperative → **preemptive scheduler** driven by the
> PIT, and a **read-only FAT32** filesystem over real block I/O — with C++17
> and Zig joined to the FFI language lay.
> **`v1.1.0` (install manager + animations):** a **`lionos setup`** interactive
> installation manager (auto-provisions the host toolchain, component picker),
> a runtime **component manifest**, **OS animations** (diagonal wallpaper drift
> + dock pop), and **installer packages** for Windows/macOS/Linux (`.exe`/`.pkg`/`.deb`).
>
> **Platform note:** this repo is the **x86_64 (Desktop)** line, booting under
> QEMU. The ARM64 **Android** port is a separate codebase with its own
> release line — see [`lion-os-android`](https://github.com/ram1234598766-dotcom/lion-os-android).

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

The goal is an honest, from-scratch OS, a milestone at a time, each with a
"Done when" criterion — not a hollow demo. Working from
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
  no QEMU session. A regression in v0.1 fails loudly instead of silently 3
  weeks later.
- **Mixed-language from day one.** A freestanding C + assembly layer
  (`kernel/c`, `kernel/asm`) links into the Rust kernel and is exercised at
  boot, so the C/asm toolchain is real — not added later as a retrofit.
- **CI boots the real thing.** CI boots the kernel headless in QEMU and greps
  the serial output (positive and negative marker tests), and the e2e job
  boots from a clean downloaded launcher artifact.

### Goals

- Boot a verified bootloader → kernel handoff inside QEMU (v0.1 — done).
- Cross-platform `lionos` launcher CLI (`run` / `doctor` / `update`).
- Kernels with memory management, interrupts, and a scheduler (the v0.2/v0.3 releases).
- Filesystem, user mode + syscalls, graphics/windowing (the v0.3–v0.5 releases).
- A usable early OS (v1.0, Path A).

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

**v0.2 (shipped, `v0.2.0`):**
- [x] Interrupt bring-up — 256-gate IDT, 8259 PIC remap, 8254 PIT timer,
      PS/2 keyboard, bounded deferred-work queue
- [x] Kernel heap (`#[global_allocator]`, first-fit free-list) — **frame-backed**
      (mapped from physical frames via the page tables, not a baked `.bss` array)
- [x] Physical frame allocator over the validated usable regions
- [x] **Page-table takeover (M2W3c unblock):** kernel builds its own PML4 and
      switches CR3 to it — CR3 is now the kernel's, not the bootloader's
- [x] Custom GDT + 64-bit TSS/IST with a dedicated double-fault stack
- [x] `v0.2.0` release + GHCR `lion:v0.2.0`

**v0.3 (shipped, `v0.3.0`):**
- [x] Mixed-language: **C++17 + Zig** join the FFI (`liblionos_ffi.a`), magic
      smoke markers `LIONOS_CPP`/`LIONOS_ZIG` boot-verified
- [x] **Scheduler** — cooperative yield + **PIT-driven preemptive RR** with an
      NASM context switch and an in-ring idle (`LIONOS_SCHED tasks=3 switches=…`)
- [x] Driver layer — serial+spinlock, framebuffer bitmap text, PS/2 keyboard,
      mouse IRQ12, CMOS RTC, PCI bus-0 enum, VGA text, PC speaker, face-id gate
- [x] **Disk + read-only FAT32** — ATA PIO block driver (0x1F0/0x170) +
      virtio-blk PCI detect; FAT32 BPB parser, root walk, cluster-chain read —
      **mtools-verified end-to-end** (`LIONOS_FS_OK/LS/READ`)
- [x] **Task 4 detect drivers** — AHCI, NVMe, e1000, RTL8139, UHCI, EHCI, HPET,
      IOAPIC, Bochs-VBE (each pure core host-tested + `LIONOS_DRV_*` marker;
      e1000 + I/O APIC are real `found=1` on QEMU)
- [x] `v0.3.1` release + GHCR `lion:v0.3.1`

### In Progress

- [x] Framebuffer (GOP) handoff — **shipped** (bootloader 0.11.17)
  - [x] `kernel/src/framebuffer.rs` validator (pure, tested, fuzzed)
  - [x] bootloader 0.9.35 → 0.11.17 upgrade; `LIONOS_FB_OK` at boot
  - [x] C framebuffer drawing layer (`kernel/c/fb.c`) — `LIONOS_FB_DRAW_OK`
  - [x] `core::fmt` (`writeln!`) via `Serial` — `LIONOS_FMT_OK`

### Shipped after v0.1.0

- [x] v0.5: syscalls, ring separation, ELF loader, user + IPC shell
- [x] v0.5: graphics, compositor, wallpaper
- [x] v1.0: Path A apps (dock/theme/editor/explorer/AI stub)
- [x] Install manager (`lionos install`, Rust) — provisions QEMU (hard dep) + build
  deps + toolchain and builds the desktop image, backgroundable (`--detach`)
- [ ] Bare-metal boot (a post-release stretch)

### Feature Matrix

| Feature | Status | Version | Notes |
|---------|--------|---------|-------|
| Boot to kernel + serial marker | ✅ | v0.1.0 | handoff validated |
| Bootloader memory-map handoff | ✅ | v0.1.0 | re-validated in-kernel |
| Launcher CLI (run/doctor/update) | ✅ | v0.1.0 | cross-platform |
| Parser unit tests + fuzzing | ✅ | v0.1.0 | 16 tests, no crashes |
| C + asm integration | ✅ | v0.1.0 | `[ffi]` boot diagnostic + CI |
| GHCR container image | ✅ | v1.1.0 | `ghcr.io/.../lion:v1.1.0` |
| Interrupts (IDT/PIC/PIT/keyboard) | ✅ | v0.2.0 | IRQ_FLAGS / TIMER_TICKS / IRQ_OK |
| Frame-backed heap + frame allocator | ✅ | v0.2.0 | `#[global_allocator]`, HEAP_OK / FRAMES |
| Page-table **takeover** (own PML4 + CR3) | ✅ | v0.2.0 | TAKEOVER cr3= … owned=1 |
| GDT + TSS/IST (double-fault stack) | ✅ | v0.2.0 | GDT_OK ist0=… |
| Framebuffer (GOP) handoff | 🔧 | v0.2.0 | drawing works; text/anim next |
| C++17 + Zig joined to FFI | ✅ | v0.3.0 | `LIONOS_CPP`/`LIONOS_ZIG` magics boot-verified |
| Scheduler (coop → preemptive RR) | ✅ | v0.3.0 | `LIONOS_SCHED`, NASM switch + PIT preempt |
| Container + driver layer | ✅ | v0.3.0 | kbd/mouse/RTC/PCI/VGA/speaker + face-id |
| ATA PIO disk + virtio-blk detect | ✅ | v0.3.0 | `LIONOS_DRV_IDE disks=…` |
| Read-only FAT32 (mtools-verified) | ✅ | v0.3.0 | `LIONOS_FS_OK/LS/READ`, byte-identical read |
| AHCI/NVMe/e1000/RT/ UHCI/EHCI/HPET/IOAPIC/VBE | ✅ | v0.3.0 | detect markers, e1000 + I/O APIC found on QEMU |
| Syscalls / user mode / shell | ✅ | v0.4.0 | SYSCALL_MSR / USER_CS=2b / SHELL_READ |
| Graphics / compositor | ✅ | v0.5.0 | GFX_CANVAS / COMPOSITE / WALL / FOCUS |
| Dock / theme / explorer / editor / AI stub (Path A) | ✅ | v1.0.0 | THEME/EDITOR/EXPLORER/DOCK/AI_STUB |
| **Install manager `lionos setup`** (interactive wizard) | ✅ | v1.1.0 | auto-provisions host toolchain + component picker |
| Runtime component manifest | ✅ | v1.1.0 | `LIONOS_MANIFEST components=…` |
| OS animations (wallpaper drift + dock pop) | ✅ | v1.1.0 | `LIONOS_GFX_ANIM tick=… drift=… pop=…` |
| Installer packages (.deb / .pkg / .exe) | ✅ | v1.1.0 | Windows/macOS/Linux setup files |

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
v0.5). Grab the latest release and `lionos run` to see the serial boot.

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
| `mtools` | 6.x | Build FAT32 test images (v0.3) |
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

**Easiest:** double-click `installer/Install-LionOS.cmd`, or run `lionos install`
— it installs QEMU (hard requirement) + the build deps/toolchain and builds the
desktop image, then boot it with `lionos run` (see
[Installation](#installation)).

Manual (equivalent of what the installer does):

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
docker run --rm ghcr.io/ram1234598766-dotcom/lion-os/lion:v1.1.0
```

(Uses QEMU inside the container and streams serial output to the terminal.)

---

## Installation

You get LionOS one of several ways: the **OS installer packages** (the
standalone installation manager), the `lionos` launcher CLI, or the container
image. Every path ships the same `lionos` binary.

### Method 0 — OS installer packages (Windows / macOS / Linux)

Download the installer for your OS from the
[Releases page](https://github.com/ram1234598766-dotcom/Lion-OS/releases), then
run `lionos setup` — the interactive installation manager.

| OS | Package | What it does |
|----|---------|--------------|
| **Windows** | `LionOS-Desktop-Setup-*.exe` | Inno Setup wizard → installs `lionos`, launches `lionos setup` |
| **macOS** (arm64 + x86_64) | `lionos-*.pkg` | native package → `/usr/local/bin/lionos` |
| **Linux** (Debian/Ubuntu) | `lionos_*_amd64.deb` | `dpkg`/`apt` → `/usr/bin/lionos` |

Each also ships a plain `.tar.gz` of the `lionos` binary if you prefer not to
use the native format. Every release also carries the **prebuilt bootable disk**
(`lionos-disk.bin` + `checksums.txt`) that `lionos setup --release` downloads
instead of building from source.

### Method 1 — `lionos setup` (the installation manager)

`lionos setup` is the interactive wizard that **auto-configures everything**:
it walks you through the required host toolchain (QEMU, Rust, nasm, g++, Zig,
mtools — all compulsory) and the LionOS component picker (🔒 core vs recommended
apps/drivers), then provisions the tools, builds the bootable disk image, and
offers to boot it in QEMU. It cannot fail on an online host — it probes first,
auto-recovers through a fallback ladder, and surfaces the only irreducible case
(offline with nothing cached) before committing.

**No repo? Use `--release`.** `lionos setup --release` (and `lionos install
--release`) skip the source build entirely: they provision **QEMU only**, then
download the **prebuilt** `lionos-disk.bin` from the GitHub release
(checksum-verified before use) and boot it. No checkout of the repo, no build
toolchain — just the internet. This is how the OS installer packages behave out
of the box.

```bash
lionos setup            # interactive wizard (welcome → toolchain → picker → build)
lionos setup --release  # fetch the prebuilt disk from GitHub instead (no repo/build)
lionos install          # same flow, non-interactive (defaults)
lionos install --release # prebuilt disk, non-interactive
lionos install --detach # background job; poll with `lionos doctor`
```

On Windows, double-click `installer/Install-LionOS.cmd` (it self-elevates and
invokes `lionos setup`). Then boot with `lionos run`.

### Method 2 — `lionos` launcher CLI

Download the latest `lionos` binary for your OS from the
[Releases page](https://github.com/ram1234598766-dotcom/Lion-OS/releases), then:

```bash
lionos doctor     # confirms QEMU and prints install help if missing
lionos run        # boots the kernel in QEMU
```

### Method 3 — Containers (GHCR)

```bash
docker run --rm ghcr.io/ram1234598766-dotcom/lion-os/lion:v1.1.0
```

### Method 4 — From source

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

Not yet supported. A bare-metal boot attempt is a planned v1.0 Path-B
milestone; today the kernel runs only under QEMU. To *run* LionOS on a desktop,
use the installation manager — `lionos install` (Rust) — which provisions QEMU
+ the build deps/toolchain and builds the image you boot with `lionos run` (see
[Installation](#installation)).

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

This is how the v0.1 `cpuid` triple-fault was diagnosed: a `#PF` writing
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

All existing output is unconditional on serial at this stage (v0.1). A
leveled kernel logger lands around v0.2.

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

Coverage tooling is not wired yet (v0.5+). The main guardrail today is the
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

The plan's scope grows leftward and upward across releases: memory manager,
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
| Ring 3 | User mode | Planned — v0.5 |

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

Early boot is identity-mapped by the bootloader. From the v0.2 **paging
takeover** onward the kernel owns the page tables: `paging::takeover` builds its
own PML4 (copying the bootloader's top level through the physical-memory
window) and switches CR3 to it, and `map_page`/`map_range` add mappings (e.g.
the frame-backed heap) at fresh virtual regions.

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
IST (interrupt stack tables) land in v0.2.

### Heap Management

None yet. No `#[global_allocator]` — validators use fixed-size stack buffers.
The heap allocator is a v0.2 deliverable.

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
a later addition — the framebuffer handoff already ships on the BIOS path.)

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

### Stage 4 — v0.2+ (planned)

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
a `lib + bin` so the pure parts are unit-testable. No user mode yet (v0.5).

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

A real driver layer lives in `kernel/src/drivers/` (v0.3), initialized by
`drivers::init_all()` at boot. Each driver prints a deterministic boot marker so
a silent init failure is caught by CI. Hardware access still goes through the
assembly/C layer (`ffi`).

### Driver Categories

| Category | Description | Examples |
|----------|-------------|----------|
| Serial | COM1 UART, spinlock-serialized | `serial.rs` |
| CPU support | asm layer | `read_cr3`, `cpuid`, `write_cr3` |
| Framebuffer / text | 5x7 bitmap font on the fb | `drivers/fbtext.rs` |
| Input | PS/2 keyboard + mouse | `drivers/keyboard.rs`, `drivers/mouse.rs` |
| Clock | CMOS RTC | `drivers/rtc.rs` |
| Bus | PCI config-space probe | `drivers/pci.rs` |
| Console | VGA text mode (0xB8000) | `drivers/vga.rs` |
| Audio | PC speaker (PIT ch2) | `drivers/speaker.rs` |
| Security | simulated biometric gate ("face id") | `drivers/face_id.rs` |

### Supported Drivers

| Driver | Status | Description |
|--------|--------|-------------|
| COM1 Serial (spinlock) | ✅ | W1D1 formalized |
| CPU (cr3/cpuid/hlt/cli/sti) | ✅ | asm stubs |
| Framebuffer bitmap text | ✅ | 5x7 font, `LIONOS_FB_TEXT` |
| PS/2 keyboard → ASCII | ✅ | set-1 scancode decode |
| PS/2 mouse (IRQ12) | ✅ | 3-byte packet decode |
| CMOS RTC clock | ✅ | `LIONOS_DRV_RTC` |
| PCI bus 0 enumeration | ✅ | `LIONOS_DRV_PCI` |
| VGA text mode | ✅ | `LIONOS_DRV_VGA` |
| PC speaker | ✅ | `LIONOS_DRV_SPEAKER` |
| "Face ID" (simulated) | ✅ | enroll → verify/gate, `LIONOS_DRV_FACEID` |
| Framebuffer | 📋 | validator scaffold only |
| PS/2 / virtio-blk | 📋 | planned |

---

## System Calls

### Overview

**Not yet implemented** — this is the v0.5 deliverable. `docs/SYSCALLS.md`
is scaffolded to track the design as it lands.

### Adding a System Call

Defined in the v0.5 plan (calling convention, `STAR`/`LSTAR`/`SFMASK` MSRs,
`syscall`/`sysret`, entry/exit path), then each syscall is documented the same
day it is implemented.

---

## File System

### Overview

**Not yet implemented** — a read-only FAT32 filesystem is the v0.3
deliverable. The plan calls for a block-device abstraction, `mtools`-built test
images, and VALGRIND/`cargo-fuzz` validation of the parser on the host before
kernel integration.

### Supported File Systems

| File System | Status | Read | Write | Notes |
|-------------|--------|------|-------|-------|
| FAT32 | 📋 | planned | ❌ (read-only) | v0.3 |

---

## Roadmap

### Version 0.1 — Foundation *(shipped)*


- [x] Toolchain, repo skeleton, `gitleaks`
- [x] Kernel boots + `LIONOS_INIT_OK`, CI smoke test
- [x] `lionos` launcher (`run`/`doctor`/`update`), cross-platform builds
- [x] Bootloader handoff + paging verification
- [x] Parser unit tests (16) + fuzzing, no crashes
- [x] C + asm integration (`[ffi]`)
- [x] `v0.1.0` release + GHCR image

### Version 0.2 — Kernel core


- [x] IDT + PIC remap + PIT timer + PS/2 keyboard + deferred work queue (boots; `LIONOS_IRQ_FLAGS`/`LIONOS_TIMER_TICKS`/`LIONOS_IRQ_OK`)
- [x] Kernel heap: `#[global_allocator]` free-list allocator + accounting (boots; `LIONOS_HEAP_OK`, `Vec`/`Box` exercised)
- [x] Physical frame allocator over validated usable regions (pure accounting; boots `LIONOS_FRAMES total=…`, alloc/free exercised)
- [x] Page-table helpers + tests (`paging.rs`)
- [x] **Page-table takeover** — enable `mappings.physical_memory`, use
      `physical_memory_offset` as a whole-physical-space window, build the
      kernel's own PML4, and switch CR3 to its physical address (boots
      `LIONOS_TAKEOVER cr3=… owned=1`, `LIONOS_MAP_RW … phys_ok=1`)
- [x] Heap is frame-backed — mapped from physical frames into a fresh 512 GiB
      region (`map_range`) instead of a baked `.bss` array
- [x] CPU init: custom GDT + TSS/IST — dedicated double-fault stack via IST1
      (boots `LIONOS_GDT_OK ist0=…`; ltr + double-fault gate IST1)
- [x] QEMU integration gates — the CI positive-boot step asserts the GDT/TSS
      (GDT_OK), allocator stress (HEAP_OK/FRAMES), keyboard (KBD_ARMED), paging,
      drivers, graphics and ring-3 markers every run; a separate in-QEMU suite
      is folded into that boot path

### Version 0.3 — Scheduler, drivers, filesystem *(shipped)*


- [x] Driver layer (serial+lock, framebuffer primitives/text) + extras
      (keyboard/mouse/RTC/PCI/VGA/speaker/face-id)
- [x] C++17 + Zig joined to the FFI (`LIONOS_CPP`/`LIONOS_ZIG` magics)
- [x] Cooperative + preemptive scheduler (PIT-driven round-robin, NASM switch)
- [x] Read-only FAT32 over real block I/O (ATA PIO + virtio-blk detect;
      mtools image, byte-identical read)
- [x] Task-4 detect set: AHCI/NVMe/e1000/RTL8139/UHCI/EHCI/HPET/IOAPIC/VBE
- [x] GHCR `lion:v0.3.1` tagged release

### Version 0.4 — Userland foundations


- [x] `syscall`/`sysret` + entry/exit path — `STAR`/`LSTAR`/`SFMASK` + `EFER.SCE`,
      `LIONOS_SYSCALL_MSR`, `LIONOS_USER_CS=…2b` (ring-3 → kernel → ring-3)
- [x] Ring 3 + user mode — `iretq` descent; the user program is now a **real
      ELF loaded by `elf.rs`** (`user/` crate, fixed U/S tables, entry map +
      NX stack) — `LIONOS_USER_CS=…2b`, `SHELL_READ/WROTE`, `USER_CALLS=6`
- [x] IPC + minimal shell — a kernel `Mailbox` (`ipc.rs`) + `SYS_RECV`/`SYS_SEND`;
      the ring-3 shell `recv`s a seeded message and `send`s an ack
      (`LIONOS_SHELL_READ n=4 head=…LiOS…`, `LIONOS_SHELL_WROTE n=3`); user→kernel
      data passing via `SYS_PUTS` bounds-checked `copy_from_user` (stac/clac under SMAP).
- [x] `SECURITY.md` + `checksec` audit (see `docs/SECURITY.md`; hardening
      follow-ups tracked there)

### Version 0.5 — Graphics *(shipped)*


- [x] Double buffering — safe `gfx::Canvas` + `BackBuffer`/`present`
      (`LIONOS_GFX_CANVAS ok`, `LIONOS_GFX_DBLBUF present=`)
- [x] Compositor — `Window` + `paint_scene` (painter's algorithm z-order with
      clipping; windows are moved/resized by editing their fields);
      `LIONOS_GFX_COMPOSITE nwins=…`
- [x] Input routing — `gfx::focus(windows, x, y)` returns the top-most window
      (the existing PS/2 mouse driver feeds the cursor); `LIONOS_GFX_FOCUS win=…`
- [x] Wallpaper — `gfx::gradient_fill(canvas, tick)` vertical gradient, animated
      by advancing `tick`; `LIONOS_GFX_WALL ok`

### Version 1.0 — Apps (Path A) *(shipped)*


- [x] Path A **apps layer** — simulated AI stub + theme (palette `recolor`),
      text editor (`TextBuffer`), file explorer (FAT count / `NO_DISK`), and a
      dock app bar (theming/editor/explorer/ai)
- [ ] (or) Path B: deepen fuzzing, bare-metal attempt, CI matrix, docs

### Version 1.1 — Install manager + animations *(shipped)*


- [x] **`lionos setup`** — interactive installation manager (welcome + compulsory
      host toolchain + component picker), auto-provisions + builds
- [x] Runtime **component manifest** (`LIONOS_MANIFEST`) from the picker selection
- [x] **OS animations** — diagonal wallpaper drift + dock pop-ease
      (`LIONOS_GFX_ANIM`)
- [x] **Installer packages** for all desktop OSes — Windows `.exe`, macOS `.pkg`,
      Linux `.deb` (`.tar.gz` fallbacks), built by `release.yml` on tag push

### Long Term Goals

- Real memory manager + interrupts (0.2)
- Scheduler + filesystem (0.3)
- User mode + syscalls (0.4)
- Graphics/compositor (0.5)
- A genuinely honest early-OS release (1.0)
- Stretch: bare-metal installer, web playground, SMP, SecureBoot, reproducibles

---

## Changelog

### [v1.1.0] — install manager + animations + packaging

#### Added

- **`lionos setup` — interactive installation manager** (`launcher/src/setup.rs`,
  dependency-free ANSI TUI). A one-binary wizard: welcome screen (the
  multilingual Rust/C/C++/Zig/NASM stack), **Page 1** — the required host
  toolchain (QEMU, Rust, nasm, g++, Zig, mtools — all **compulsory**, each
  tagged with the language it compiles), and **Page 2** — the LionOS component
  picker (🔒 compulsory core vs recommended apps/drivers, toggled with arrow
  keys + Space). On continue it persists `.lionos/config.toml`, auto-provisions
  the toolchain through a fallback ladder (package manager → verified staged
  download into `~/.lionos/toolchain/bin`), builds the disk image, and offers to
  boot. **Never fails on an online host** — probe-first, auto-recover through
  every rung; the one irreducible case (offline + nothing cached) is surfaced on
  the welcome screen instead of mid-build.
- **Runtime component manifest** — `lionos setup`'s component choice reaches
  the kernel: `build_disk` exports `LIONOS_COMPONENTS` → `kernel/build.rs`
  generates a `component_manifest.rs` (merged with the compulsory core) → boot
  prints `LIONOS_MANIFEST components=…`. Dropping a component disables it at
  boot (hybrid gating; the binary is not shrunk).
- **OS animations** (`kernel/src/gfx.rs`) — `wallpaper_drift(canvas, tick)`
  drifts the wallpaper diagonally, and `ease_out_back`/`dock_pop` add a bounded
  overshoot pop for the dock/window focus, both driven off the PIT tick
  (`LIONOS_GFX_ANIM tick=… drift=… pop=…`).
- **Installer packages for every desktop OS** — a `release.yml` workflow builds
  `.deb` (Linux), `.pkg` (macOS arm64 + x86_64), and the Windows **Inno Setup
  wizard** `.exe` on a `v*` tag push and attaches them to the GitHub Release.
  `packaging/deb/build.sh` and `packaging/pkg/build.sh` are the format builders;
  every package ships the `lionos` launcher (and therefore `lionos setup`).
- **Prebuilt-disk install (`lionos setup --release`)** — `release.yml` also
  builds and attaches the bootable `lionos-disk.bin` + `checksums.txt`; the
  install manager provisions QEMU only and downloads the verified prebuilt disk
  from the GitHub release, so LionOS installs without a repo checkout or build
  toolchain (curl-based https download added to `update.rs`).

#### Changed

- Inno Setup now launches `lionos setup` (the interactive install manager)
  instead of a read-only `doctor` after install.
- Feature matrix, Docker refs, and roadmap bumped to `v1.1.0`.

#### Retained from post-v1.0.0 hardening (no longer "Unreleased")

- **ELF loader** — the ring-3 user program is now a **real compiled ELF**
  (`user/` crate) embedded and loaded by `kernel/src/elf.rs` + `user.rs`:
  parses `PT_LOAD` segments, maps them as user pages (exec code / NX stack)
  into a fresh U/S table region, and descends to the ELF entry. Replaces the
  hand-encoded byte stub. Boot markers unchanged (`LIONOS_USER_CS=…2b`, `SHELL_READ/WROTE`,
  `USER_CALLS=6`). `user/linker.ld` links at a relative base; the loader offsets
  by a runtime free region so the user tables are U/S at every level.
- **NX on user data pages** — `paging::map_user_data` sets the NX leaf bit on
  the ring-3 stack; boot marker `LIONOS_SEC_CAPS nx=1`.
- **SYS_PUTS (user→kernel copy)** — the user program puts `"Hello!"` on its
  ring-3 stack and the kernel bounds-checks `copy_from_user` against the loaded
  user VA range (`LIONOS_SYS_PUTS ok=1 str="Hello!"`).
- **SMEP (CPUID-gated)** — enabled when the CPU supports it (`.. smep=0|1`),
  fixing the earlier CR4 `#GP` stall on QEMU's default CPU; SMAP stays deferred
  until `copy_from_user` gets `stac`/`clac` (see `docs/SECURITY.md`).

### [v1.0.0] — apps (Path A)

#### Added

- **Simulated AI assistant** (`kernel/src/ai.rs`) — honest, no-ML canned
  reply engine (case-insensitive keyword match, allocation-free); exercised at
  boot with `LIONOS_AI_STUB reply="LionOS AI ready"`.
- **Path-A apps layer** — **theme** (`theme.rs` palette + `recolor`),
  **editor** (`editor.rs` `TextBuffer` insert/backspace), **explorer**
  (`explorer.rs` `dir_lines`, reports the FAT mount count / `NO_DISK`), and a
  **dock** app bar (`dock.rs`) — `LIONOS_THEME`/`LIONOS_EDITOR`/
  `LIONOS_EXPLORER`/`LIONOS_DOCK` markers.

### [v0.5.0] — userland + graphics

#### Added

- **Ring-3 + syscall bring-up** — the kernel descends to ring 3 (`iretq` to a
  `USER_CODE|3`/`USER_DATA|3` frame) and the user process round-trips through
  the `syscall`/`sysret` fast path (`STAR`/`LSTAR`/`SFMASK` + `EFER.SCE`).
  Boot markers: `LIONOS_SYSCALL_MSR`, `LIONOS_USER_DROP`,
  `LIONOS_USER_CS=000000000000002b` (proves CPL3), `LIONOS_USER_CALLS=6`.
- **User maps** — `paging::map_user_page` (U/S on the leaf *and* the upper
  page-table levels, per the Intel user-page rule) + ring-3 segments in the GDT
  (`USER_CODE` 0x28 / `USER_DATA` 0x30) + a TSS `RSP0` kernel stack for
  future ring-3 IRQs.
- **IPC mailbox + shell** — a bounded kernel `Mailbox` (`ipc.rs`) behind
  `SYS_RECV`/`SYS_SEND`; the ring-3 shell `recv`s a seeded message and `send`s
  an ack (`LIONOS_SHELL_READ`/`LIONOS_SHELL_WROTE`).
- **v0.5 graphics foundation** — a safe, bounds-checked `gfx::Canvas`
  (host-tested `set_pixel`/`fill_rect`/`clear`/`blit`) + a `BackBuffer` that
  `present`s onto the front (`LIONOS_GFX_CANVAS ok`,
  `LIONOS_GFX_DBLBUF present=6912`).
- **v0.5 compositor + input + wallpaper** — `gfx::Window` + `paint_scene`
  (painter z-order with clipping), `gfx::focus` (top-most window at a cursor,
  routing), and an animated `gfx::gradient_fill(canvas, tick)` wallpaper
  (`LIONOS_GFX_COMPOSITE nwins=2`, `LIONOS_GFX_FOCUS win=1`, `LIONOS_GFX_WALL ok`).
- **`SECURITY.md`** — threat + permission model, and the first
  `checksec`/`readelf` audit of the kernel ELF (NX on, partial RELRO, no
  canary/PIE, 605 debug symbols).

#### Pending
- SMAP (needs `stac`/`clac` around `copy_from_user`) + a kernel canary —
  hardening only, tracked in `docs/SECURITY.md`.

### [v0.3.1] — scheduler + drivers follow-ups

#### Added

- **virtio-blk real virtqueue** — modern virtio-pci: capability parse,
  `VIRTIO_F_VERSION_1` negotiate, split etc-ring over 4 frames + `read_sector`
  submit/poll; read-only FAT32 mounts and reads over a real virtio disk
  (`LIONOS_FS_VIRTIO_OK/LS/READ`).
- **FAT LFN + subdirectories** — `DirEntry.long_name`/`is_dir`, LFN-chain
  reconstruction (`String::from_utf16_lossy`), and `fs::read_path/ls_path`
  descent into `/`-paths (case-insensitive long-or-short match).
- **Real device registers** — `drivers/mmio.rs` + `pci::bar_addr`; the Task-4
  drivers now read genuine AHCI/NVMe/e1000/RTL8139/UHCI/EHCI/HPET/IOAPIC/VBE
  registers (IOAPIC `irqs=24 raw=0x00170020` on QEMU).
- **Scheduler fix** — task idle must busy-`pause()`-pump (not `hlt`) so the
  deferred-switch round-robin keeps circulating under the `-O1` used to fit the
  larger kernel image (was stalling after the first switch; now
  `LIONOS_SCHED tasks=3 switches=4`).
- **CI toolchain** — Zig 0.14 + g++ added to every job that builds the kernel
  (`kernel-boot`, `publish`, `launcher e2e`), fixing the post-C++/Zig gap.

### [v0.3.0] — scheduler, drivers, filesystem

#### Added

- **Driver layer** (`kernel/src/drivers/`), beyond the plan's required serial +
  framebuffer + text trio:
  - `spinlock.rs` — minimal test-and-set lock (backed by an atomic swap);
    `serial.rs` formalized with it (W1D1: no interleaved output).
  - `drivers/fbtext.rs` + `font5x7.rs` — 5x7 bitmap-font text on the
    framebuffer (`LIONOS_FB_TEXT`), W1D3.
  - `drivers/keyboard.rs` — PS/2 scancode set-1 → ASCII decoder (Shift-aware).
  - `drivers/mouse.rs` — PS/2 mouse (IRQ12) 3-byte packet decode.
  - `drivers/rtc.rs` — CMOS real-time clock (`LIONOS_DRV_RTC`).
  - `drivers/pci.rs` — PCI bus-0 config-space enumeration (`LIONOS_DRV_PCI`).
  - `drivers/vga.rs` — VGA text-mode console at 0xB8000 (via the physical
    window — identity-mapping low memory isn't available post-takeover).
  - `drivers/speaker.rs` — PC speaker (PIT channel 2) beep.
  - `drivers/face_id.rs` — a **simulated** biometric identity gate ("face id"):
    no camera/ML on QEMU, so it exercises the real driver boundary + access
    policy (enroll → verify/gate), clearly labeled a mock (`LIONOS_DRV_FACEID`).
- All driver inits print deterministic markers that CI greps; 76 host unit
  tests (was 57).
- **C++17 + Zig language lay:** `kernel/cpp/lionos_cpp.cpp` +
  `kernel/zig/lionos_zig.zig` compile into `liblionos_ffi.a` (build.rs adds
  `g++` and `zig build-obj` invocations, kernel-target only). Boot magics
  `LIONOS_CPP magic=c0ffee0c` and `LIONOS_ZIG magic=…` / `table=…` prove both
  objects linked and ran.
- **Scheduler (`kernel/src/sched.rs` + `asm/switch.asm`):** PCB ring → index
  based idle; cooperative `yield` plus **PIT-preemptive round-robin** using an
  NASM callee-saved context switch; task stacks heap-allocated (frame-backed).
  Boots `LIONOS_SCHED tasks=3 switches=… rot=…` (3 tasks interleave on one
  closure across 100k rotations — the preemption proof).
- **Disk + read-only FAT32:** `drivers/ide.rs` — ATA-1 PIO block driver
  (`probe_all` both channels, LBA-28 `read_sector`, pure geometry host-tested);
  `drivers/virtio_blk.rs` — PCI detect shim. `kernel/src/fs.rs` — FAT32 BPB
  parser, root dir walk, cluster-chain `read`, `Fs{mount,ls,find,read}`.
  Fixed the FAT32 dir-entry cluster layout (hi word @20 | lo word @26 — not a
  little-endian u32 @20). **mtools-verified end-to-end:** boots a real FAT32
  image on the secondary ATA channel, `LIONOS_FS_OK disk=1`,
  `LIONOS_FS_LS count=1 [HELLO.TXT]`, `LIONOS_FS_READ … bytes=44 head=6c6c6548`
  (byte-identical to the host file).
- **Task 4 detect drivers:** `ahci`, `nvme`, `e1000`, `rtl8139`, `uhci`, `ehci`,
  `hpet`, `ioapic`, `vbe` — each a pure host-tested core + a `#[cfg(none)]`
  probe printing `LIONOS_DRV_* found=1 …` / `ABSENT` (never faults). On QEMU
  the e1000 NIC and I/O APIC are real `found=1`; the rest report absent.
- Host suite now **105 tests** (was 76); CI greps the new ATA/FS, Task-4,
  scheduler, C++ and Zig markers and boots a FAT32 second drive.

### [v0.2.0] — kernel core

#### Added

- C + assembly integration into the kernel (`c/support.c`, `asm/cpu.s`,
  `build.rs`, `src/ffi.rs`), exercised at boot and asserted in CI.
- `[ffi]` boot diagnostic (cr3/cpuid/memset/memcpy/vendor).
- **v0.1 NASM + C string language lay** (`asm/port_io.asm`,
  `cpu_utils.asm`, `c/string_utils.c`): the master-plan's NASM port-I/O/CPU-utils
  routines + C string helpers, coexisting with the GAS layer. Markers
  `LIONOS_NASM …`, `LIONOS_C_STR`, `LIONOS_C_MEMMOVE`. CI runner moved off the
  retired `macos-13` to `macos-15-intel`.
- **v0.2 interrupt bring-up:** 256-gate IDT (hand-rolled gates,
  `extern "x86-interrupt"` handlers, structured `LIONOS_FAULT` diagnostics),
  8259 PIC remap to vectors 0x20+, 8254 PIT timer (100 Hz), PS/2 keyboard
  IRQ, and a bounded deferred-work queue drained from the idle loop.
  Boot markers: `LIONOS_IRQ_FLAGS=…` (IF=1), `LIONOS_TIMER_TICKS=…`,
  `LIONOS_IRQ_OK`. CI asserts all three.
- **v0.2 heap (frame-backed):** hand-rolled first-fit free-list allocator
  backing `#[global_allocator]` (`Vec`/`Box`/`String`). The arena is now drawn
  from physical frames mapped into a fresh 512 GiB region (`paging::map_range`)
  instead of a baked `.bss` array — the concrete payoff of owning the page
  tables. Boot marker `LIONOS_HEAP_OK cap=… used=… sum=… box=…`.
- **v0.2 frame allocator:** `kernel/src/frames.rs` — pure-accounting
  physical frame allocator over the validated usable regions (free-list of
  frame runs, split/merge, `_end`-based floor so kernel/bootloader frames are
  never handed out). Boot markers `LIONOS_FRAMES total=…` and
  `LIONOS_FRAME_ALLOC phys=…`.
- **v0.2 paging foundation + TAKEOVER (the M2W3c unblock):**
  `kernel/src/paging.rs` — 4-level page-index/PTE helpers, then
  `takeover()`: the kernel enables `mappings.physical_memory` in its
  `BootloaderConfig`, uses `BootInfo.physical_memory_offset` as a window over
  the whole physical address space, builds its **own** PML4, and switches CR3 to
  its physical address. `map_page` / `translate` / `map_range` map frames on
  demand. Boot markers `LIONOS_TAKEOVER cr3=… owned=1` and
  `LIONOS_MAP_RW back=deadbeefcafef00d phys_ok=1` (map → write → read → translate).
- **v0.2 GDT + TSS/IST:** `gdt::setup()` installs a custom GDT + 64-bit TSS
  with `IST0` = a dedicated double-fault stack (frames mapped writable via
  paging); `ltr` loads the TSS and the IDT double-fault gate (0x08) selects
  IST1 — a fault inside a fault handler now runs on its own stack. Boot marker
  `LIONOS_GDT_OK ist0=…`.

#### Fixed

- `cpuid` stub destroyed the `%rdx` `out` pointer (CPUID clobbers `EDX`) —
  triple-fault; staged the base in `%r8`.
- The boilerplate's `cpuid_query` had the same EDX-clobber bug — not copied
  verbatim; parked `&eax`/`&ebx` in `r10`/`r11` before `cpuid`.

### [v0.1.0] — foundation

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

Not yet benchmarked (baselines land in v0.2 memory/stress work). What we do
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
| Heap | none | no allocator yet (v0.2) |

### Optimization Notes

- Optimization is deliberately deferred — correctness, tests, and fuzzing come
  first (v0.1 behavior). Consistent with the plan.

---

## Known Issues

| # | Issue | Severity | Status | Workaround |
|---|-------|----------|--------|------------|
| 1 | Framebuffer (GOP) handoff not wired (bootloader 0.11.17 field absent) | Medium | Open | Scaffold validator; upgrade bootloader at M2/M3 |
| 2 | `core::fmt` at boot historically triple-faulted | High (historical) | Fixed | Raw port printing (`serial.rs`) |
| 3 | `macos-13` Intel CI runners can queue long | Low | Open | Intel job kept separate; consider dropping Intel |
| 4 | No heap / alloc / interrupts yet | By design | — | Planned v0.2 |

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

A v0.1 kernel: it boots a real bootloader → kernel handoff inside QEMU,
prints validated memory-map + a C/asm diagnostic over serial, and parks.

#### Is it a usable OS?

Not yet — no user mode, filesystem, or GUI. Those are the v0.2–v1.0 releases.

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

Include: the release it serves, expected behavior, and an acceptance
criterion (a "Done when" line).

### Development Workflow

Week-based against the the original roadmap in `docs/ARCHITECTURE.md`; each week's
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
- Syscall permission model documented at v0.5 (`SECURITY.md`).

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

This project is **All Rights Reserved** — proprietary and confidential. No
permission is granted to copy, reuse, modify, distribute, sublicense, or sell
any part of this work. See the [LICENSE](LICENSE) file for the full terms.

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

*v0.1 done: boots, validates, fuzzes, ships.*

[Architecture](docs/ARCHITECTURE.md) · [Dev Setup](docs/DEV_SETUP.md) · [Releases](https://github.com/ram1234598766-dotcom/Lion-OS/releases)

</div>
