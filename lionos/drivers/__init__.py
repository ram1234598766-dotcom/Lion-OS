"""Driver framework + driver library for Lion-OS.

The kernel probes a DriverBus at boot; drivers auto-configure themselves and
degrade gracefully. See ``bus.py`` and ``framework.py``.
"""
from .framework import Driver, DriverStatus
from .bus import DriverBus, BootProbeLine
from .core import CORE_DRIVERS
from .library import LIBRARY_DRIVERS

__all__ = ["Driver", "DriverStatus", "DriverBus", "BootProbeLine",
           "CORE_DRIVERS", "LIBRARY_DRIVERS", "build_driver_bus"]


def build_driver_bus(config=None) -> DriverBus:
    """Instantiate every driver, apply config overrides, and build a bus.

    Simulated drivers are disabled unless ``show_simulated`` is set."""
    overrides = {}
    if config is not None:
        overrides = getattr(config, "drivers", {}) or {}
    show_sim = bool(getattr(config, "show_simulated", False))
    bus = DriverBus()
    for cls in CORE_DRIVERS + LIBRARY_DRIVERS:
        d = cls(config=overrides.get(cls.name))
        if d.simulated:
            d.status.enabled = bool(show_sim)
        bus.register(d)
    return bus
