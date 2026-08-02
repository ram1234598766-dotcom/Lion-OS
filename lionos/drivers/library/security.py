"""Security/crypto library drivers."""
import hashlib
import os

from ..framework import Driver


class Fingerprint(Driver):
    name = "fingerprint"
    category = "security"
    description = "Hash-key-file profile auth"
    def probe(self):
        return True
    def verify(self, secret, stored_hash):
        return hashlib.sha256(secret.encode()).hexdigest() == stored_hash


class SmartCard(Driver):
    name = "smart_card"
    category = "security"
    description = "Key-file security token gate"
    def probe(self):
        return True


class SecureRNG(Driver):
    name = "secure_rng"
    category = "security"
    description = "os.urandom secure bits"
    def probe(self):
        return True
    def random_bytes(self, n):
        return os.urandom(n)


_SANDBOX_BLOCKED = (
    "__import__", "import ", "eval(", "exec(", "compile(",
    "open(", "__subclasses__", "__globals__", "__base__", "getattr",
    "input", "breakpoint",
)


class Sandbox(Driver):
    name = "sandbox"
    category = "security"
    description = "Restricted container for untrusted scripts"
    def probe(self):
        return True
    def run(self, code):
        # Python cannot be fully sandboxed via exec(); block the common escape
        # vectors (import, dunder traversal, eval/compile, I/O) so the sandbox
        # only runs benign arithmetic/string logic.
        if any(b in code for b in _SANDBOX_BLOCKED):
            return "blocked: disallowed construct"
        ns = {"__builtins__": {}}
        try:
            exec(code, ns)  # nosec B102 — gated by _SANDBOX_BLOCKED; not a true sandbox
            return "ok"
        except Exception as e:
            return f"err: {e}"


class CaStore(Driver):
    name = "ca_store"
    category = "security"
    description = "Manage/validate certificates"
    def __init__(self, config=None):
        super().__init__(config)
        self._certs = {}
    def probe(self):
        return True
    def add(self, name, cert):
        self._certs[name] = cert
    def validate(self, name):
        return name in self._certs


class IdsScanner(Driver):
    name = "ids"
    category = "security"
    description = "Scan logs; block malicious patterns"
    config_defaults = {"blocklist": ["rm -rf", "DROP TABLE"]}
    def probe(self):
        return True
    def check(self, line):
        return any(b in line for b in self.config["blocklist"])


class KeyLogger(Driver):
    name = "key_logger"
    category = "security"
    description = "Admin audit ledger of inputs"
    def __init__(self, config=None):
        super().__init__(config)
        self._ledger = []
    def probe(self):
        return True
    def log(self, entry):
        self._ledger.append(entry)


class AclManager(Driver):
    name = "acl"
    category = "security"
    description = "Role-based read/write/execute"
    config_defaults = {"roles": {
        "user": {"read", "write"},
        "admin": {"read", "write", "exec"},
    }}
    def probe(self):
        return True
    def can(self, role, perm):
        return perm in self.config["roles"].get(role, set())


class VulnSimulator(Driver):
    name = "vuln_sim"
    category = "security"
    simulated = True
    description = "Inject mock race conditions"
    def probe(self):
        return True


class MemoryScrubber(Driver):
    name = "memory_scrub"
    category = "security"
    description = "Zero freed buffers"
    def probe(self):
        return True
    def scrub(self, data):
        return b"\x00" * len(data)


class AntiTamper(Driver):
    name = "anti_tamper"
    category = "security"
    description = "Hash core files on startup"
    def probe(self):
        return True
    def hash_file(self, path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            h.update(f.read())
        return h.hexdigest()


class GdprScrubber(Driver):
    name = "gdpr_scrub"
    category = "security"
    description = "Wipe personal-data rows"
    def probe(self):
        return True
    def scrub_row(self, row, fields):
        return {k: ("[REDACTED]" if k in fields else v) for k, v in row.items()}


class BlackBox(Driver):
    name = "black_box"
    category = "security"
    description = "Write-only last-1000 commands"
    config_defaults = {"capacity": 1000}
    def __init__(self, config=None):
        super().__init__(config)
        self._buf = []
    def probe(self):
        return True
    def record(self, cmd):
        self._buf.append(cmd)
        if len(self._buf) > self.config["capacity"]:
            self._buf.pop(0)
