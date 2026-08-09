ENTRY(_start)

/* USER_BASE — the fixed low-canonical virtual base the kernel's ELF loader maps
   this program at (kernel/src/elf.rs `USER_BASE`). Non-PIE, so the loader maps
   PT_LOAD segments at exactly these VAs and jumps to `_start`. */
PHDRS
{
  text PT_LOAD FLAGS(5); /* R E */
  data PT_LOAD FLAGS(6); /* R W */
}

SECTIONS
{
  /* Relative base — the kernel loads this at a runtime-chosen free ring-3
     region (user_base + segment.vaddr), keeping the tables U/S on all levels.
     Entry is a small offset; all code is RIP-relative (no data/absodups). */
  . = 0x1000;
  .text : { *(.text*) } :text
  .rodata : { *(.rodata*) } :text
  .data : { *(.data*) } :data
  .bss : { *(.bss*) *(COMMON) } :data
  /DISCARD/ : { *(.eh_frame*) *(.comment) *(.note.*) }
}