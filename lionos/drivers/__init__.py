"""Driver framework + driver library for Lion-OS.

The kernel probes a DriverBus at boot; drivers auto-configure themselves and
degrade gracefully. See ``bus.py`` and ``framework.py``.
"""
from .framework import Driver, DriverStatus

__all__ = ["Driver", "DriverStatus"]
