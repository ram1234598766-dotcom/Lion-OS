"""Driver bus: registers drivers, orders by dependency, probes/auto-tunes/init/
starts them at boot, and exposes a device tree + auto-config snapshot."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from .framework import Driver, DriverStatus


@dataclass
class BootProbeLine:
    name: str
    state: str      # ok | warn | offline | sim
    detail: str = ""


class DriverBus:
    def __init__(self, drivers: Optional[List[Driver]] = None):
        self._drivers: Dict[str, Driver] = {}
        for d in drivers or []:
            self.register(d)
        self._boot_time = time.time()

    # -- registration --------------------------------------------------------
    def register(self, driver: Driver) -> None:
        self._drivers[driver.name] = driver

    def get(self, name: str) -> Optional[Driver]:
        return self._drivers.get(name)

    def all(self) -> List[Driver]:
        names = self._topo()
        return [self._drivers[n] for n in names]

    def by_category(self) -> Dict[str, List[Driver]]:
        out: Dict[str, List[Driver]] = {}
        for d in self.all():
            out.setdefault(d.category, []).append(d)
        return out

    def _topo(self) -> List[str]:
        """Dependency-ordered names (parents before children)."""
        visited, order = set(), []

        def visit(name):
            if name in visited:
                return
            visited.add(name)
            d = self._drivers.get(name)
            if d:
                for dep in d.depends:
                    visit(dep)
                order.append(name)

        for n in self._drivers:
            visit(n)
        return order

    # -- lifecycle ------------------------------------------------------------
    def probe_all(self) -> List[BootProbeLine]:
        lines = []
        for d in self.all():
            if not d.status.enabled:
                lines.append(BootProbeLine(d.name, "offline", "disabled"))
                continue
            try:
                ok = d.probe()
            except Exception as e:                      # pragma: no cover
                d._error(f"probe failed: {e}")
                ok = False
            if not ok:
                d.status.available = False
                lines.append(BootProbeLine(d.name, "offline", "not detected"))
                continue
            # auto-tune: manual overrides win over auto values
            tuned = d.auto_tune() or {}
            d.configure(tuned)
            try:
                d.init()
                d.start()
                d._set(available=True, running=True, health=100,
                       detail=d.diagnose() or "ok", last_error="")
            except Exception as e:
                d._error(str(e))
                lines.append(BootProbeLine(d.name, "warn", f"init failed: {e}"))
                continue
            state = "sim" if d.simulated else "ok"
            lines.append(BootProbeLine(d.name, state, d.diagnose() or "ok"))
        return lines

    def re_probe(self, name: str) -> BootProbeLine:
        d = self.get(name)
        if d is None:
            return BootProbeLine(name, "warn", "unknown driver")
        d.stop()
        d.status = DriverStatus(enabled=not d.simulated)
        lines = self.probe_all()
        return next((l for l in lines if l.name == name),
                    BootProbeLine(name, "warn", "no line"))

    def enable(self, name: str) -> None:
        d = self.get(name)
        if d:
            d.status.enabled = True

    def disable(self, name: str) -> None:
        d = self.get(name)
        if d:
            d.stop()
            d.status.enabled = False
            d.status.running = False

    def update(self, dt: float) -> None:
        for d in self.all():
            if d.status.running:
                try:
                    d.update(dt)
                except Exception:
                    pass

    def stop_all(self) -> None:
        for d in self.all():
            try:
                d.stop()
            except Exception:
                pass

    # -- reporting ------------------------------------------------------------
    def device_tree(self) -> List[dict]:
        out = []
        for cat, drivers in self.by_category().items():
            out.append({
                "category": cat,
                "drivers": [{
                    "name": d.name,
                    "status": d.status.to_dict(),
                    "simulated": d.simulated,
                    "description": d.description,
                    "config": dict(d.config),
                } for d in drivers],
            })
        return out

    def auto_config_snapshot(self) -> dict:
        return {
            "written_at": time.time(),
            "drivers": {d.name: {"name": d.name, "config": dict(d.config)}
                        for d in self.all()},
        }
