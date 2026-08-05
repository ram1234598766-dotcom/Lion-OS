/* LionOS kernel linker script — Month 1 / Week 3.
 *
 * Boots from 1 MiB (the conventional lowest safe load point for a non-PIE
 * kernel). Every output section is 4KiB-aligned so the resulting LOAD segments
 * are page-aligned. (Under bootloader 0.9.x/bootimage this alignment was
 * REQUIRED — a non-page-aligned VMA made the bootloader mis-map pages so
 * `_start` was never reached. Under bootloader 0.11 the loader maps arbitrary
 * `PT_LOAD`s, so the alignment is now hygiene rather than correctness.)
 *
 * `.got`, `.got.plt`, `.data.rel.ro` are folded into `.data` so they live in a
 * single 4KiB-aligned RW segment instead of a separate RELRO one.
 *
 * `.bootloader-config` (emitted by `bootloader_api`) MUST survive linking or
 * the 0.11 loader panics ("bootloader config section not found") before any
 * serial output.
 */
ENTRY(_start)

SECTIONS
{
    . = 1M;

    .text : ALIGN(4K)
    {
        *(.text)
        *(.text.*)
    }

    .rodata : ALIGN(4K)
    {
        *(.rodata)
        *(.rodata.*)
    }

    /* bootloader 0.11 requires this section; KEEP guards it against any
     * future --gc-sections. */
    .bootloader-config : ALIGN(4K)
    {
        KEEP(*(.bootloader-config))
    }

    .data : ALIGN(4K)
    {
        *(.data)
        *(.data.*)
        *(.got)
        *(.got.plt)
        *(.data.rel.ro)
        *(.data.rel.ro.*)
    }

    .bss : ALIGN(4K)
    {
        *(COMMON)
        *(.bss)
        *(.bss.*)
    }

    /* The C/asm objects (`c/support.c`, `asm/cpu.s`) emit these extra
     * sections; drop them so they can never become orphan LOAD segments that
     * break the page-aligned program-header layout the bootloader maps. */
    /DISCARD/ : {
        *(.comment)
        *(.note.GNU-stack)
        *(.note.gnu.property)
        *(.eh_frame)
        *(.eh_frame_hdr)
        *(.gcc_except_table)
    }
}