# LionOS Month 3 — Real-Standards Drivers, Scheduler, Read-only FAT32

Date: 2026-08-08
Status: Approved (design)
Months 1–2 shipped at `bde69c9` (paging takeover, frame-backed heap, GDT/TSS/IST,
IDT, PIC/PIT/keyboard, driver layer). This spec is the Month-3 push.

## Scope

You are standing on a working BIOS-QEMU x86_64 kernel. Months 1–2 are done and
shipped. This month:

1. **Scheduler** — PCB, cooperative `yield`, then preemptive round-robin via the
   PIT (Month-3 W2 of the master plan). Context switch in NASM.
2. **+10 real-hardware-standard drivers** (beyond the existing 9 real drivers:
   UART serial, 8259 PIC, 8254 PIT, PS/2 keyboard, PS/2 mouse, CMOS RTC, PCI bus-0,
   VGA text, Bochs-VBE framebuffer).
3. **Read-only FAT32** over a real block device (virtio-blk backed by a host-built
   image), validated against `mtools`.
4. **New languages** join the FFI pie: **C++17** and **Zig**, both compiling
   freestanding to x86_64 ELF64 objects that drop into `liblionos_ffi.a`, beside
   the existing Rust / C / NASM / GAS.

## Explicit non-goals (boot chain)
- **Android from an SD card / phone boot is out of scope.** A consumer Android is
  ARM64 with a locked bootloader; it cannot boot this x86_64 BIOS kernel, and this
  repo will not fake that. The +10 driver set is real-hardware *standards* that
  QEMU also emulates — developable and testable today, and applicable to real
  silicon later.
- **Real-PC UEFI boot is deferred** to a future month (separate boot-chain
  milestone). This month's drivers (AHCI, NVMe, NICs, HPET, IOAPIC, VBE) are the
  precursor hardware work for it; the boot path itself stays BIOS/QEMU.

## The +10 real driver set (all QEMU-emulatable → real-worthy)
| # | Driver | Real standard | QEMU device | Bundle |
|---|--------|----------------|-------------|--------|
| 1 | `ide` | ATA-1 PIO | `-drive if=ide` | disk |
| 2 | `ahci` | SATA/AHCI | `-device ahci` | disk |
| 3 | `nvme` | NVMe identify-gate | `-device nvme` | disk |
| 4 | `e1000` | Intel 8254x NIC | default NIC | net |
| 5 | `rtl8139` | Realtek NIC | `-device rtl8139` | net |
| 6 | `uhci` | USB 1.0 host | `-device usb-uhci` | usb |
| 7 | `ehci` | USB 2.0 host | `-device usb-ehci` | usb |
| 8 | `hpet` | HPET timer | `-device hpet` | timer |
| 9 | `ioapic` | Intel IO-APIC (IRQ remap) | APIC | irq |
| 10 | `vbe` | VESA/VBE framespec | `-vga std` | gfx |

Each driver = a **pure, host-testable core** (chip-identify, register map, decode,
checksum; in Zig/C++/C, no hardware touch) + a `x86_64`-only I/O shim
(`outb/inb/writel/readl` in NASM + Rust `ffi`). Gateway + IRQ-aware drivers gate
their IRQ on `interrupts.rs`. Boot marker per driver (e.g. `LIONOS_DRV_AHCI
found=1 ctl-ver=…`) + a `…_ABSENT` variant that CI and dev host can see when the
device isn't present — never a fault.

## Scheduler
- `sched.rs`: `Pcb { state, saved_regs: [u64; N], sp, flags, … }` — full
  general-reg revert enough to resume exactly.
- Cooperative: `yield()` explicit switch between 2–3 hardcoded test tasks,
  interleaved counter output (CI marker).
- Preemptive: PIT IRQ → rr switch; 3+ tasks interleave without explicit yields.
- **Context switch in NASM** (`asm/switch.asm`, `_switch_tosw` C-ABI save/restore +
  `iretq`-style on the preemptive path), linked via existing `link_ffi`. Host side:
  pure schedule-selection logic host-tested; register save/restore verified by
  multi-switch soak (the classic snag: a single missed reg corrupts far later,
  so the soak covers it).

## Languages (the reinforcement)
- **Rust** — kernel core, scheduler, memory, parsing, driver *policy*.
- **C++17** (freestanding: `-fno-exceptions -fno-rtti -fno-threadsafe-statics`,
  a trivial new/delete over the kernel heap allocator) — FAT boot-structure parser
  + an HBA/AHCI ownership class, exercising classes/templates.
- **Zig** (`zig build-obj`, `@export` C-ABI symbols) — NIC descriptor tables +
  IP/TCP checksum + CRC, comptime-defined hardware tables. Reverse C-ABI into
  `ffi.rs` via `#[link_name]`.
- **NASM** (new) — context-switch save/restore + RTL8139/e1000 ring-desc push.
- **GAS + C** — existing layer, kept.
- Build.rs: add `g++`/`CXX` + `zig` invocations to `link_ffi` objects. CI:
  `g++-x86_64-Linux-gnu`? no — freestanding `g++ -ffreestanding` (same host cc),
  plus `zig` added to the runner. Boot smoke markers `LIONOS_CPP_…`,
  `LIONOS_ZIG_…`, `LIONOS_SWITCH …` prove each linked+called.

## FAT32 (read-only, real-disk-backed)
- `fs.rs`: block-device trait (sector read) over the real `ide`/`virtio-blk` —
  not a mock. FAT12-parsing moved to host-testable pure Rust parser (boot-sector
  validation first, like `framebuffer.rs` style) + a C++ boot-structure helper.
- Build a real FAT32 image with `mtool`, fill, verify with `mdir`.
- Kernel `ls*` + file-read; bytes must equal the host source bytes.

## Build / runs / error safety
- Bootstrap in QEMU (`lionos run`) with the accumulated test suite green
  (76+ host, 7 launcher).
- Unrecognized/unprovided device → clean `…_N/A`/absent markers, no fault.
- Parser cores fuzzable; hand-crafted-malformed tests on FAT/boot structs.
- Both new compiler/assembler invocations in `build.rs` are `TARGET==x86_64-unknown-none`
  gated (host `cargo test` stays pure, no kernel compiler contract).

## Docs / release
- `docs/ARCHITECTURE.md` §3 (M3: scheduler+drivers+FS) written to reality
  (addresses from `objdump` where it matters).
- Monthly release ritual after the month: cut `v0.4.0` (tag+changelog+GHCR last)
  with an honest "what works now" — and, in the README, an explicit note: *"runs
  in QEMU today; UEFI real-PC boot and Android are future boot-chain milestones,
  explicitly not v0.4.0."*

## Definition of done (M3 gate)
- All Months 1–2 markers still boot in one run AND the M3 markers
  (`LIONOS_SCHED…`, each of the 10 `LIONOS_DRV_*`, `LIONOS_FS_*`, `LIONOS_CPP`,
  `LIONOS_ZIG`, `LIONOS_SWITCH`) appear.
- Scheduler: 3+ tasks interleaved via preemption; host tests green.
- FAT: `ls` and `read` match `mdir`/byte-for-byte.
- All interpreter/language smoke markers present.
- Full accumulated test suite green in CI; docs updated the same day.