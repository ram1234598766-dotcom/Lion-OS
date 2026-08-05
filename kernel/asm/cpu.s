# LionOS kernel low-level CPU assembly — Month 1 refinement.
#
# GAS (AT&T) syntax. This is the "assembly half" of the mixed-language
# integration: minimal boot-context CPU stubs that are cleaner to express in
# raw assembly than in Rust `asm!`. They're compiled by build.rs and linked
# into the kernel, called through the FFI bridge in kernel/src/ffi.rs.
#
# No stack annotations, no libgcc, no late-binding; position-dependent only.
.section .text

# void lion_hlt(void) — HLT loop (boot park / panic). Never returns.
.global lion_hlt
.type lion_hlt,@function
lion_hlt:
    hlt
    jmp lion_hlt        # IF=0 so HLT unblocks only on NMI/INIT — keep parked
.size lion_hlt,.-lion_hlt

# void lion_cli(void)
.global lion_cli
.type lion_cli,@function
lion_cli:
    cli
    ret
.size lion_cli,.-lion_cli

# void lion_sti(void)
.global lion_sti
.type lion_sti,@function
lion_sti:
    sti
    ret
.size lion_sti,.-lion_sti

# void lion_pause(void) — spin-wait hint.
.global lion_pause
.type lion_pause,@function
lion_pause:
    pause
    ret
.size lion_pause,.-lion_pause

# uint64_t lion_read_cr3(void) — current page-table root, returned in RAX.
.global lion_read_cr3
.type lion_read_cr3,@function
lion_read_cr3:
    movq %cr3, %rax
    ret
.size lion_read_cr3,.-lion_read_cr3

# void lion_cpuid(uint32_t leaf, uint32_t subleaf, uint32_t out[4])
#   SysV: rdi=leaf, rsi=subleaf, rdx=&out. Writes eax,ebx,ecx,edx into out[0..3].
#
#   WATCH OUT: `cpuid` overwrites EDX with its output, and SysV has parked the
#   `out` pointer in %rdx. So the base address is moved to %r8 (a register
#   `cpuid` does NOT clobber) before the instruction; %r8 is caller-saved so it
#   needs no preservation. RBX is callee-saved and is restored around it.
.global lion_cpuid
.type lion_cpuid,@function
lion_cpuid:
    pushq %rbx
    movq  %rdx, %r8         # out base -> %r8 (cpuid would clobber %rdx)
    movl  %edi, %eax        # leaf
    movl  %esi, %ecx        # subleaf
    cpuid                   # clobbers eax,ebx,ecx,edx
    movl  %eax, 0(%r8)
    movl  %ebx, 4(%r8)
    movl  %ecx, 8(%r8)
    movl  %edx, 12(%r8)     # edx now holds cpuid's edx output -> out[3]
    popq  %rbx
    ret
.size lion_cpuid,.-lion_cpuid

# uint64_t lion_read_msr(uint32_t msr) — reads a model-specific register.
#   SysV: edi = MSR number. rdmsr reads ecx into edx:eax; combine into RAX.
#   rdmsr clobbers ecx/edx/eax, all caller-saved — safe for a leaf wrapper.
.global lion_read_msr
.type lion_read_msr,@function
lion_read_msr:
    movl  %edi, %ecx
    rdmsr                   # edx:eax = MSR[ecx]
    shlq  $32, %rdx
    orq   %rdx, %rax        # edx:eax -> rax (u64)
    ret
.size lion_read_msr,.-lion_read_msr

# void lion_write_msr(uint32_t msr, uint64_t value)
#   SysV: edi = msr, rsi = value. wrmsr takes ecx=msr, edx:eax=value.
.global lion_write_msr
.type lion_write_msr,@function
lion_write_msr:
    movl  %edi, %ecx
    movq  %rsi, %rax        # low 32 bits
    shrq  $32, %rsi
    movl  %esi, %edx        # high 32 bits
    wrmsr
    ret
.size lion_write_msr,.-lion_write_msr

# uint64_t lion_read_rflags(void) — snapshot of RFLAGS (e.g. IF bit 9).
.global lion_read_rflags
.type lion_read_rflags,@function
lion_read_rflags:
    pushfq
    popq  %rax
    ret
.size lion_read_rflags,.-lion_read_rflags

# uint8_t lion_inb(uint16_t port) — read one byte from an I/O port.
.global lion_inb
.type lion_inb,@function
lion_inb:
    movw  %di, %dx
    inb   %dx, %al
    ret
.size lion_inb,.-lion_inb

# void lion_outb(uint16_t port, uint8_t value) — write one byte to an I/O port.
.global lion_outb
.type lion_outb,@function
lion_outb:
    movw  %di, %dx
    movb  %sil, %al
    outb  %al, %dx
    ret
.size lion_outb,.-lion_outb

# uint8_t lion_xchg8(uint8_t *ptr, uint8_t value) — atomic byte exchange.
#   Returns the previous value. Spinlock acquire: prev = xchg8(&lock, 1);
#   the lock is held iff prev == 0. `xchg` with a memory operand is implicitly
#   locked on x86; the explicit `lock` is documentation.
.global lion_xchg8
.type lion_xchg8,@function
lion_xchg8:
    movb  %sil, %al
    lock xchgb %al, (%rdi)  # al <-> *rdi; al now holds the old value
    movzbl %al, %eax
    ret
.size lion_xchg8,.-lion_xchg8

# Mark the objects as having a non-executable stack (GNU_STACK PT_GNU_STACK).
.section .note.GNU-stack,"",@progbits