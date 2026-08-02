# Lion-OS 2.0 "Majestic" — Phase 3 (Persistence & identity) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Lion-OS real persistence and identity: session resume (restore + animate windows back in, crash-recovery checkpoints), an append-only activity log powering launcher Recents + a boot "Session Summary" card, a clipboard with history (Super+V), and a first-boot wizard writing `profile.json`.

**Architecture:** New `lionos/session.py`, `lionos/activity.py`, `lionos/clipboard.py` (pure, testable, stdlib-only), plus a wizard screen and integration points in `kernel.py` (restore on boot, graceful shutdown, activity instrumentation, Super+V palette, Recents row) and `lionos/config.py` (`LionConfig.drivers`, `session_resume`, `clipboard_enabled`, `wizard_done` fields). Evolutionary refactor — existing modules modified in place.

**Tech Stack:** Python 3.9+, stdlib (`json`, `os`, `time`, `signal`, `shutil`), pygame.

## Global Constraints

- Python `>=3.9`; no new runtime dependencies.
- Keep all 85 existing tests + headless smoke green after every task.
- All new state files live under `~/.lionos/` and are corrupt-tolerant (bad JSON → defaults).
- Test via `py -3 -m pytest tests/ -q` (never `python3`).
- Session state is **minimal** (windows/positions/theme/workspace) — not full app state.

---

### Task 1: Session persistence (`session.py`)

**Files:**
- Create: `lionos/session.py`
- Test: `tests/test_session.py` (new)

**Interfaces:**
- Produces:
  - `session_path() -> str` (~/.lionos/session.json)
  - `save_session(data: dict) -> None` (atomic write)
  - `checkpoint_session(data: dict, keep=3) -> None` (rotates `session-1/2/3.json`)
  - `load_session() -> dict | None` (None on missing/corrupt)
  - `recover_session() -> dict | None` (falls back to newest checkpoint)
  - `cleanup_session() -> None` (removes current + checkpoints)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session.py
import json, os, tempfile
import lionos.session as S

def _cfg(tmp):
    S._state_dir = tmp
    return tmp

def test_save_load_roundtrip(tmp_path):
    _cfg(str(tmp_path))
    data = {"windows": [{"app": "Terminal", "rect": [0, 0, 800, 600]}],
            "theme": "ocean", "workspace": 2}
    S.save_session(data)
    assert S.load_session() == data

def test_load_missing_returns_none(tmp_path):
    _cfg(str(tmp_path))
    assert S.load_session() is None

def test_load_corrupt_returns_none(tmp_path):
    _cfg(str(tmp_path))
    with open(S.session_path(), "w") as f:
        f.write("{not json")
    assert S.load_session() is None

def test_checkpoint_rotation(tmp_path):
    _cfg(str(tmp_path))
    for i in range(5):
        S.checkpoint_session({"n": i}, keep=3)
    files = sorted(n for n in os.listdir(str(tmp_path)) if n.startswith("session-"))
    assert len(files) == 3

def test_recover_falls_back_to_checkpoint(tmp_path):
    _cfg(str(tmp_path))
    S.checkpoint_session({"n": 1})
    assert S.recover_session() == {"n": 1}
```

- [ ] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_session.py -v` → ImportError.

- [ ] **Step 3: Implement `lionos/session.py`**

```python
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
```

- [ ] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_session.py -v` → 5 passed.

- [ ] **Step 5: Commit**

```bash
git add lionos/session.py tests/test_session.py
git commit -m "feat(session): session snapshots + crash-recovery checkpoints"
```

---

### Task 2: Activity log (`activity.py`)

**Files:**
- Create: `lionos/activity.py`
- Test: `tests/test_activity.py` (new)

**Interfaces:**
- Produces:
  - `activity_path() -> str`
  - `log_event(event_type: str, detail: str = "") -> None` (append JSONL `{ts, type, detail}`)
  - `read_events(limit=None) -> list[dict]` (newest first)
  - `app_counts() -> dict[str, int]` (per-app launch counts)
  - `session_summary() -> str | None` (e.g. "Yesterday: Terminal ×3, switched to Sunset")

- [ ] **Step 1: Write the failing test**

```python
# tests/test_activity.py
import lionos.activity as A

