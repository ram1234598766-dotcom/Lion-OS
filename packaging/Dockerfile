# LionOS — packaged as an OCI/GHCR image that boots the kernel headless in QEMU.
#
# The kernel currently prints LIONOS_INIT_OK to the serial port then halts.
# `-nographic` routes that serial output to stdout, so running the container
# streams the boot marker to the terminal:
#
#   docker run --rm ghcr.io/ram1234598766-dotcom/lion-os
#
# The boot image is a build artifact (not committed); rebuild it before
# building this image with:  (cd kernel && cargo build && cargo bootimage)

FROM debian:bookworm-slim

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends qemu-system-x86 \
    && rm -rf /var/lib/apt/lists/*

# The prebuilt, checksummed bootable disk image (bootloader crate + kernel).
COPY bootimage-lionos-kernel.bin /opt/lionos/bootimage-lionos-kernel.bin

ENTRYPOINT ["qemu-system-x86_64", "-nographic", "-machine", "accel=tcg", "-no-reboot", \
    "-drive", "format=raw,file=/opt/lionos/bootimage-lionos-kernel.bin"]