"""Developer-tools library drivers."""
from ..framework import Driver


class JitProxy(Driver):
    name = "jit_proxy"
    category = "dev"
    description = "Tokenize + exec user scripts (sandboxed)"
    config_defaults = {"sandbox": True}
    def probe(self):
        return True
    def run(self, code):
        if self.config["sandbox"]:
            from .security import _SANDBOX_BLOCKED
            if any(b in code for b in _SANDBOX_BLOCKED):
                return "blocked: disallowed construct"
            ns = {"__builtins__": {}}
        else:
            ns = {}
        try:
            exec(code, ns)  # nosec B102 — gated by _SANDBOX_BLOCKED when sandboxed
            return "ok"
        except Exception as e:
            return f"err: {e}"


class MacroRecorder(Driver):
    name = "macro_recorder"
    category = "dev"
    description = "Record/replay keystrokes + commands"
    def __init__(self, config=None):
        super().__init__(config)
        self._tape = []
    def probe(self):
        return True
    def record(self, step):
        self._tape.append(step)
    def replay(self):
        return list(self._tape)
