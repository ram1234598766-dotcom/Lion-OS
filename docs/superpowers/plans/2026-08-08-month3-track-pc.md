# LionOS Month 3 (Track PC) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Month-3 Track PC: a scheduler (cooperative → preemptive), a +10 real-hardware-standard driver set, read-only FAT32 over a real block device, and C++/Zig joined to the FFI — all booting in QEMU with the accumulated suite green.

**Architecture:** Extends the working BIOS-QEMU x86_64 kernel at `bde69c9`. New pure logic lives host-testable in `lib.rs`; hardware I/O is NASM-shimmed and `#[cfg(target_os="none")]`-gated. Build.rs grows g++ and zig invocations into `liblionos_ffi.a`. Scheduler switches in NASM; FAT mounts a real disk via the IDE/virtio block shim.

**Tech Stack:** Rust (nightly, `x86_64-unknown-none`), NASM + GAS, C, **C++17 (freestanding)**, **Zig (build-obj)**, qemu 10.2.2, mtools. Git Bash (Windows) for read/edit/push; Kali for build/commit (gitleaks pre-commit) — see Global Constraints.

## Global Constraints
- **Build env:** kernel built in **Kali** (`wsl -d kali-linux -- bash -lc 'cd ~/Projects/lion-os && …'`); build `cd kernel && cargo build` then `cd ../os && cargo build` → `target/bios.img`. `cargo test --target x86_64-unknown-linux-gnu` is the pure host-test command.
- **FFI object rules:** all C/C++/GAS/NASM/Zig objects link into `liblionos_ffi.a` only when `TARGET==x86_64-unknown-none` (build.rs guard). Host test build never compiles them.
- **Markers:** every printed boot marker line starts `LIONOS_` and is deterministic for a fixed VM; CI greps them. Device-present drivers print `…_FOUND`; absent print `…_ABSENT` (never fault).
- **`#[cfg(target_os="none")]`:** any code that touches `ffi::`/port-I/O/IRQ is gated non-none; pure logic is always host-testable.
- **Commit in Kali, push from Windows** (`cd //wsl.localhost/…/lion-os && gh auth setup-git && git push`). Never `$VAR` in Bash-tool commands (expands empty). CRLF: `tr -d '\r' < f > f.lf && mv`, verify byte-delta.
- **No Android work in this plan:** Track Android (arm64) is a separate future spec; its only artifact here is the optional x86-Android emulator preview harness, labeled mock.

---

### Task 1: Bootstrap Zig + add C++17/Zig to the FFI build

**Files:**
- Modify: `kernel/build.rs` (add zig compile + more `rerun-if-changed`s)
- Create: `kernel/cpp/lionos_cpp.cpp` (a first freestanding C++ symbol)
- Create: `kernel/zig/lionos_zig.zig` (a first `@export` Zig symbol + comptime table)
- Modify: `kernel/src/ffi.rs` (wrappers for the two new symbols)
- Modify: `kernel/src/main.rs` (boot smoke markers)

**Interfaces:**
- Consumes: existing `compile()`/`link_ffi()` helpers in `build.rs`.
- Produces: extern fns `lionos_cpp_magic() -> u32` (`#[link_name="lionos_cpp_magic"]`) and `lionos_zig_magic() -> u32` (`#[link_name="lionos_zig_magic"]`); boot markers `LIONOS_CPP magic=…` and `LIONOS_ZIG magic=…`.

- [ ] **Step 1: install Zig in Kali**
```
wsl -d kali-linux -- bash -lc 'cd /tmp && curl -sL -o zig.tar.xz https://ziglang.org/download/0.13.0/zig-linux-x86_64-0.13.0.tar.xz && tar xf zig.tar.xz && sudo mv zig-linux-x86_64-0.13.0 /opt/zig && sudo ln -sf /opt/zig/zig /usr/local/bin/zig'
wsl -d kali-linux -- bash -lc 'zig version'   # expect 0.13.0
```
Expected: prints `0.13.0`.