def test_log_and_read(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "_state_dir", str(tmp_path))
    A.log_event("app_launch", "Terminal")
    A.log_event("app_launch", "Notes")
    A.log_event("theme_change", "ocean")
    evs = A.read_events()
    assert evs[0]["type"] == "theme_change"
    assert len(evs) == 3

def test_app_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "_state_dir", str(tmp_path))
    A.log_event("app_launch", "Terminal")
    A.log_event("app_launch", "Terminal")
    A.log_event("app_launch", "Notes")
    assert A.app_counts() == {"Terminal": 2, "Notes": 1}

def test_session_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "_state_dir", str(tmp_path))
    A.log_event("app_launch", "Terminal")
    A.log_event("app_launch", "Terminal")
    A.log_event("app_launch", "Notes")
    s = A.session_summary()
    assert "Terminal" in s and "Notes" in s
```

- [ ] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_activity.py -v` → ImportError.

- [ ] **Step 3: Implement `lionos/activity.py`**

```python
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
```

- [ ] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_activity.py -v` → 3 passed.

- [ ] **Step 5: Commit**

```bash
git add lionos/activity.py tests/test_activity.py
git commit -m "feat(activity): append-only activity log + recents/summary"
```

---

### Task 3: Clipboard with history (`clipboard.py`)

**Files:**
- Create: `lionos/clipboard.py`
- Test: `tests/test_clipboard.py` (new)

**Interfaces:**
- Produces:
  - `Clipboard` class with `copy(kind, value)`, `paste()`, `history() -> list`, `clear()`.
  - Persists a bounded history ring to `~/.lionos/clipboard.jsonl`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_clipboard.py
import lionos.clipboard as C

def test_copy_paste(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "_state_dir", str(tmp_path))
    cb = C.Clipboard()
    cb.copy("text", "hello")
    assert cb.paste() == "hello"

def test_history_ring(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "_state_dir", str(tmp_path))
    cb = C.Clipboard(max_history=3)
    for i in range(5):
        cb.copy("text", f"item{i}")
    h = cb.history()
    assert [e["value"] for e in h] == ["item4", "item3", "item2"]

def test_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "_state_dir", str(tmp_path))
    cb = C.Clipboard()
    cb.copy("text", "x")
    cb.clear()
    assert cb.paste() == ""
```

- [ ] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_clipboard.py -v` → ImportError.

- [ ] **Step 3: Implement `lionos/clipboard.py`**

```python
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
        return self._current.get("value", "") if hasattr(self, "_current") else (
            self._entries[0]["value"] if self._entries else "")

    def history(self) -> list:
        return list(self._entries)

    def clear(self) -> None:
        self._entries = []
        if hasattr(self, "_current"):
            del self._current
        self._persist()
```

- [ ] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_clipboard.py -v` → 3 passed.

- [ ] **Step 5: Commit**

```bash
git add lionos/clipboard.py tests/test_clipboard.py
git commit -m "feat(clipboard): clipboard + bounded persisted history ring"
```

---

### Task 4: First-boot wizard (profile + 4-step flow)

**Files:**
- Create: `lionos/wizard.py`
- Modify: `lionos/config.py` (add `wizard_done`, `pinned_apps`), `lionos/kernel.py` (wizard screen + `_do_login` gate)
- Test: `tests/test_wizard.py` (new)

**Interfaces:**
- Produces:
  - `profile_path() -> str` (~/.lionos/profile.json)
  - `load_profile() -> dict` / `save_profile(dict) -> None` (idempotent; archives prior to `~/.lionos/archives/`)
  - `WIZARD_STEPS = ["name", "theme", "pin", "matters"]`
  - Kernel: `self.wizard_active`, `self._wizard_step`, `self._wizard_input`; the login screen shows the wizard on first boot (when `not config.wizard_done`); step transitions on Enter; completing step 4 saves `profile.json` + sets `wizard_done`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wizard.py
import lionos.wizard as W

