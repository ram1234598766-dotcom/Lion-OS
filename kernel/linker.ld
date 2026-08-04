/* LionOS kernel linker script — Month 1 / Week 3.
 *
 * Boots from 1 MiB (the conventional lowest safe load point for a non-PIE
 * kernel). Every output section is 4KiB-aligned so the resulting LOAD segments
 * are page-aligned: the bootloader 0.9.x (bundled by `bootimage`) maps the
 * kernel by page-aligned program headers, and a segment starting at a
 * non-page-aligned VMA (the default placement of `.got`/`.data.rel.ro` under
 * RELRO) makes the bootloader mis-map pages so `_start` is never reached.
 *
 * `.got`, `.got.plt`, `.data.rel.ro` are folded into `.data` so they live in a
 * single 4KiB-aligned RW segment instead of a separate misaligned RELRO one.
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