- [ ] **Step 2: write the C++17 source**
```cpp
// kernel/cpp/lionos_cpp.cpp — one freestanding symbol the kernel links in.
extern "C" unsigned int lionos_cpp_magic(void) { return 0xC0FFEE0C; }
```
- [ ] **Step 3: write the Zig source**
```zig
// kernel/zig/lionos_zig.zig — comptime + a C-ABI export.
comptime { _ = @import("std").zig.version_string; }
export fn lionos_zig_magic() callconv(.C) u32 {
    return 0x00002616; // "zig" on a phone keypad, deterministic
}
```
- [ ] **Step 4: extend `build.rs`** — in `main()`, after the NASM loop, compile C++ + Zig and push into `objects`, plus `rerun-if-changed` for both sources:
```rust
// C++ — freestanding, no exceptions/rtti (kernel heap allocator is Rust-owned,
// so C++ does NOT get a global new; see Task 2's policy split).
let cpp_obj = out.join("cpp_lionos.o");
compile_cxx(&cc, "cpp/lionos_cpp.cpp", &cpp_obj);   // g++ via cc
objects.push(cpp_obj);

// Zig — build-obj emits a bare C-ABI object.
let zig = std::env::var("ZIG").unwrap_or_else(|_| "zig".to_string());
let zim_obj = out.join("zig_lionos.o");
let status = std::process::Command::new(&zig)
    .args(["build-obj", "zig/lionos_zig.zig", "-O", "ReleaseSafe",
           "-femit-bin", zim_obj.to_str().unwrap()]).status()?;
assert!(status.success(), "zig build-obj failed");
objects.push(zim_obj);
```
Add `compile_cxx()` mirroring `compile()` but with `-std=c++17 -fno-exceptions -fno-rtti -fno-threadsafe-statics` appended (keep `-ffreestanding -fno-builtin -mno-red-zone -mcmodel=kernel -fno-pie -nostdinc`). Note `compile()` is the `cc`-based helper used for both C and C++ in practice (g++ reads C++ by extension), but keep flag parity explicit.

- [ ] **Step 5: bind and assert in `ffi.rs` + `main.rs`**
```rust
// ffi.rs
extern "C" { pub fn lionos_cpp_magic() -> u32; pub fn lionos_zig_magic() -> u32; }
```
```rust
// main.rs, in the ffi smoke block
serial::write_str("LIONOS_CPP magic=");
serial::write_hex(ffi::lionos_cpp_magic() as u64);
serial::write_str(" LIONOS_ZIG magic=");
serial::write_hex(ffi::lionos_zig_magic() as u64);
serial::write_str("\r\n");
```
- [ ] **Step 6: build + boot + check both magic values**
Run: `wsl -d kali-linux -- bash -lc 'cd ~/Projects/lion-os/kernel && cargo build'`
Then `cd ~/Projects/lion-os/os && cargo build`, then run `target/bios.img` in QEMU.
Expected (serial, inside the Kali QEMU run): `LIONOS_CPP magic=c0ffee0c LIONOS_ZIG magic=0014` (zig magic `0x00002600` prints hex-4 as `1400`).
- [ ] **Step 7: commit (Kali) + push (Windows)**
`wsl -d kali-linux -- bash -lc 'cd ~/Projects/lion-os && git add kernel/build.rs kernel/cpp kernel/zig kernel/src/ffi.rs kernel/src/main.rs && git commit -m "feat(kernel): C++17 + Zig join the FFI pie (build.rs gated)"'`
then Windows `git push`.

### Task 2: context-switch assembly + scheduler (cooperative → preemptive)

**Files:**
- Create: `kernel/asm/switch.asm` (NASM)
- Create: `kernel/src/sched.rs` (+ `mod sched;` in lib.rs)
- Create: `kernel/tests` host unit tests under `kernel/src/sched.rs` `#[cfg(test)]`
- Modify: `kernel/src/main.rs` (init + marker), `kernel/src/interrupts.rs` (PIT hook)

**Interfaces:**
- Consumes: `frames` (stack frames), `ffi::outb`/PIT (through interrupts.rs), `serial`.
- Produces: NASM `switçh_save_restore(prev_rsp:*mut *mut u64, next_rsp:*mut u64)`, Rust `sched::spawn(f)` , `sched::yield_()`, `sched::tick()` (preempt), `Pcb`; marker `LIONOS_SCHED coop=… preempt=…`, `LIONOS_SWITCH count=…`.

