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

# Mark the objects as having a non-executable stack (GNU_STACK PT_GNU_STACK).
.section .note.GNU-stack,"",@progbits