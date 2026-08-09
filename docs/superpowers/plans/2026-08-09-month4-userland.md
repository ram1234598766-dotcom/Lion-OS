# LionOS Month 4 (Userland) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Month 4 userland (v0.4.0): a working `syscall`/`sysret` kernel→user→kernel path, a real ring-3 user process that descends from and returns to ring 0, a minimal IPC + earliest shell, and `SECURITY.md` + a `checksec`/`ropper` audit. Everything still boots in QEMU with the accumulated suite green.

**Architecture:** extends the running kernel at `2b20d83` (M3 complete: scheduler, FAT32 + LFN, virtio/blk, Task-4 detect drivers). The kernel already owns its page tables (`paging::takeover`), has a writable GDT + TSS/IST (`gdt::setup`) + a frame-backed heap. Month 4 adds the ring-transition primitive set: ring-3 user segments, the `syscall`/`sysret` MSR path (`STAR`/`LSTAR`/`SFMASK`), user-mapped pages (U/S bit), a ring-3 trampoline (`iretq`), then syscall dispatch, IPC, and a tiny shell.

**Tech Stack:** Rust (nightly, `x86_64-unknown-none`), NASM + GAS, C. qemu 10.2.2. Git Bash (Windows) for read/edit/push; Kali for build/commit (gitleaks pre-commit) — see Global Constraints.

## Global Constraints (from previous months — honor these)
- **Build:** `wsl -d kali-linux -- bash -lc 'cd ~/Projects/lion-os && …'`; `cd kernel && cargo build` then `cd ../os && cargo build` → `target/bios.img`. Host tests: `cargo test --target x86_64-unknown-linux-gnu`.
- **FFI objects:** compiled only when `TARGET==x86_64-unknown-none` (build.rs guard).
- **Markers:** every boot marker starts `LIONOS_` and is deterministic for a fixed VM; CI greps them. Add new markers to `.github/workflows/ci.yml`'s positive-boot step.
- **`#[cfg(target_os="none")]`:** anything touching `ffi::`/ports/ring state is gated; pure logic is host-tested.
- **Commit in Kali, push from Windows** (gitleaks pre-commit on Kali). Never `$VAR` in Bash tool commands (expands empty). CRLF: `tr -d '\r' < X > X.lf && mv`, verify byte-delta.
- **Kernel `.bss` stays modest** (bootloader's PageAlreadyMapped trap) — ring-3 user code/stacks come from the frame allocator, not `.bss`.
- **MMIO/VGA through the phys window** (`0xB8000 + paging::phys_offset()`), never identity.
- **Honesty:** user-mode bring-up on a bare-metal x86 kernel is genuinely hard; each milestone must boot with its markers + CI green before moving on. If `syscall` unsupported (CPUID), fall back to `int 0x80`-style IDT entry and say so.

---

### Task 1: Ring-3 segments + syscall MSRs (the foundation)

**Files:**
- Modify: `kernel/src/gdt.rs` — add `USER_CODE` (0x28) and `USER_DATA` (0x30) ring-3 descriptors to the writable GDT in `setup()`, bump the GDT entry count (was null+code+data+TSS(2) = 5 slots → +2 user slots).
- Modify: `kernel/src/paging.rs` — add `map_user_page(offset, virt, phys)` (present + writable + **user**). The existing `map_page` maps supervisor-only.
- Create: `kernel/src/syscall.rs` — MSR constants, `enable_syscall()` (CPUID check → write STAR/LSTAR/SFMASK), a pure syscall-number/dispatch table.
- Modify: `kernel/src/ffi.rs` + `kernel/asm/cpu.s` — `lion_swapgs`/`lion_sysret`/`lion_iret_to_3` stubs + safe wrappers.

**Reasoning (the trap to not relearn):**
- `syscall` uses `STAR[47:32]` = kernel CS (0x08) and `STAR[63:48]` = user CS (0x28) for `sysretq` (RPL forced to 3 on return). `LSTAR` = kernel RIP of the entry stub; `SFMASK` = RFLAGS bits to clear on entry — clear `IF` (bit 9) so user-set IF can't unmask kernel interrupts mid-handler.
- `iretq` to ring-3 pops {RIP, CS(RPL3), RFLAGS, RSP, SS} from the *kernel* stack; the CPU performs a privilege descent (uses SS/RSP from the frame) — the only descent path (sysret is a return, not a descent). The ring-0→3 drop uses iretq; ring-3→0 uses a `syscall` trampoline in ring 3 via LSTAR.
- On the very first ring-3 descent, interrupts must be OFF while building the frame; enable afterward in ring 3 with the interrupt flag you actually want. A TSS/RSP0 must point at a valid *kernel* stack so ring-3→ring-0 IRQs (timer/keyboard) have a kernel stack to switch to — set it before dropping to ring 3.

**Steps** (host-testable pieces first, then the ring-3 hardware path):
- [ ] Step 1: add ring-3 descriptors + selectors + host tests in `gdt.rs` (access bytes 0xFA / 0xF2, present|DPL3).
- [ ] Step 2: add `paging::map_user_page` + a host test that the U bit is set (and supervisor `map_page` does not).
- [ ] Step 3: `syscall.rs` — pure dispatch table + `enable_syscall()` (kernel target).
- [ ] Step 4: `cpu.s` `lion_sysret`/`lion_iret_to3` stubs + ffi wrappers (kernel target only).
- [ ] Step 5: boot smoke prints `LIONOS_SYSCALL_MSR star=… lstar=… sfmask=…` (write→read round-trip proves wrmsr+rdmsr). Host suite green.

### Task 2 — First descent (0→3) + a user syscall round-trip *(the hot loop)*
- [ ] map a user code page (a small machine-code stub) + a user stack page, both user-writable, at a free low 512 GiB region
- [ ] set TSS.RSP0 to a kernel frame-allocated stack; set `STAR`/`LSTAR`/`SFMASK`
- [ ] iretq to ring 3 (prints `LIONOS_USER_L3 cs=…r3`)
- [ ] the user stub does `syscall` with a number in `rax`; the LSTAR handler echoes it and `sysretq`s (`LIONOS_SYSCALL num=…`)
- [ ] user stub loops a bounded count → `LIONOS_USER_RT done`
- [ ] CI greps — many QEMU triages expected (this is the hardest)

### Task 3 — IPC + minimal shell
- [ ] define a `put`/`get`-style syscall pair on the dispatch table
- [ ] a two-line ring-3 shell that prints a prompt and echoes a typed line via syscall

### Task 4 — SECURITY.md + audit
- [ ] write `SECURITY.md`: threat model, permission/ring model, explicitly NOT enforced yet
- [ ] run `checksec --file=target/bios.img` and `readelf`/`objdump` on the kernel ELF; record NX/RELRO/canary findings + TODOs
- [ ] fold the Security section of the README to reference it

### Release
Task 5 — bump everything to **v0.4.0** (README roadmap already keyed to it), `[Unreleased]`→`[v0.4.0]` changelog, `lion:v0.4.0` Docker refs, tag `v0.4.0` in Kali → push (publish.yml → GHCR) → `gh release create`. License label stays All-Rights-Reserved.

---

While Month 1–3 each cracked a hard bring-up, this is the integrated-stir slow one (ring 3 + the full MSR syscall path + a real user process). Reserve a dedicated block for Task 2. Finish each task booted + CI-green before the next begins.