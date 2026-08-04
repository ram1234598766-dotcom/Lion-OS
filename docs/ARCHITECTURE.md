# LionOS Architecture

Work-in-progress; sections fill in as each subsystem lands. Status reflects the
**current** state of the tree, per the six-month plan.

## 1. Boot Process *(M1W3 — real handoff)*

**Firmware → bootloader → kernel handoff**, faithfully recorded as it stands:

1. **Power-on → SeaBIOS (BIOS)** boots the disk image. (UEFI/OVMF is not yet in
   the boot path — the `bootimage`-built image is BIOS. UEFI boot returns with
   the bootloader upgrade that also brings the GOP framebuffer handoff.)
2. **Boot provider = upstream `bootloader` crate v0.9.35**, built into a disk
   image by the `bootimage` 0.10.5 tool. It reads the BIOS memory map, sets up
   initial 4-level page tables, enters long mode, provides a stack, and hands a
   structured `BootInfo` to the kernel's `_start` (pointer in RDI).
3. **Kernel `_start(boot_info)`** re-validates the memory map (defense in depth,
   `kernel/src/memory.rs`), prints a summary over COM1
   (`LIONOS_MEM_MAP regions=N usable=M`, then `LIONOS_HANDOFF_OK`), preserves
   the Week-1 checkpoint marker `LIONOS_INIT_OK`, and parks the CPU. No
   interrupts, no heap, no user mode yet (Month 2).

### The handoff data

`BootInfo` (bootloader crate, default features) carries a `MemoryMap` of
4 KiB frame-number regions with a `MemoryRegionType` per region. `_start`
adapts each region into a `(start_frame, end_frame, kind)` triple and feeds it
to `lionos_kernel::memory::validate_regions`, which rejects malformed input
(zero-length, u64 overflow, >64 entries, overlapping **usable** regions) and
returns sorted byte-address regions. The same pure functions are unit-tested on
the host and fuzzed with `cargo-fuzz`.

The bootloader's page tables are the **boot provider's** for now (not ours):
verified by attaching `gdb` to QEMU's `-s` stub and walking P4→PDPT→PD→PT. In
the reference QEMU run: `CR3=0x1000`, and `0x100000` (virtual) → `0x401000`
(physical, present), `.data` at `0x10c000` → `0x40d000` (present+writable).
The kernel is identity-mapped at its link address; the bootloader places it at
~`0x401000` physical and maps it 1:1.

### Build flags that matter

The kernel uses the builtin `x86_64-unknown-none` target, but must be linked
**non-PIE at 1 MiB** or it cannot boot: the default build emits a
position-independent ELF (segments at VMA 0) that the bootloader jumps into and
immediately faults. `kernel/.cargo/config.toml` forces `ET_EXEC` via
`-C relocation-model=static` + `-C link-arg=-no-pie` + `kernel/linker.ld`.

The rustflags are scoped to the freestanding **target**
(`[target.x86_64-unknown-none]`, not `[build]`) so host-side unit tests
(`cargo test --target x86_64-unknown-linux-gnu`) link without the kernel linker
script. They still cannot leak into the std `launcher` crate because the file
lives under `kernel/`.

> **Watch note (M1W3, fixed):** with `-no-pie` and more complex kernel code, the
> linker emitted a `.got`/`.data.rel.ro` RELRO segment at a **non-4KiB-aligned
> VMA** (`0x10b6e8`). The bootloader maps kernels by page-aligned program
> headers, so that segment made it mis-map pages and the kernel never entered
> `_start` (silent hang after "Booting (second stage)…"). Fixed by folding
> `.got`/`.got.plt`/`.data.rel.ro` into `.data` in `kernel/linker.ld`, so every
> LOAD segment is 4KiB-aligned. Symptom to remember: any silent
> "boots to second stage then nothing" is a load-segment mis-map — check
> `readelf -lW` for non-aligned LOAD VMAs first.
>
> **Watch note (M1W3, deferred):** the UEFI GOP **framebuffer** descriptor
> (address/resolution/pixel format) is **not yet handed off** — bootloader
> 0.9.35's `BootInfo` has no framebuffer field. The kernel-side contract is
> scaffolded (`kernel/src/framebuffer.rs`, pure + tested) and the handoff
> itself is planned via the bootloader 0.10/0.11 upgrade. Until then the
> graphics framebuffer is not usable from the kernel.
>
> **Watch note (M1W1, deferred):** a JSON target spec (`disable-redzone`,
> `+soft-float`) is wanted for Month 2 (interrupts) but requires
> `-Zjson-target-spec`, which `bootimage` cannot pass. Revisit with a
> bootloader upgrade.
>
> **Watch note (M1W1, deferred):** calling `core::fmt` (`writeln!`) from the
> early stub triple-faulted at boot (double fault `INT 0x08` → CPU reset). The
> raw `outb` printer path (`serial::write_hex`/`write_dec`/`write_str`) works
> and is used today; `core::fmt` output returns with the Month-3 serial driver.

### Memory layout *(real addresses from `readelf`/`objdump`, debug build)*

| Section / symbol | Address (VMA) | Notes |
|------------------|---------------|-------|
| Entry point      | `0x1008e0`    | `_start` |
| `.text`          | `0x100000`    | kernel code (`lib` + bin) |
| `.rodata`        | `0x109000`    | marker strings, `HEX` table |
| `.eh_frame_hdr`  | `0x10b6b0`    | — |
| `.data`          | `0x10c000`    | `.got`/`.data.rel.ro` folded in (M1W3 fix) |
| `.bss`           | —             | empty in the placeholder |

Debug sections (`.debug_*`) have VMA 0 and are not loaded into memory. The
canonical load base is the bootloader's decision; it currently places the
kernel at ~`0x401000` physical and identity-maps it.

## 2. Memory & CPU — *Month 2 (pending)*

## 3. Drivers & Filesystem — *Month 3 (pending)*

## 4. Userland & Syscalls — *Month 4 (pending)*

## 5. Graphics & Window Management — *Month 5 (pending)*
