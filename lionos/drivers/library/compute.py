"""Compute drivers — math accel, RNG, quantum sim."""
from __future__ import annotations

import math
import os

from ..framework import Driver


class FPUDriver(Driver):
    name = "fpu"
    category = "compute"
    description = "Math co-processor (routes to math/numpy)"
    config_defaults = {"use_numpy": False}

    def probe(self):
        try:
            import numpy  # noqa: F401
            self._numpy = True
        except Exception:
            self._numpy = False
        return True

    def sqrt(self, x):
        return math.sqrt(x)

    def sin(self, x):
        return math.sin(x)

    def diagnose(self):
        return "numpy" if self._numpy else "math"


class RNGDriver(Driver):
    name = "rng"
    category = "compute"
    description = "Cryptographically secure random bits"

    def probe(self):
        return True

    def random_bytes(self, n: int) -> bytes:
        return os.urandom(n)

    def int_in(self, lo, hi):
        return int.from_bytes(os.urandom(4), "big") % (hi - lo + 1) + lo


class QuantumDriver(Driver):
    name = "quantum"
    category = "compute"
    simulated = True
    description = "Qubit register with Hadamard/CNOT"

    def __init__(self, config=None):
        super().__init__(config)
        self.state = [1.0 + 0.0j, 0.0 + 0.0j]

    def probe(self):
        return True

    def hadamard(self):
        s = self.state
        self.state = [s[0] / math.sqrt(2) + s[1] / math.sqrt(2),
                      s[0] / math.sqrt(2) - s[1] / math.sqrt(2)]
        return self.state

    def diagnose(self):
        return "1-qubit"
