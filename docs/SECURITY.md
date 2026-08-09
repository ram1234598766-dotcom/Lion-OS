# SECURITY.md — LionOS security model

> **Month 4 deliverable.** Documents the v0.4.0 threat model, the ring/permission
> model, what *is* enforced, and — honestly — what is **not yet** enforced.
> Quantitative scan output (`checksec` / `readelf` / `objdump`) is recorded in
> the accompanying audit task of Month 4.

## 1. Design principles

1. **Least privilege at every ring.** User (ring-3) code only reaches the
   system through the syscall ABI (`docs/SYSCALLS.md`), never through direct
   I/O or MSR access.
2. **Kernel/user page split.** Kernel pages are mapped supervisor-only
   (unprivileged ring-3 access #PFs). User pages carry the U/S bit.
3. **Honest about gaps.** If an isolation boundary is not yet exercised, it is
   stated explicitly rather than implied. No security theater.
4. **No secrets in the image.** The kernel binary contains no long-lived
   credentials by design (gitleaks pre-commit + secret scanning).

## 2. Enforced (v0.4.0)

- Ring-3 execution via the `syscall`/`sysret` + `iretq` trampoline.
- User code cannot execute privileged instructions at CPL3 (I/O ports and
  MSRs are ring-0 only; device pages are supervisor-mapped).
- Syscall number lookup is bounded: unknown numbers return `ENOSYS`.
- Paging: `map_user_page` vs `map_page` split keeps user line-page access
  from the kernel; the takeover (`paging::takeover`) gives us owned tables we
  control the U/S bit on.

## 3. Threat model

| Adversary | privilege | what it can do | against it |
|-----------|-----------|----------------|------------|
| Buggy/rogue user process | ring 3 | call any syscall, read its own mappings | syscall ABI + per-page user mapping; no privileged instructions |
| User reading kernel memory | ring 3 | read U/S pages only | kernel pages have no U/S → #PF |
| Kernel bug | ring 0 | full memory/I/O | mitigation via the fault handlers + our PageParse tracing (`LIONOS_FAULT`) |

## 4. NOT yet enforced (explicit)

- **SMEP is enabled when the CPU supports it** (boot `LIONOS_SEC_CAPS nx=1
  smep=0|1`); writing CR4 bits the CPU lacks #GPs (QEMU's default CPU has no
  SMEP — that was the earlier silent stall), so it is gated on CPUID.7.0:EBX.
- **SMAP is still deferred.** Enabling it must come with `stac`/`clac` around
  the ring-0 `copy_from_user` (SYS_PUTS), or ring-0 reads of user pages fault.
  NX-on-user-*data* pages IS enforced (`map_user_data`).
- **No upper/lower half separation.** User allocations share the same
  global page tables as the kernel (the kernel just leaves the U/S off).
- **No pids / no per-process page-table switch.** The scheduler is
  ring-0-only so far; the single ring-3 program is the only U/S process. A
  future `exec` must give each process its own PML4 (+ flip CR3 on switch),
  then `SECURITY.md` grows the multi-process isolation row.

## 5. Audit (Month 4 Task 4 — run against the debug kernel ELF)

```
checksec --file=target/x86_64-unknown-none/debug/lionos-kernel
readelf -lW  target/x86_64-unknown-none/debug/lionos-kernel
```

**Recorded (2026-08-09, debug build):**

| checksec | value |
|----------|-------|
| NX       | **enabled** (GNU_STACK is RW, non-exec) |
| RELRO    | **Partial** (GNU_RELRO over 0x188 bytes) |
| Stack canary | **none** (freestanding kernel, no libc/prologue canary) |
| PIE      | **No** (static `EXEC`, `-no-pie` by design) |
| RPATH/RUNPATH | none |
| Symbols  | 605 (debug build, not stripped) |

`readelf -lW` (4 LOAD segments): text `R E`, rodata `R`, data/bss `RW`. NX is
real for the stack/CLS; code pages are executable because they must be (the
kernel runs them). A single `GNU_STACK RW` means no executable stack.

**Honest gaps → TODOs (no hardening commit yet):**
- **NX on user *data* pages — DONE** (`map_user_data`, boot `LIONOS_SEC_CAPS
  nx=1`). The user *code* page stays W+X; the user *stack* is NX.
- **SMEP — DONE when supported** (CPUID-gated, boot `.. smep=0|1`); on a CPU
  without SMEP (QEMU default) it stays 0 and boots fine.
- **SMAP — open** (needs `stac`/`clac` around the SYS_PUTS `copy_from_user`).
- **Partial RELRO / no canary / no PIE** — a freestanding kernel relocates to a
  fixed low address by design; these are inherent rather than regressions, but a
  canary on the ring-0 syscall path would raise the cost of a userland exploit
  escalation. Open hardening file.
- **Kernel ELF not stripped in debug** (615 symbols) — debug-only.

Run a release (`--release`) build of the same audit for the shipped image; the
relro/canary/PIE story is unchanged, symbols drop.

## 6. Reporting

filed bugs / vulns: open via GH Issues in `ram1234598766-dotcom/Lion-OS`.
The kernel is a study bare-metal OS — no production guarantees.