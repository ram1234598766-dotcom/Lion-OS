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
        ns = {"__builtins__": {}} if self.config["sandbox"] else {}
        try:
            exec(code, ns)
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