- [ ] **Step 1: write the NASM context switch**
```asm
; asm/switch.asm — cooperative x86_64 context switch (C-ABI), NASM.
; void switch_context(void **prev_sp, void *next_sp);
;   rdi = address of the CURRENT task's sp slot to store into
;   rsi = the NEXT task's saved rsp value to load
; Saves the 6 callee-saved regs of the running task on its own stack, stores
; its rsp into *prev_sp, points rsp at the next task's stack, and pops that
; task's 6 callee-saved regs, then `ret` returns into whichever caller pushed
; them (each task resumes exactly where its last switch returned).
section .text
global context_switch
context_switch:
    push rbx
    push rbp
    push r12
    push r13
    push r14
    push r15                 ; 6 pushes -> rsp is now the task's savepoint
    mov rax, rsp             ; rax = what to store
    mov [rdi], rax           ; *prev_sp = current rsp  (stash this task)
    mov rsp, rsi             ; switch to the next task's stack
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbp
    pop rbx
    ret
```
**Fresh-task spawn:** a new task's `Pcb.sp` points at a synthetic frame: `task_entry` (a `#[no_mangle] extern fn` that calls `f` then falls into an infinite `yield`/`hlt` loop) as the return address, under the 6 zeros the pops would consume. `sched::spawn` sets that up directly.

**Preemptive (PIT) path:** reuse the same save/restore register order, but run from inside the timer ISR, where the vecer-visible return is via `iretq`. So the ISR (Rust, `extern "x86-interrupt"`) builds an explicit interrupt frame on the *current*  stack — `[rip, cs, rflags, rsp, ss]` plus the 6 callee-saved — stashes rsp into the running PCB, selects the next PCB, then `iretq` consumes that frame on the next task's stack. The cooperative `context_switch` callee-saved order is reused so both paths agree. If a sub-agent hits the classic multi-switch corruption, the checklist is those exact 6 callee-saved regs + the rflags/rip/cs/ss frame ordering; do NOT trust interleaved output alone (the master plan warns it manifests several switches later).

- [ ] **Step 2: `sched.rs` PCB + spawn + cooperative yield (pure logic host-tested)**
```rust
pub struct Pcb {
    pub id: usize,
    pub state: TaskState,        // Ready, Running, Blocked
    pub sp: *mut u64,           // saved rsp
    pub counter: u64,
    pub timeslice: u64,         // preemptive rr quantum
}
pub struct Scheduler { tasks: Vec<Pcb>, current: usize, next_id: usize }
impl Scheduler {
    pub fn spawn(&mut self, f: fn()) {
        // alloc a stack page, lay down the synthetic switch frame: 6 callee-saved
        // zeros + return address = `entry` trampoline that calls f then loops
        // yield/hlt; push the PCB as Ready.
    }
    pub fn yield_(&mut self) { self.current = (self.current + 1) % self.tasks.len(); }
    pub fn tick(&mut self) { /* decrement quantum; on zero, rr-yield */ }
}
```
Host test (`#[cfg(test)]`): spawn 3 empty closures and assert `yield_` round-robins ids `0→1→2→0` and `state` flips Ready/Running. Done last.

- [ ] **Step 3: wire PIT preemption in `interrupts.rs`** — in the timer ISR (existing `timer_isr`), call `sched::tick()` when a scheduler exists; decrement current PCB quantum; on expiry do the `switch_context` inside the ISR. Guard: only if `sched::started()` else fall through to the existing tick-counter logic (backward compatible; old markers still fire).

- [ ] **Step 4: kernel boot markers** in `kernel_main` after `drivers::init_all()`:
```rust
// spawn 3 tiny tasks that busy-count in a loop and drop; their interleave
// counter is a deterministic marker.
serial::write_str("LIONOS_SCHED coop=");
serial::write_dec(coop_rounds);
serial::write_str(" preempt=");
serial::write_dec(preempt_rounds);
serial::write_str(" switch=");
serial::write_dec(switch_count);
serial::write_str("\r\n");
```
- [ ] **Step 5: soak** — the preemption loop runs many thousands of switches; assert no `PANIC` and counters monotonic (interleaving itself is the correctness proof). Build+boot in QEMU.
- [ ] **Step 6: commit (Kali)+push (Windows)** as `feat(kernel): scheduler - cooperative yield + PIT preemptive context switch (NASM)`.

