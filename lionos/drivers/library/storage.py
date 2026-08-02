"""Storage drivers — in-memory block stores, RAID striping, caps."""
from __future__ import annotations

import io

from ..framework import Driver


class NVMeDriver(Driver):
    name = "nvme"
    category = "storage"
    description = "High-speed in-memory block store"
    config_defaults = {"size": 1 << 20}

    def __init__(self, config=None):
        super().__init__(config)
        self._disk = io.BytesIO()

    def probe(self):
        return True

    def write(self, data: bytes):
        self._disk.seek(0)
        self._disk.write(data)

    def read(self) -> bytes:
        self._disk.seek(0)
        return self._disk.read()

    def diagnose(self):
        return f"{self.config['size'] // 1024} KiB"


class RamDiskDriver(Driver):
    name = "ramdisk"
    category = "storage"
    description = "Volatile RAM disk, wiped on reboot"
    config_defaults = {"size": 1 << 20}

    def __init__(self, config=None):
        super().__init__(config)
        self._disk = io.BytesIO()

    def probe(self):
        return True

    def write(self, data: bytes):
        self._disk.seek(0)
        self._disk.write(data)

    def read(self) -> bytes:
        self._disk.seek(0)
        return self._disk.read()

    def diagnose(self):
        return "volatile"


class RaidDriver(Driver):
    name = "raid"
    category = "storage"
    description = "Stripes virtual data across host folders"
    config_defaults = {"mirror": True}

    def __init__(self, config=None):
        super().__init__(config)
        self._parts = []

    def probe(self):
        return True

    def write(self, data: bytes):
        half = len(data) // 2
        self._parts = [data[:half], data[half:]]

    def read(self) -> bytes:
        return (self._parts[0] + self._parts[1]) if len(self._parts) == 2 else b""


class FloppyDriver(Driver):
    name = "floppy"
    category = "storage"
    simulated = True
    description = "3.5\" floppy — 1.44 MB caps"
    max_size = 1_474_560

    def probe(self):
        return True

    def fits(self, size: int) -> bool:
        return size <= self.max_size

    def diagnose(self):
        return "1.44 MB"


class TapeDriver(Driver):
    name = "tape"
    category = "storage"
    simulated = True
    description = "Sequential-only archival tape"

    def probe(self):
        return True


class SanDriver(Driver):
    name = "san"
    category = "storage"
    description = "Treat host folders as drives"

    def probe(self):
        return True
