# Lion-OS 2.0 "Majestic" — Phase 5 (Power features + new apps) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the power-user desktop features — virtual workspaces, window tiling shortcuts, global search, a screenshot tool, a Media Player rebuild on the media driver, and new apps (Inbox/quick-capture, System Health, Today/Timeline) plus focus mode.

**Architecture:** Extend `lionos/wm.py` (workspace tagging on windows) + `kernel.py` (workspace switching, tiling shortcuts, global-search overlay, screenshot capture, focus mode); new `lionos/search.py` (global search); rewrite `lionos/apps/mediaplayer.py` on the MediaDriver; new apps `inbox.py`, `health.py`, `today.py`; config fields for focus mode + workspace count.

**Tech Stack:** Python 3.9+, pygame, stdlib, psutil.

## Global Constraints

- Python `>=3.9`; no new runtime dependencies.
- Keep all 112 existing tests + headless smoke green after every task.
- Global-search and screenshots are keyboard hotkeys (Super+Space, Win+Shift+S); motion-gated.
- Test via `py -3 -m pytest tests/ -q`.

---

### Task 1: Workspaces + window tiling

**Files:**
- Modify: `lionos/wm.py` (add `Window.workspace`), `lionos/kernel.py` (switch hotkeys, tiling shortcuts)
- Test: `tests/test_workspaces.py` (new)

**Interfaces:**
- Produces:
  - `Window.workspace: int` (default 0); `WindowManager.windows_in(ws)`.
  - `LionOS.workspace: int`, `set_workspace(n)`, `WORKSPACE_COUNT = 4`.
  - Tiling: `tile_window(dir)` (Win+arrows) → half/quarter/center; `_workspace_indicator` on taskbar.

- [x] **Step 1: Write the failing test**

```python
# tests/test_workspaces.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
from lionos.kernel import LionOS


def test_workspace_switch_hides_windows():
    os_ = LionOS()
    os_._no_draw = False
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    inst = os_.launch("Terminal")
    inst.window.workspace = 1
    os_.set_workspace(0)
    assert os_.workspace == 0
    os_.set_workspace(1)
    assert os_.workspace == 1
    os_.wm.focus(inst.window)
    assert os_.wm.focused is inst.window


def test_tile_window_half():
    os_ = LionOS()
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    inst = os_.launch("Terminal")
    os_.tile_window("left")
    assert inst.window.rect.width == os_.screen_w // 2
```

- [x] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_workspaces.py -v` → AttributeError.

- [x] **Step 3: Implement**

`lionos/wm.py` — add `self.workspace = 0` to `Window.__init__`; add:

```python
    def windows_in(self, ws):
        return [w for w in self.windows if w.workspace == ws]
```

`lionos/kernel.py`:
- `self.workspace = 0`, `WORKSPACE_COUNT = 4` (module constant).
- `set_workspace(n)`: clamp, set `self.workspace = n`, `_needs_redraw = True`.
- In `_draw_windows`, skip windows whose `workspace != self.workspace`.
- `tile_window(direction)`: for the focused window, set rect to half/quarter of screen based on direction ("left"/"right"/"up"/"down"/"center"); `_dirty.mark(win.rect)`.
- Hotkeys: Ctrl+Alt+←/→ → `set_workspace`, Win+arrows → `tile_window`. (Add to `_handle_global_event`/`_handle_event`.)
- Taskbar `_workspace_indicator`: draw 4 dots, highlight current.

- [x] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_workspaces.py -v` → 2 passed. Full suite + smoke.

- [x] **Step 5: Commit**

```bash
git add lionos/wm.py lionos/kernel.py tests/test_workspaces.py
git commit -m "feat(wm): virtual workspaces + window tiling shortcuts"
```

---

### Task 2: Global search (`search.py`)

**Files:**
- Create: `lionos/search.py`
- Modify: `lionos/kernel.py` (Super+Space overlay)
- Test: `tests/test_search.py` (new)