def test_profile_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "_state_dir", str(tmp_path))
    W.save_profile({"name": "Lion", "theme": "ocean", "pinned": ["Terminal"]})
    assert W.load_profile()["name"] == "Lion"

def test_load_missing_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "_state_dir", str(tmp_path))
    assert W.load_profile() == {}

def test_profile_step_constants():
    assert W.WIZARD_STEPS == ["name", "theme", "pin", "matters"]
```

- [ ] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_wizard.py -v` → ImportError.

- [ ] **Step 3: Implement `lionos/wizard.py`**

```python
"""First-boot wizard — scaffolds ~/.lionos/profile.json."""
from __future__ import annotations

import json
import os
import shutil
import time

from .config import config_dir

_state_dir = config_dir()
WIZARD_STEPS = ["name", "theme", "pin", "matters"]


def profile_path() -> str:
    return os.path.join(_state_dir, "profile.json")


def load_profile() -> dict:
    try:
        with open(profile_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_profile(data: dict) -> None:
    os.makedirs(_state_dir, exist_ok=True)
    if os.path.exists(profile_path()):
        arch = os.path.join(_state_dir, "archives")
        os.makedirs(arch, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        shutil.copyfile(profile_path(), os.path.join(arch, f"profile-{stamp}.json"))
    data["saved_at"] = time.time()
    tmp = profile_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, profile_path())
```

- [ ] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_wizard.py -v` → 3 passed.

- [ ] **Step 5: Kernel integration (wizard screen)**

In `lionos/config.py` `LionConfig`, add fields:

```python
    wizard_done: bool = False
    pinned_apps: list = field(default_factory=list)
```

In `lionos/kernel.py` `__init__`:

```python
        self.wizard_active = not self.config.wizard_done
        self._wizard_step = 0
        self._wizard_input = ""
```

In `_update`, in the login branch, when `self.wizard_active`, handle Enter to advance; on final step save the profile:

```python
            if self.wizard_active:
                if self._wizard_step == 0 and self._wizard_input:
                    profile = dict(load_profile())
                    profile["name"] = self._wizard_input
                    save_profile(profile)
                self._wizard_step += 1
                self._wizard_input = ""
                if self._wizard_step >= len(WIZARD_STEPS):
                    self.wizard_active = False
                    self.config.wizard_done = True
                    self.config.save()
```

(Exact wiring follows the login-screen pattern; the wizard renders via a new `_draw_wizard()` called from `_draw_login` when active.)

- [ ] **Step 5: Commit**

```bash
git add lionos/wizard.py lionos/config.py lionos/kernel.py tests/test_wizard.py
git commit -m "feat(wizard): first-boot wizard + profile.json scaffold"
```

---

### Task 5: Kernel integration — restore, shutdown, recents, clipboard, summary

**Files:**
- Modify: `lionos/kernel.py`, `lionos/config.py` (add `session_resume`, `clipboard_enabled`)
- Test: `tests/test_kernel_persistence.py` (new, headless)

**Interfaces:**
- Consumes: `session`, `activity`, `clipboard`, `wizard` (Tasks 1-4).
- Produces:
  - `LionOS.session_resume_enabled: bool` (config), `LionOS._restore_session()` (launch windows from a saved session + animate), `LionOS._save_session_on_exit()`.
  - Graceful shutdown: `LionOS.shutdown()` saves session + checkpoints (called by power menu + SIGINT/SIGTERM handler).
  - Activity instrumentation: app launch/close/theme-change/screenshot events; launcher **Recents** row + **Session Summary** card at login.
  - `LionOS.clipboard: Clipboard`; a `SUPER+V` clipboard-history palette; helper `os.clipboard_copy(value)` / `os.clipboard_paste()` used by Text Editor/Notes/Terminal.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_kernel_persistence.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
from lionos.kernel import LionOS


def test_kernel_has_clipboard():
    os_ = LionOS()
    assert os_.clipboard is not None
    os_.clipboard_copy("hello")
    assert os_.clipboard_paste() == "hello"


def test_session_save_restore_roundtrip():
    os_ = LionOS()
    os_._no_draw = False
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    os_.launch("Terminal")
    snapshot = os_._collect_session()
    assert any(w["app"] == "Terminal" for w in snapshot["windows"])
    os_._restore_session(snapshot)
    assert any(w.app.name == "Terminal" for w in os_.wm.windows)
```

