; asm/switch.asm — cooperative x86_64 context switch (C ABI), NASM.
; Assembled by kernel/build.rs alongside port_io/cpu_utils, into liblionos_ffi.a.
;
; void context_switch(void **prev_sp, void *next_sp);
;   rdi = address of the CURRENT task's sp slot to store into
;   rsi = the NEXT task's saved rsp value to load
;
; Saves the 6 callee-saved regs of the running task on its own stack, stores
; its rsp into *prev_sp, points rsp at the next task's stack, and pops that
; task's 6 callee-saved regs, then `ret` returns into whichever caller pushed
; them. Each task resumes exactly where its last switch returned.  sysv args:
; rdi=arg1, rsi=arg2. We never touch rax/rcx/rdx/rsi/rdi or the r8-r11 (caller-
; saved) so the Rust caller's live values survive.

section .text

global context_switch
context_switch:
    push rbx
    push rbp
    push r12
    push r13
    push r14
    push r15                 ; rsp now points at this task's savepoint
    mov rax, rsp             ; rax = what to store for the current task
    mov [rdi], rax           ; *prev_sp = current rsp  (stash this task)
    mov rsp, rsi             ; switch to the next task's stack
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbp
    pop rbx
    ret