### Task 3: IDE/ATI/ATA PIO block driver (real ATA) + a pure FAT32 parser

**Files:**
- Create: `kernel/src/drivers/ide.rs`, `kernel/src/drivers/virtio_blk.rs`
- Create: `kernel/src/fs.rs` (read-only FAT32 over a `BlockDevice` trait)
- Optional (kept only if a fuzzable pure boot-struct parser in C++ is genuinely wanted): `kernel/cpp/` — but the plan defaults the FAT BPB parser to pure Rust for host-testing/fuzzing, so this file is normally NOT created
- Modify: `kernel/src/drivers/mod.rs`, `kernel/src/main.rs`
- Create host tests in `fs.rs`, `ide.rs` pure cores.

**Interfaces:**
- Consumes: `serial`, `ffi::outb/inb/write`, heap.
- Produces: `ide::probe()->Option<AtaDisk>`, `BlockDevice { read_sector(lba,u8[512]) }`, `fs::Fs { bpb, root, read_file(path)->Vec<u8> }`; markers `LIONOS_DRV_IDE found=`, `LIONOS_FS_OK ls=… read=…`.

- [ ] **Step 1: FAT boot-structure parser — pure, host-tested, fuzz (before touching disk I/O)**
Write `fs.rs::parse_bpb(&[u8;512]) -> Result<FAT` validating ex-Signature `0x55AA`, FAT type, sector size=512, cluster math; host tests + a `cargo-fuzz` target `fuzz/fuzz_targets/fat_bpb.rs` (run a few minutes, no crash). This is the host-first practice from the plan's valgrind note (no block hardware yet).

- [ ] **Step 2: ATA-1 legacy port I/O driver**
`ide.rs` uses primary `0x1F0` / secondary `0x170` ports via NASM in/out wrappers. Identify (EC CAD1), LBA-28 read. Pure `probe` decides presence from the identify sign; returns `None` cleanly if no drive.
Boot marker `LIONOS_DRV_IDE found=1 virt=…` or `…_ABSENT`.

- [ ] **Step 3: virtio-blk shim (QEMU-backed real block)**
`virtio_blk.rs` minimal (`virtio-pci` bar 0. Note QEMU attaches by default; enables a disk image to be the letter `-drive file=fat.img,format=raw,if=virtio`. Pure PCI-detected; renders real sector reads back to the FS layer.)

- [ ] **Step 4: FAT12 FAT `fat32_ls` + `read_file`**
- Host-built image: Kali `mkfs`? no — mtools `mmd`/`mcopy` produce a FAT32 image you can `mdir`; but FAT32 needs at least a "partition table" or a Super floppy image. Build I model: `dd if=/dev/zero of=fs.img bs=1M count=32`; then `mkfs.fat -F 32 fs.img` (mtools `-i /mnt` mount or `mmd -i fs.img ::/dir`). Verify with `mdir ::` .
- In kernel: mount virtual device, `ls` prints filenames exactly matching `mdir ::`; `cat`/read returns byte-identical to the host source file. Marker `LIONOS_FS_READ ok`.

- [ ] **Step 5: drive boot with a FAT32 image in QEMU**
`lionos run` (launcher) gains a `-drive file=fs.img,format=raw,if=virtio` for the second disk; confirm the kernel reads the FS image over virtio during boot and `LIONOS_FS_READ ok` prints. Verify the virtio driver's PCI bar/registers with `objdump`-derived addresses match the PCI config space (`lspci`-equivalent) — the plan uses the same PCI-probe truth the `pci.rs` driver already has.

- [ ] **Step 6: commit** `feat(disk, fs): ATA/virtio block + read-only FAT32 (mtools-verified)`.

### Task 4: remaining nine real drivers (AHCI, NVMe, e1000, RTL8139, UHCI, EHCI, HPET, IOAPIC, VBE)

Each is a **pure-identify core (host-testable, architecture-portable for Track Android) + a `#[cfg(target_os="none")]` probe shim + a `LIONOS_DRV_*` marker**. The pattern from Task 3's IDE repeat; copy the structure. The plan compresses the nine to the shared pattern + the small unique register tables:

