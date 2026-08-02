"""Session persistence — minimal desktop-state snapshots with crash recovery.

State files live under ``~/.lionos/``: ``session.json`` (latest, atomic write)
plus rotated ``session-1..3.json`` checkpoints. Every read is corrupt-tolerant.
"""
from __future__ import annotations

import json
import os
import shutil
import time

from .config import config_dir

_state_dir = config_dir()          # overridable in tests


def session_path() -> str:
    return os.path.join(_state_dir, "session.json")


def _checkpoint_path(n: int) -> str:
    return os.path.join(_state_dir, f"session-{n}.json")


def _atomic_write(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _read(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def save_session(data: dict) -> None:
    data["saved_at"] = time.time()
    _atomic_write(session_path(), data)


def checkpoint_session(data: dict, keep: int = 3) -> None:
    """Rotate checkpoints so the last ``keep`` survive a crash mid-write."""
    for i in range(keep - 1, 0, -1):
        src, dst = _checkpoint_path(i), _checkpoint_path(i + 1)
        if os.path.exists(src):
            shutil.copyfile(src, dst)
    data["saved_at"] = time.time()
    _atomic_write(_checkpoint_path(1), data)
    # prune beyond keep
    for i in range(keep + 1, 6):
        p = _checkpoint_path(i)
        if os.path.exists(p):
            os.remove(p)


def load_session():
    return _read(session_path())


def recover_session():
    """Latest session, else newest checkpoint."""
    data = _read(session_path())
    if data:
        return data
    for i in range(1, 6):
        data = _read(_checkpoint_path(i))
        if data:
            return data
    return None


def cleanup_session() -> None:
    for path in [session_path()] + [_checkpoint_path(i) for i in range(1, 6)]:
        if os.path.exists(path):
            os.remove(path)