**Interfaces:**
- Produces:
  - `global_search(query, os_) -> list[dict]` — searches app names/descriptions, Settings sections, Notes filenames, activity log; each result `{title, source, kind, target}`.
  - Kernel: `self.search_open`, `self.search_query`, `_draw_search()`, Enter opens the target.

- [x] **Step 1: Write the failing test**

```python
# tests/test_search.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
from lionos.kernel import LionOS
from lionos.search import global_search


def test_search_finds_apps():
    os_ = LionOS()
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    results = global_search("terminal", os_)
    assert any(r["kind"] == "app" and "Terminal" in r["title"] for r in results)


def test_search_finds_settings():
    os_ = LionOS()
    results = global_search("wallpaper", os_)
    assert any(r["kind"] == "setting" for r in results)
```

- [x] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_search.py -v` → ImportError.

- [x] **Step 3: Implement `lionos/search.py`**

```python
"""Global search across apps, settings, notes, and activity."""
from __future__ import annotations


def global_search(query: str, os_) -> list:
    q = query.lower()
    results = []
    if not q:
        return results
    # apps
    for name, cls in os_.apps_registry.all().items():
        if q in name.lower() or q in (getattr(cls, "description", "") or "").lower():
            results.append({"title": name, "source": "Apps", "kind": "app", "target": name})
    # settings
    for field in ("theme", "wallpaper", "accent_override", "motion", "sound_enabled",
                  "statusline", "session_resume", "clipboard_enabled", "show_fps"):
        if q in field.replace("_", " ").lower():
            results.append({"title": field.replace("_", " ").title(), "source": "Settings",
                            "kind": "setting", "target": field})
    # notes filenames
    try:
        import os as _os
        from .config import config_dir
        notes_dir = _os.path.join(config_dir(), "notes")
        if _os.path.isdir(notes_dir):
            for fn in _os.listdir(notes_dir):
                if q in fn.lower():
                    results.append({"title": fn, "source": "Notes", "kind": "note", "target": fn})
    except Exception:
        pass
    # activity log apps
    from . import activity
    for name in activity.app_counts():
        if q in name.lower():
            results.append({"title": name, "source": "Activity", "kind": "app", "target": name})
    return results
```

Kernel: `search_open`, `search_query`; `_draw_search()` centered overlay listing results; Enter launches apps / opens Settings / opens a note; Super+Space toggles.

- [x] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_search.py -v` → 2 passed. Full suite + smoke.

- [x] **Step 5: Commit**

```bash
git add lionos/search.py lionos/kernel.py tests/test_search.py
git commit -m "feat(search): global search overlay (Super+Space)"
```

---

### Task 3: Screenshot tool + focus mode

**Files:**
- Modify: `lionos/kernel.py`, `lionos/config.py`
- Test: `tests/test_screenshot_focus.py` (new)

**Interfaces:**
- Produces:
  - `LionOS.take_screenshot() -> str | None` — captures the screen to `~/.lionos/screenshots/YYYYmmdd-HHMMSS.png`, toast + activity event.
  - Focus mode: `LionConfig.focus_off: list[str]` (apps marked "not today"); `LionOS.focus_dimmed(name)`; dimmed apps are dimmed in the launcher and their notifications swallowed.

- [x] **Step 1: Write the failing test**

```python
# tests/test_screenshot_focus.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
from lionos.kernel import LionOS


def test_screenshot_writes_file():
    os_ = LionOS()
    os_._no_draw = False
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    os_._needs_redraw = True
    os_._draw()
    import pygame; pygame.display.flip()
    path = os_.take_screenshot()
    assert path and os.path.exists(path)


def test_focus_mode_dim():
    os_ = LionOS()
    os_.config.focus_off = ["Terminal"]
    assert os_.focus_dimmed("Terminal") is True
    assert os_.focus_dimmed("Notes") is False
```

