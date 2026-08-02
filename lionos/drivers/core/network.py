"""Network driver — cached connectivity probe."""
from __future__ import annotations

import time

from ..framework import Driver


class NetworkDriver(Driver):
    name = "network"
    category = "core"
    description = "Network connectivity"

    def __init__(self, config=None):
        super().__init__(config)
        self._last = 0.0
        self._cached = False

    def probe(self) -> bool:
        self._set(available=True, detail="unknown")
        return True

    def online(self) -> bool:
        now = time.time()
        if now - self._last < 2.0:
            return self._cached
        self._last = now
        self._cached = self._check()
        return self._cached

    def _check(self) -> bool:
        try:
            import urllib.request
            urllib.request.urlopen("https://pypi.org", timeout=2)  # nosec B310 — hardcoded https connectivity probe
            return True
        except Exception:
            return False

    def diagnose(self) -> str:
        return "online" if self.online() else "offline"
