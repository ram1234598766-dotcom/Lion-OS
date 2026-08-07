; cpu_utils.asm - CPU-level utility routines (NASM)
; Assembled with NASM (-f elf64) by kernel/build.rs. These are things that
; either have no safe Rust equivalent (raw MSR access, CPUID) or are much
; cleaner expressed in asm than via inline asm! macros.
;
; Integration note: the GAS cpu.s layer already provides lion_read_msr/
; lion_write_msr/lion_cli/lion_sti under their own names; this NASM file adds
; the master-plan's canonical symbol names (enable_interrupts, disable_interrupts,
; read_msr, write_msr, cpuid_query). No symbol collisions with the GAS layer.
;
; WATCH OUT (inherited from the GAS layer's hard-won fix): `cpuid` overwrites
; EDX with its output, and SysV parks argument pointers in RDX/RCX. Any
; `mov [rdx], ...` / `mov [rcx], ...` AFTER the cpuid would write through the
; clobbered register -> #PF -> triple fault. Stage every output-pointer base in
; a register `cpuid` does NOT touch (rsi, r8, r9, r10) BEFORE the instruction.
; Those are caller-saved, so no preservation is needed. RBX is callee-saved and
; IS preserved around cpuid.

section .text

; void enable_interrupts(void) - sti
global enable_interrupts
enable_interrupts:
    sti
    ret

; void disable_interrupts(void) - cli
global disable_interrupts
disable_interrupts:
    cli
    ret

; uint64_t read_msr(uint32_t msr)
; Read a Model-Specific Register. ECX = MSR number. rdmsr returns EDX:EAX.
global read_msr
read_msr:
    mov ecx, edi        ; msr number from first arg
    rdmsr               ; result: EDX = high 32, EAX = low 32
    shl rdx, 32
    or  rax, rdx        ; combine into RAX
    ret

; void write_msr(uint32_t msr, uint64_t value)
global write_msr
write_msr:
    mov ecx, edi        ; msr number
    mov eax, esi        ; low 32 bits of value
    mov rdx, rsi
    shr rdx, 32         ; high 32 bits
    wrmsr
    ret

; void cpuid_query(uint32_t leaf, uint32_t subleaf,
;                  uint32_t *eax, uint32_t *ebx, uint32_t *ecx, uint32_t *edx)
; Execute CPUID(leaf, subleaf) and write the four result words through the
; pointers. SysV: rdi=leaf, rsi=subleaf, rdx=&eax, rcx=&ebx, r8=&ecx, r9=&edx.
;
; `cpuid` overwrites EAX/EBX/ECX/EDX, so the &eax base in rdx and the &ebx base
; in rcx would be clobbered and must be parked in safe registers r10/r11 before
; the instruction. rsi (subleaf), r8 (&ecx), r9 (&edx) are untouched by cpuid.
global cpuid_query
cpuid_query:
    push rbx            ; preserve callee-saved RBX (cpuid clobbers it)
    mov  r10, rdx       ; &eax   -> r10 (cpuid won't touch r10)
    mov  r11, rcx       ; &ebx   -> r11 (cpuid won't touch r11)
    mov  eax, edi       ; leaf
    mov  ecx, esi       ; subleaf
    cpuid               ; results in EAX, EBX, ECX, EDX
    mov  [r10], eax     ; *&eax = eax
    mov  [r11], ebx     ; *&ebx = ebx
    mov  [r8],  ecx     ; *&ecx = ecx   (r8 base intact)
    mov  [r9],  edx     ; *&edx = edx   (r9 base intact)
    pop  rbx
    ret