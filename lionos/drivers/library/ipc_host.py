"""IPC / host-machine library drivers."""
import subprocess

from ..framework import Driver


class HostClipboard(Driver):
    name = "host_clipboard"
    category = "ipc"
    description = "Sync real host clipboard (guarded)"
    def probe(self):
        try:
            import pyperclip  # noqa: F401
            self._has = True
        except Exception:
            self._has = False
        return True
    def copy(self, text):
        if self._has:
            import pyperclip
            pyperclip.copy(text)
    def paste(self):
        if self._has:
            import pyperclip
            return pyperclip.paste()
        return ""


class SharedMemoryIpc(Driver):
    name = "shared_memory"
    category = "ipc"
    description = "multiprocessing.shared_memory segments"
    def probe(self):
        return True


class SubprocessPipe(Driver):
    name = "subprocess_pipe"
    category = "ipc"
    description = "Run host commands; capture output"
    def probe(self):
        return True
    def run(self, cmd, timeout=5, shell=False):
        """Run a command and capture stdout.

        Defaults to shell=False (argument list, no metacharacter expansion).
        Pass ``shell=True`` explicitly only when real shell semantics are
        required, since that enables command injection."""
        try:
            if shell and isinstance(cmd, str):
                return subprocess.run(cmd, shell=True, capture_output=True,  # nosec B602 — shell is opt-in only (terminal-style path); default shell=False
                                      text=True, timeout=timeout).stdout
            if isinstance(cmd, str):
                cmd = cmd.split()
            return subprocess.run(cmd, capture_output=True,
                                  text=True, timeout=timeout).stdout
        except Exception:
            return ""


class DemuxSignal(Driver):
    name = "demux"
    category = "ipc"
    description = "Split combined streams per subsystem"
    def probe(self):
        return True
    def split(self, stream, n):
        return [stream[i::n] for i in range(n)]


class Hypervisor(Driver):
    name = "hypervisor"
    category = "ipc"
    simulated = True
    description = "Spawn/freeze guest sub-instances"
    def probe(self):
        return True


class Vswitch(Driver):
    name = "vswitch"
    category = "ipc"
    simulated = True
    description = "Route between virtual machines"
    def probe(self):
        return True


class Kubelet(Driver):
    name = "kubelet"
    category = "ipc"
    description = "Manifest to desired background state"
    def probe(self):
        return True
    def desired(self, manifest):
        return manifest.get("replicas", 1)


class BusMaster(Driver):
    name = "bus_master"
    category = "ipc"
    description = "Priority arbitration of driver data"
    def __init__(self, config=None):
        super().__init__(config)
        self._queue = []
    def probe(self):
        return True
    def push(self, prio, data):
        self._queue.append((prio, data))
        self._queue.sort(key=lambda x: x[0])
    def pop(self):
        return self._queue.pop(0) if self._queue else None
