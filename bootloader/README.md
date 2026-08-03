# bootloader

Week-1 placeholder. The custom LionOS bootloader (UEFI memory-map handoff,
page tables, long-mode entry) is built here in Month 1 Week 3. Until then, the
kernel is booted with the upstream `bootloader` crate + `bootimage` tool so
CI can exercise the real QEMU boot path.
