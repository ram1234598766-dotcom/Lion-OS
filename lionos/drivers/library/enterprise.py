"""Enterprise/archival library drivers."""
import zipfile

from ..framework import Driver


class JobQueue(Driver):
    name = "job_queue"
    category = "enterprise"
    description = "Priority batch queue execution"
    def __init__(self, config=None):
        super().__init__(config)
        self._jobs = []
    def probe(self):
        return True
    def enqueue(self, priority, job):
        self._jobs.append((priority, job))
        self._jobs.sort(key=lambda x: x[0])
    def next_job(self):
        return self._jobs.pop(0) if self._jobs else None


class FpgaLoader(Driver):
    name = "fpga"
    category = "enterprise"
    simulated = True
    description = "Parse config to reconfigure virtual circuits"
    def probe(self):
        return True


class SymbolicDebugger(Driver):
    name = "symbolic_debugger"
    category = "enterprise"
    simulated = True
    description = "Line stepping + breakpoints"
    def probe(self):
        return True


class TimeMachineBackup(Driver):
    name = "time_machine"
    category = "enterprise"
    description = "Zip snapshots of a folder"
    def probe(self):
        return True
    def snapshot(self, folder, out):
        with zipfile.ZipFile(out, "w") as z:
            z.write(folder)
        return out


class NvmeOverFabrics(Driver):
    name = "nvme_of"
    category = "enterprise"
    simulated = True
    description = "Block-storage-over-socket proxy"
    def probe(self):
        return True
