"""Driver framework for Lion-OS.

A ``Driver`` declares a name/category/dependencies and a lifecycle:
``probe -> init -> start -> update -> stop``. Drivers auto-tune their own
config from ``probe()`` results, degrade gracefully when hardware/backends are
absent, and report ``DriverStatus`` for the Devices app and System Health.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class DriverStatus:
    available: bool = True
    enabled: bool = True
    running: bool = False
    health: int = 100
    detail: str = ""
    last_error: str = ""

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ("available", "enabled", "running", "health", "detail", "last_error")}


class Driver:
    name: str = "driver"
    category: str = "generic"
    simulated: bool = False
    depends: List[str] = []
    description: str = ""
    config_defaults: Dict = {}

    def __init__(self, config: Optional[dict] = None):
        self.config: Dict = {**self.config_defaults, **(config or {})}
        self.status = DriverStatus(enabled=not self.simulated)

    # -- lifecycle (override in subclasses) ----------------------------------
    def probe(self) -> bool:
        """Detect whether the underlying hardware/backend exists. Return True
        if available (or for simulations). Auto-configures from the result."""
        return True

    def init(self) -> None:
        """Initialize resources. Raise on hard failure (bus catches + heals)."""

    def start(self) -> None:
        self.status.running = True

    def stop(self) -> None:
        self.status.running = False

    def update(self, dt: float) -> None:
        """Per-frame tick, called by the kernel loop for running drivers."""

    def auto_tune(self) -> dict:
        """Return recommended config derived from probe() (called by the bus)."""
        return {}

    def configure(self, cfg: dict) -> None:
        """Merge + apply manual configuration (wins over auto-tuned values)."""
        self.config.update(cfg)

    def diagnose(self) -> str:
        """One-line human-readable status detail (used by the Devices app)."""
        return self.status.detail

    # -- helpers --------------------------------------------------------------
    def _set(self, **kw) -> None:
        for k, v in kw.items():
            setattr(self.status, k, v)

    def _error(self, msg: str) -> None:
        self.status.available = False
        self.status.running = False
        self.status.health = 0
        self.status.last_error = msg
