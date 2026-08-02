"""Simulated driver library. Importing registers nothing; the kernel builds a
DriverBus with selected drivers (see build_driver_bus in bus.py / kernel)."""
from ..core import CORE_DRIVERS
from .storage import NVMeDriver, RamDiskDriver, RaidDriver, FloppyDriver, TapeDriver, SanDriver
from .compute import FPUDriver, RNGDriver, QuantumDriver

LIBRARY_DRIVERS = [NVMeDriver, RamDiskDriver, RaidDriver, FloppyDriver, TapeDriver,
                   SanDriver, FPUDriver, RNGDriver, QuantumDriver]
