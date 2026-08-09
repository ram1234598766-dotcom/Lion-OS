# SYSCALLS.md — LionOS syscall interface

> **Month 4 (design week + build):** This is the syscall ABI for LionOS v0.4.0.
> Interface and numeration are specified here and driven by the `syscall`/
> `sysret` ring path (see `docs/ARCHITECTURE.md §4`). The low-level trap notes
> are logged in
> `docs/superpowers/plans/2026-08-09-month4-userland.md`.

## 1. Calling convention

Ring 3 code calls the kernel with the **`syscall`** instruction on a 64-bit
Kernel. Registers on entry:

| Reg  | Meaning                                  |
|------|------------------------------------------|
| `rax`| **syscall number**                         |
| `rdi`| arg0 (first argument)                    |
| `rsi`| arg1                                    |
| `rdx`| arg2                                    |
| `r10`| arg3 (the 4th arg; `syscall` clobbers `rcx`, so the C ABI 4th arg `rcx` is mirrored into `r10` before the call — see §5 for the model) |

Only `rax` (number) + up to 4 args are passed this way; the entry stub stash
args into a closed save area and returns via `sysretq` with the result in
`rax`. **Registers are not all-saved:** the kernel preserves callee-saved regs
(`rbx`, `rsp`, `rbp`, `r12..r15`) and the caller saves the rest — the same
normal C ABI split.

## 2. Return

`rax` = signed 64-bit `Errno` on failure (negative), or the API's result on
success. Zero is success for void syscalls. Error values are stable and
negative:

| errno (value)        | description                          |
|----------------------|--------------------------------------|
| `ENOSYS` / 0xffffffffffffff38 | unknown syscall number  |
| `EINVAL`          | bad argument                     |
| `EACCES`          | permission denied (ring/permission model, §7) |
| `EFAULT`          | bad user pointer                 |

## 3. User↔kernel transitions

- **Ring 0 → ring 3:** only the *initial* descent uses `iretq` (frame:
  `RIP; CS(RPL3); RFLAGS; RSP; SS`). Thereafter ring 3 stays in ring 3.
- **Ring 3 → ring 0:** `syscall`. The LSTAR stub clobbers only `rcx`/
  `r11` (HW), swaps to a kernel stack, dispatches, returns via `sysretq`.
- **ring 3 → ring 0 negative path:** the stub checks `SFMASK`/CPL; a `sysretq`
  forces RPL 3 by definition. A `call` from ring-0 code that wrongly triggers
  the stub is a kernel bug (assert).

## 4. Syscall numbers

| # | name | args | returns |
|---|------|------|---------|
| 0 | `exit(code)` | u64 | never |
| 1 | `putc(c)` | char | errno |
| 2 | `puts(ptr,len)` | ptr,len | count |
| 3 | `getc()` | — | char or `EAGAIN` |
| 4 | `ledget(hz)` | hz | errno (PIT/IPC placeholder) |
| 5 | `sleep(ms)` | ms | errno (park until PIT) |

Numbers 0–7 are reserved for kernel core; >= 8 are per-driver extendable.

## 5. `syscall`/`sysret` MSR wiring (kernel side)

`IDT`-gates `int` are not the path; the provided fast entry is:

```
STAR       (0xC000_0081)  bit47:32 = kernel CS (0x08)
                          bit63:48 = user  CS (0x28)
LSTAR      (0xC000_0082)  RIP of `syscall_entry` (64-bit)
SFMASK     (0xC000_0084)  RFLAGS to clear on entry  (IF, bit 9)

CPUID extended feature:  `syscall` present iff
   CPUID.0x80000001:EDX (bit 11). Gate `enable_syscall()` on it.
```

Segment selectors live in `gdt.rs`: `KERNEL_CODE 0x08`, kernel `DATA 0x10`,
`USER_CODE 0x28`, `USER_DATA 0x30` (all descriptors present, DPL as expected).

## 6. Entry path (ring → ring0) — needs kernel stack

`syscall` does **not** auto-switch RSP like an interrupt to a ring0 TSS. The
stub must immediately stash the user RSP and load a kernel stack:

```
syscall_entry:
    swapgs                 # (only if user's GS is live — see §8)
    mov  %rsp, %r11        # user RSP saved (r11 is scratch)
    mov  KERNEL_STACK, %rsp
    push %rcx              # user RIP (syscall saved it) — return addr
    push %r11              # user RSP
    ...dispatch on rax...
    pop  %r11
    pop  %rcx
    mov  %r11, %rsp
    sysretq                # RCX→RIP, R11→RFLAGS
```

The pointer `KERNEL_STACK` here is a *per-descent* kernel stack, allocated
from the frame-backed heap and recorded in the TSS/RSP0 (so IRQs from ring 3
also get a kernel stack). Without it, the stub would reuse the last user RSP
and corrupt user memory.

## 7. Permission model (v0.4.0 scope)

- Ring 3 code cannot directly access ports, MSRs, or I/O — only via the
  syscalls listed. On a “no direct `in`/`out`” policy, this is enforced by
  ring privilege (CPL3 cannot execute `in`/`out` at IOPL<3) and by mapping no
  U/S device pages.
- Memory: a user process sees only **its own** U/S-mapped pages (code + stack
  + a shared copy/out buffer). Kernel pages are supervisor (no U/S) and fault
  on ring-3 access. Any v0.4.0 milestone that does NOT yet enforce
  upper/lower split MUST say so (honest in SECURITY.md §Not-yet).
- `filepos`/`putc`: the shell only touches a single channel (COM1) for now;
  multi-channel routing is Task 4 follow-up.

## 8. Deferred / future
- `swapgs` once a user GS/FS base is used; a per-PCB kernel stack chosen by
  the dispatcher, not one global; `getpid`/`kill` and a scheduler tie-in;
  buffer-safety review of the shared copy/out buffer.

## 9. Reference
- `kernel/src/syscall.rs` — number table + dispatch (pure, host-tested).
- `kernel/asm/cpu.s` — `lion_syscall_entry`/`lion_sysret`.
- `docs/ARCHITECTURE.md §4` — architecture.
- `docs/superpowers/plans/2026-08-09-month4-userland.md` — build plan.

## 10. Why the fourth argument hazard
`syscall` saves the return RIP in `RCX` and RFLAGS in `R11`, so `rcx` is *not*
available as a general arg. The compiler ABI passes arg4 in `rcx` — so the
stub's dispatch reads `rdi,rsi,rdx,r10` and never uses `rcx` for data. This
is the classic syscall4-vs-call4 trap; the model table above already treats
arg4 as `r10`.