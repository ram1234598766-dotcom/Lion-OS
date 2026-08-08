# Track Android (arm64) — honest status

> **Snap verdict: not yet.** Month 3 shipped **Track PC** (x86_64, boots in QEMU
> today). Android/arm64 support does not produce a booting kernel yet; this page
> says exactly how far it actually is and what the real-today path is.

## Where it stands

- The kernel is x86_64-only (`x86_64-unknown-none`, BIOS-QEMU boot via the
  `bootloader` crate, `-nographic`). There is **no arm64 image** and **no
  Android device target** builds or boots.
- The driver + scheduler + FAT32 logic added in Month 3 is deliberately
  **architecture-portable at the pure-core layer** (FAT BPB parser, scheduler
  PCB ring, PCI detect helpers) so it can be reused if an arm64 bring-up ever
  happens — but none of it is wired to arm64 yet.

## Why Android is hard (locked-boot honest note)

- Real Android devices ship with **verified/KNOX-style locked bootloaders** that
  refuse to run a UEFI/BIOS image you didn't sign — so "build an Android kernel
  and boot it on hardware" is not something a hobby OS can just flash. That is
  not a gap in this repo; it's a property of the hardware.

## The real-today paths (in order of effort)

1. **x86 Android emulator preview** — the Android Studio emulator is an x86
   (QEMU-based) VM; an x86 BIOS image can in principle run there as a guest.
   Anything we'd learn there is an *x86* boot, not arm64 hardware.
2. **arm64 under QEMU** (`qemu-system-aarch64`) — future-proofing before any
   hardware: build an `aarch64-unknown-none` kernel and boot it under
   `-machine virt`. No Android userspace, but a real arm64 bring-up.
3. **Arm64 hardware / Android** — furthest; blocked on the locked-boot MitM
   above plus a full SoC driver bring-up. Not this quarter.

## Guarantee

Nothing here claims Android or arm64 boots. If this page ever says "shipped",
close it and check the CI serial log for an `arm64` boot marker — that is the
only honest proof.