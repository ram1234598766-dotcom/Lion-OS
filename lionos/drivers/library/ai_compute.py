"""AI/compute library drivers."""
from ..framework import Driver


class NpuEmulator(Driver):
    name = "npu"
    category = "ai"
    simulated = True
    description = "Route AI ops to ollama if present"
    def probe(self):
        try:
            import importlib.util
            self._has = importlib.util.find_spec("ollama") is not None
        except Exception:
            self._has = False
        return True


class VectorAccelerator(Driver):
    name = "vector_accel"
    category = "ai"
    description = "memoryview array ops"
    def probe(self):
        return True
    def sum(self, data):
        return sum(memoryview(data))
