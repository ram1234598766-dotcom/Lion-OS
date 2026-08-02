"""Compliance/auditing library drivers."""
from ..framework import Driver


class AuditLedger(Driver):
    name = "audit_ledger"
    category = "compliance"
    description = "Append-only audit log"
    def __init__(self, config=None):
        super().__init__(config)
        self._entries = []
    def probe(self):
        return True
    def append(self, entry):
        self._entries.append(entry)
