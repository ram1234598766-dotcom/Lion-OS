"""Append-only activity log — drives launcher Recents + Session Summary."""
from __future__ import annotations

import json
import os
import time
from collections import Counter

from .config import config_dir

_state_dir = config_dir()


def activity_path() -> str:
    return os.path.join(_state_dir, "activity.jsonl")


def log_event(event_type: str, detail: str = "") -> None:
    try:
        os.makedirs(os.path.dirname(activity_path()), exist_ok=True)
        with open(activity_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "type": event_type,
                                "detail": detail}) + "\n")
    except OSError:
        pass


def read_events(limit=None):
    """Events newest-first."""
    try:
        with open(activity_path(), "r", encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except (OSError, json.JSONDecodeError):
        return []
    rows.reverse()
    return rows if limit is None else rows[:limit]


def app_counts() -> dict:
    counts = Counter()
    try:
        with open(activity_path(), "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("type") == "app_launch":
                    counts[e.get("detail", "?")] += 1
    except OSError:
        pass
    return dict(counts)


def session_summary() -> str:
    counts = app_counts()
    if not counts:
        return ""
    top = ", ".join(f"{name} ×{n}" for name, n in
                    sorted(counts.items(), key=lambda kv: -kv[1])[:3])
    return f"Yesterday: {top}"