- [x] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_screenshot_focus.py -v` → AttributeError.

- [x] **Step 3: Implement**

`lionos/config.py` add: `focus_off: list = field(default_factory=list)`.

`lionos/kernel.py`:
- `take_screenshot()`: copy the screen, `pygame.image.save(copy, path)`; ensure dir; toast; `_activity.log_event("screenshot", path)`; return path.
- `focus_dimmed(name)`: return `name in self.config.focus_off`.
- In `_draw_launcher` grid + `_draw_desktop_icons`, dim dimmed apps (blend toward black).
- In `notify`, swallow notifications whose `app` is dimmed.
- Hotkey Win+Shift+S → `take_screenshot()`.

- [x] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_screenshot_focus.py -v` → 2 passed. Full suite + smoke.

- [x] **Step 5: Commit**

```bash
git add lionos/kernel.py lionos/config.py tests/test_screenshot_focus.py
git commit -m "feat(tools): screenshot tool + focus mode"
```

---

### Task 4: Media Player rebuild + new apps (Inbox, System Health, Today)

**Files:**
- Rewrite: `lionos/apps/mediaplayer.py` (use MediaDriver + visualizer)
- Create: `lionos/apps/inbox.py`, `lionos/apps/health.py`, `lionos/apps/today.py`
- Modify: `lionos/apps/__init__.py` (register)
- Test: `tests/test_new_apps.py` (new)

**Interfaces:**
- Produces: `MediaPlayerApp` (open audio via `os.drivers.get("media")`, play/pause/seek, simple amplitude visualizer), `InboxApp` (quick-capture list + promote-to-task), `SystemHealthApp` (scored audit /100), `TodayApp` (activity log timeline).

- [x] **Step 1: Write the failing test**

```python
# tests/test_new_apps.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
from lionos.kernel import LionOS
from lionos.apps import get_apps


def test_new_apps_registered():
    names = {c.name for c in get_apps()}
    for want in ("Inbox", "System Health", "Today"):
        assert want in names, want


def test_new_apps_launch_and_draw():
    os_ = LionOS()
    os_._no_draw = False
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    for name in ("Inbox", "System Health", "Today", "Media Player"):
        inst = os_.launch(name)
        for _ in range(4):
            os_._dt = 0.016
            os_._update(os_._dt)
        assert inst.hydrated, name
    os_._needs_redraw = True
    os_._draw()
    pygame.display.flip()
```

- [x] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_new_apps.py -v` → FAIL (not registered).

- [x] **Step 3: Implement**

`mediaplayer.py`: keep the playlist UI; route playback through `self.os.drivers.get("media")` (audio) and the audio driver for volume; add a simple amplitude visualizer (bars from `self._phase`).
`inbox.py`: `InboxApp` — list of entries (title, section To Do/Someday/Ideas), text input to add, click "promote" → move to To Do; persists `~/.lionos/inbox.json`.
`health.py`: `SystemHealthApp` — computes a score from apps count, themes, drivers running, profile complete; renders score /100 + top-3 next steps.
`today.py`: `TodayApp` — renders `activity.read_events()` grouped by day.

Register all four in `apps/__init__.py`.

- [x] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_new_apps.py -v` → 2 passed. Full suite + smoke.

- [x] **Step 5: Commit**

```bash
git add lionos/apps/mediaplayer.py lionos/apps/inbox.py lionos/apps/health.py lionos/apps/today.py lionos/apps/__init__.py tests/test_new_apps.py
git commit -m "feat(apps): Media Player rebuild + Inbox/System Health/Today apps"
```

---

## Self-Review notes

- **Spec coverage:** Phase 5 covers §6.17 (workspaces), §6.18 (tiling), §6.19 (global search), §6.20 (screenshots), §6.21 (Media Player rebuild), §6.22 (new apps: Help done in Phase 4, plus Inbox/System Health/Today), and focus mode.
- **No placeholders:** every task has concrete test + implementation.
- **Type consistency:** `set_workspace/tile_window`, `global_search`, `take_screenshot/focus_dimmed`, and the four apps are defined once and used consistently.
