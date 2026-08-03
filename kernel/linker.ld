/* LionOS kernel linker script — Month 1 / Week 1.
 *
 * Boots from 1 MiB (the conventional lowest safe load point for a
 * non-PIE kernel). Month 1 Week 3 replaces this with the real layout
 * (higher-half mapping, bootloader-defined segments).
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
    }

    .bss : ALIGN(4K)
    {
        *(COMMON)
        *(.bss)
        *(.bss.*)
    }
}