- [ ] **Step 1 — AHCI (SATA):** `drivers/ahci.rs` — probe PCI class 0x0106; `LIONOS_DRV_AHCI found=… ctl-ver=…`. QEMU `-device ich9-ahci`.
- [ ] **Step 2 — NVMe:** `drivers/nvme.rs` — probe PCI class 0x010802, `identify` via admin queue envelope nominal read of `CSI`; marker found/absent.
- [ ] **Step 3 — e1000 NIC:** `drivers/e1000.rs` — PCI 8086:100e eth0 detect EEsetup/ctrl, pause read; marker `LIONOS_DRV_E1000 mac=… pci=…`.
- [ ] **Step 4 — RTL8139 NIC:** `drivers/rtl8139.rs` — PCI 10ec:8139, config (FMP) read, `LIONOS_DRV_RTL8139 mac=…`.
- [ ] **Step 5 — UHCI (USB1.1):** `drivers/uhci.rs` — PCI 8086:7020, legacy support-REG, `LIONOS_DRV_UHCI cmd=…`.
- [ ] **Step 6 — EHCI (USB2):** `drivers/ehci.rs` — PCI class 0x0C0320, protocol `HCC`/`CAP`, `LIONOS_DRV_UHCI…`(EHCI chosen).
- [ ] **Step 7 — HPET:** `drivers/hpet.rs` — MMIO reg base via ACPI (or PCI? use predefined), read clock tick; `LIONOS_DRV_HPET clock=…`.
- [ ] **Step 8 — IOAPIC:** `drivers/ioapic.rs` — probe `IOAPICBASE` MMIO 0xFEC00000, IRQ-read from a bitmap, print `LIONOS_DRV_IOAPIC irqs={count}`; don't rewire the PIC (stays safe) — just enumerate.
- [ ] **Step 9 — VBE (Bochs/VBE + fb):** `drivers/vbe.rs` fill the existing framebuffer descriptor `modes`/set `LIONOS_DRV_VBE w=… h=… bpp=…`. (Real standard.)
- [ ] **Step 10 — register all in `drivers/mod.rs::init_all()`** in PCI order (enum first, then net/usb/timer/gfx), each guarded `probe → *_FOUND` else `*_ABSENT`.

Hand-built malformed checks + the C++/Zig smoke markers already cover the language half. Every driver repeats the identical host-testable-core/"none-shim" split. Batch per-driver commits with markers, and host tests (`cargo test --target x86_64-unknown-linux-gnu`) stay green after each.

### Task 5: CI + ARCHITECTURE §3 + boot-chain honesty docs + release `v0.4.0`

**Files:**
- Modify: `.github/workflows/ci.yml` (+ install `zig`, `g++`), `publish.yml` (add same; OCI labels)
- Modify: `docs/ARCHITECTURE.md` §3, `README.md` ("What works"), CHANGELOG
- Create: `docs/android.md` (Track A honest status)

**Interfaces:**
- Consumes: all Task 1–4 artifacts.

- [ ] **Step 1: CI add `zig` + `g++`** in both workflows' apt steps (`zig` from a pinned download, `g++` from apt), so the kernel build with C++/Zig compiles in CI. Add greps for a handful of the new markers (`LIONOS_CPP`, `LIONOS_ZIG`, `LIONOS_SCHED`, one driver FOUND).
- [ ] **Step 2: docs honest words** — recap the Track-PC "active, builds now" vs Track-A "arm64 future" split in the README "What works" and note UEFI real-PC boot deferred. `docs/android.md` names Android locked-boot + the x86-emulator preview as the real-today path.
- [ ] **Step 3: release ritual** — bump version, `[Unreleased]`→`[v0.4.0]`, tag `v0.4.0` (name it honestly per the plan, not a claim of arm64). `gh release create`; GHCR `lion:v0.4.0`; digest refresh in the Docker quick start.
- [ ] **Step 4: M3 gate regression** — full accumulated build boots all Months 1–3 markers in ONE QEMU run, host suite green, CI green on the push.
- [ ] **Step 5: commit + push**, handoff note in `docs/superpowers/`.