; port_io.asm - Raw x86_64 port I/O helpers (NASM)
; Assembled with NASM (-f elf64) by kernel/build.rs, archived into the kernel
; static FFI lib alongside the GAS cpu.s and C sources. Called from Rust via
; extern "C" declarations in kernel/src/ffi.rs (nasm_* bindings).
;
; WHY NASM ALONGSIDE GAS:
;   Month 1 of the master plan specifies NASM for the low-level port-I/O and
;   CPU-utils routines (port_io.asm, cpu_utils.asm), which is what the
;   lion-os-boilerplate scaffold ships. The existing GAS cpu.s layer (lion_*
;   symbols) stays; these NASM files add the plan's canonical low-level surface
;   (outb/inb/outw/inw/io_wait/cpu_pause/cpu_halt) as a second, auditable
;   assembly layer. Symbol names do not collide with the GAS layer.
;
; Position-dependent, no stack annotations, no libgcc. Flat code segment
; (bootloader 0.11's CS=0x08), SysV argument passing:
;   rdi=arg1, rsi=arg2, rdx=arg3, rcx=arg4, r8=arg5.

section .text

; void outb(uint16_t port, uint8_t value)
; Write a byte to an x86 I/O port. Port in DI, value in SIL.
global outb
outb:
    mov dx, di          ; port  -> DX (the I/O port register)
    mov al, sil         ; value -> AL
    out dx, al          ; write AL to port DX
    ret

; uint8_t inb(uint16_t port)
; Read a byte from an x86 I/O port. Returns value in AL (= RAX).
global inb
inb:
    mov dx, di          ; port -> DX
    in  al, dx          ; read from port DX into AL
    ret

; void outw(uint16_t port, uint16_t value)
; 16-bit port write (used for PIC EOI and some legacy hardware).
global outw
outw:
    mov dx, di
    mov ax, si
    out dx, ax
    ret

; uint16_t inw(uint16_t port)
global inw
inw:
    mov dx, di
    in  ax, dx
    ret

; void io_wait(void)
; Brief delay by writing to an unused port - classic workaround for slow I/O
; devices that need a moment after a write (e.g. PIC). Port 0x80 is
; conventionally used for POST codes; writing to it wastes ~1-2 us on real hw.
global io_wait
io_wait:
    out 0x80, al        ; writing to 0x80 is the standard "I/O delay" idiom
    ret

; void cpu_pause(void)
; x86 PAUSE instruction - tells the CPU it is in a spin-wait loop.
global cpu_pause
cpu_pause:
    pause
    ret

; void cpu_halt(void)
; Halt the CPU until the next interrupt arrives. Used in idle loops and panic
; handlers to avoid busy-spinning.
global cpu_halt
cpu_halt:
    hlt
    ret
