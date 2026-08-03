# LionOS Architecture

Work-in-progress; sections fill in as each subsystem lands. Status reflects the
**current** state of the tree, per the six-month plan.

## 1. Boot Process *(M1W1 — initial placeholder)*

**Firmware → bootloader → kernel handoff** is not yet the real chain. This week's
state, faithfully recorded:

1. **Power-on → OVMF (UEFI) firmware** boots and hands off to the boot medium.
2. **Boot provider = upstream `bootloader` crate v0.9.35** (wrapped by the
   `bootimage` 0.10.5 tool). It sets up initial page tables, enters long mode,
   provides a stack, and jumps to the kernel's `_start` entry point. This is a
   **placeholder** — our own bootloader (UEFI memory-map handoff, paging,
   long-mode entry) is built in **Month 1 Week 3** and will replace this.
3. **Kernel `_start` (COM1 serial init + halt)** — writes `LIONOS_INIT_OK` to
   COM1 (`0x3F8`), then parks the CPU. No interrupts, no heap, no user mode yet.

### Build flags that matter

The kernel uses the builtin `x86_64-unknown-none` target, but must be linked
**non-PIE at 1 MiB** or it cannot boot: the default build emits a
position-independent ELF (segments at VMA 0) that the bootloader jumps into and
immediately faults. `kernel/.cargo/config.toml` forces `ET_EXEC` via
`-C relocation-model=static` + `-C link-arg=-no-pie` + `kernel/linker.ld`.

The rustflags are scoped to `kernel/` (not the workspace root) because cargo
concatenates `build.rustflags` across config layers — a deeper file cannot clear
them, so they would otherwise leak into the std `launcher` crate.

> **Watch note (deferred):** a JSON target spec (`disable-redzone`,
> `+soft-float`) is wanted for Month 2 (interrupts) but requires
> `-Zjson-target-spec`, which `bootimage` cannot pass. Revisit with the custom
> bootloader in M1W3.
>
> **Watch note (deferred):** calling `core::fmt` (`writeln!`) from the Week-1
> stub triple-faults at boot (double fault `INT 0x08` → CPU reset). The raw
> `outb` banner path works; `core::fmt` output is revisited in Month 3 when the
> serial driver and exception handlers are built.

### Memory layout *(real addresses from `readelf`/`objdump`, debug build)*

| Section / symbol | Address (VMA) | Notes |
|------------------|---------------|-------|
| Entry point      | `0x100020`    | `_start`, top of `.text` |
| `.text`          | `0x100000`    | kernel code |
| `.rodata`        | `0x101000`    | boot marker string |
| `.eh_frame`      | `0x101020`    | — |
| `.bss`           | —             | empty in the placeholder |

Debug sections (`.debug_*`) have VMA 0 and are not loaded into memory. The
canonical load base becomes the bootloader's decision in M1W3.

## 2. Memory & CPU — *Month 2 (pending)*

## 3. Drivers & Filesystem — *Month 3 (pending)*

## 4. Userland & Syscalls — *Month 4 (pending)*

## 5. Graphics & Window Management — *Month 5 (pending)*