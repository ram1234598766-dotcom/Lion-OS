# bootloader

Week-1 placeholder. The custom LionOS bootloader (UEFI memory-map handoff,
page tables, long-mode entry) is built here in Month 1 Week 3. Until then, the
kernel is booted with the upstream `bootloader` 0.11.17 crate (disk image built
by the `os/` crate's `BiosBoot` DiskImageBuilder) so
CI can exercise the real QEMU boot path.
