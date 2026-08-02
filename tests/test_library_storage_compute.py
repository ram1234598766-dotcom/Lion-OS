# tests/test_library_storage_compute.py
from lionos.drivers.library.storage import NVMeDriver, RamDiskDriver, RaidDriver, FloppyDriver
from lionos.drivers.library.compute import FPUDriver, RNGDriver


def test_nvme_read_write():
    d = NVMeDriver()
    d.probe()
    d.write(b"hello")
    assert d.read() == b"hello"


def test_ramdisk_wiped_on_reinit():
    d = RamDiskDriver()
    d.probe()
    d.write(b"x")
    d2 = RamDiskDriver()
    assert d2.read() == b""


def test_floppy_size_cap():
    d = FloppyDriver()
    assert d.max_size == 1_474_560


def test_fpu_accel():
    d = FPUDriver()
    assert d.sqrt(9) == 3.0


def test_rng_entropy():
    d = RNGDriver()
    d.probe()
    assert len(d.random_bytes(16)) == 16