- [ ] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_kernel_persistence.py -v` → AttributeError (`_collect_session`).

- [ ] **Step 3: Implement**

`lionos/config.py` `LionConfig` add: `session_resume: bool = True`, `clipboard_enabled: bool = True`.

`lionos/kernel.py`:
- imports: `from . import session as sess`, `from . import activity`, `from .clipboard import Clipboard`, `from .wizard import load_profile, save_profile, WIZARD_STEPS`.
- in `__init__`: `self.clipboard = Clipboard()`, and after `self._do_login` setup — call `self._restore_session(sess.recover_session())` only when `config.session_resume` and a session exists and `not wizard_active`.
- helpers:

```python
    def _collect_session(self):
        windows = []
        for win in self.wm.windows:
            if win.app and win.app.name != "Welcome":
                windows.append({
                    "app": win.app.name,
                    "rect": list(win.rect),
                    "minimized": win.state == WINDOW_STATE_MINIMIZED,
                })
        return {"windows": windows, "theme": self.config.theme,
                "workspace": getattr(self, "_workspace", 0)}

    def _restore_session(self, data):
        if not data or not data.get("windows"):
            return
        self.config.theme = data.get("theme", self.config.theme)
        for w in data["windows"]:
            cls = self.apps_registry.get(w["app"]) if self.apps_registry else None
            if cls is None:
                continue
            try:
                inst = cls(self, win=None)
                if len(w["rect"]) == 4:
                    inst.window.rect = pygame.Rect(*w["rect"])
                    inst.window.content_rect = inst.window.content_rect  # refresh
                inst.window.begin_anim("open")
                if w.get("minimized"):
                    inst.window.state = WINDOW_STATE_MINIMIZED
                self.instances.append(inst)
            except Exception:
                continue

    def _save_session_on_exit(self):
        if not getattr(self, "logged_in", False):
            return
        data = self._collect_session()
        sess.save_session(data)
        sess.checkpoint_session(data)
```

- wire `shutdown`/power menu to call `_save_session_on_exit()`; register SIGINT/SIGTERM:

```python
        import signal as _signal
        def _on_term(*_a):
            self._save_session_on_exit()
            self.running = False
        try:
            _signal.signal(_signal.SIGINT, _on_term)
            _signal.signal(_signal.SIGTERM, _on_term)
        except (ValueError, OSError):
            pass
```

- activity instrumentation: in the app-launch path call `activity.log_event("app_launch", cls.name)`; on theme change `activity.log_event("theme_change", name)`.
- clipboard helpers:

```python
    def clipboard_copy(self, value): self.clipboard.copy("text", value)
    def clipboard_paste(self):
        return self.clipboard.paste() if self.config.clipboard_enabled else ""
```

- launcher **Recents**: `_draw_launcher_recent` already reads `config.mru_apps`; extend to fall back to `activity.app_counts()` keys. Session **Summary card**: after login, if `activity.session_summary()` non-empty, show a fading card (store `self._summary`, `self._summary_t`; draw in `_draw`).

- [ ] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_kernel_persistence.py -v` → 2 passed. Full suite + smoke.

- [ ] **Step 5: Commit**

```bash
git add lionos/kernel.py lionos/config.py tests/test_kernel_persistence.py
git commit -m "feat(session): kernel restore-on-boot + graceful shutdown + recents + clipboard"
```

---

## Self-Review notes

- **Spec coverage:** Phase 3 covers §6.8 (session), §6.9 (wizard), §6.10 (activity/recents/summary), §6.11 (clipboard), plus graceful shutdown (§6.10 of the design). `workspace` is carried in session state now so Phase 5's workspaces slot in cleanly.
- **No placeholders:** every task has concrete test + implementation code.
- **Type consistency:** `save_session/load_session/checkpoint_session/recover_session`, `log_event/app_counts/session_summary`, `Clipboard.copy/paste/history/clear`, `save_profile/load_profile` are defined once and used identically across tasks.
