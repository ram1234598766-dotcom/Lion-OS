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

- **No SMEP/SMAP / NX on user-flagged exec pages.** We rely on `Nx`-capable
  but the ELF/PTE setup doesn't set NX bits yet; `kernel` code pages are
  executable. TODO at a lower number in a hardening commit.
- **No upper/lower half separation.** User allocations share the same
  global page tables as the kernel (the kernel just leaves the U/S off).
- **No pids / no per-process page-table switch.** The scheduler is
  ring-0-only so far; the single ring-3 program is the only U/S process. A
  future `exec` must give each process its own PML4 (+ flip CR3 on switch),
  then `SECURITY.md` grows the multi-process isolation row.

## 5. Audit (run at Month 4 Task 4)

```
# kernel still a static non-PIE ELF; NX/RELRO are ELF-level and apply to the
# load image. Record output here, then update the CHANGELOG/README Security
# section with the real numbers.
checksec --file=target/x86_64-unknown-none/debug/lionos-kernel
readelf -lW  target/x86_64-unknown-none/debug/lionos-kernel
objdump -d  target/x86_64-unknown-none/debug/lionos-kernel | head -40
```
Record here once run:
- `checksec`: NX: ____, RELRO: ____, Canary: ____, PIE: ____, GNU_STACK: ____
- `readelf` LOAD segments: ____

## 6. Reporting

filed bugs / vulns: open via GH Issues in `ram1234598766-dotcom/Lion-OS`.
The kernel is a study bare-metal OS — no production guarantees.