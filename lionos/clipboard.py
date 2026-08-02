"""Cross-app clipboard with a bounded, persisted history ring."""
from __future__ import annotations

import json
import os

from .config import config_dir

_state_dir = config_dir()


def _history_path() -> str:
    return os.path.join(_state_dir, "clipboard.jsonl")


class Clipboard:
    def __init__(self, max_history: int = 20):
        self._max = max_history
        self._entries = self._load()
        if not hasattr(self, "_current"):
            self._current = {}

    def _load(self) -> list:
        try:
            with open(_history_path(), "r", encoding="utf-8") as f:
                return [json.loads(line) for line in f if line.strip()]
        except (OSError, json.JSONDecodeError):
            return []

    def _persist(self) -> None:
        try:
            os.makedirs(os.path.dirname(_history_path()), exist_ok=True)
            with open(_history_path(), "w", encoding="utf-8") as f:
                for e in self._entries:
                    f.write(json.dumps(e) + "\n")
        except OSError:
            pass

    def copy(self, kind: str, value: str) -> None:
        self._current = {"kind": kind, "value": value}
        self._entries.insert(0, self._current)
        del self._entries[self._max:]
        self._persist()

    def paste(self):
        if self._current:
            return self._current.get("value", "")
        return self._entries[0]["value"] if self._entries else ""

    def history(self) -> list:
        return list(self._entries)

    def clear(self) -> None:
        self._entries = []
        self._current = {}
        self._persist()
