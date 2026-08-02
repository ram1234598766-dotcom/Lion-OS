# Lion-OS 2.0 "Majestic" — Phase 4 (Catalog & chrome) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the shell feel like a real desktop: a categorized app catalog launcher, a notification center, polished sound design (via the audio driver), a wallpaper gallery + accent picker, a system tray, toggleable statusline widgets, motion-level accessibility, and a self-documenting Help app.

**Architecture:** Extend `kernel.py` (catalog launcher, notification center, tray, statusline, motion gating, accent/wallpaper live-switch), `widgets.py` (NotificationCenter widget), new `lionos/sound.py` (sound theme on the AudioDriver), `lionos/apps/help.py` (Help app), and `lionos/theme.py` (accent override helper). Config fields on `LionConfig` (motion, statusline widgets, accent, wallpaper, sound).

**Tech Stack:** Python 3.9+, pygame, existing psutil.

## Global Constraints

- Python `>=3.9`; no new runtime dependencies.
- Keep all 101 existing tests + headless smoke green after every task.
- All animations gated behind the motion setting (Full/Reduced/None).
- Sound is fully guarded (no audio device → silent).
- Test via `py -3 -m pytest tests/ -q`.

---

### Task 1: Sound design (`sound.py`)

**Files:**
- Create: `lionos/sound.py`
- Modify: `lionos/kernel.py` (play SFX on boot/open/close/toast/screenshot), `lionos/config.py` (`sound_enabled`)
- Test: `tests/test_sound.py` (new)

**Interfaces:**
- Produces:
  - `SoundTheme` class wrapping the audio driver: `__init__(self, audio)`; `play(id)` maps ids to `audio.play_sfx`; `set_volume(v)`; `enabled` flag.
  - Kernel: `self.sound: SoundTheme`; calls `self.sound.play("open")` on window open, `"close"` on close, `"toast"` on toast, `"boot"` once booted.

- [x] **Step 1: Write the failing test**

```python
# tests/test_sound.py
from lionos.sound import SoundTheme


class FakeAudio:
    def __init__(self):
        self.calls = []
    def play_sfx(self, sid):
        self.calls.append(sid)
    def set_volume(self, v):
        pass


def test_sound_theme_plays():
    a = FakeAudio()
    s = SoundTheme(a)
    s.enabled = True
    s.play("open")
    assert a.calls == ["open"]


def test_sound_disabled_noop():
    a = FakeAudio()
    s = SoundTheme(a)
    s.enabled = False
    s.play("open")
    assert a.calls == []
```

- [x] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_sound.py -v` → ImportError.

- [x] **Step 3: Implement `lionos/sound.py`**

```python
"""Sound theme — plays guarded UI sounds through the audio driver."""
from __future__ import annotations


class SoundTheme:
    def __init__(self, audio=None):
        self._audio = audio
        self.enabled = True
        self.volume = 0.8

    def set_volume(self, v: float) -> None:
        self.volume = max(0.0, min(1.0, v))
        if self._audio is not None:
            self._audio.set_volume(self.volume)

    def play(self, sound_id: str) -> None:
        if not self.enabled or self._audio is None:
            return
        try:
            self._audio.play_sfx(sound_id)
        except Exception:
            pass
```

- [x] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_sound.py -v` → 2 passed.

- [x] **Step 5: Wire into kernel**

`lionos/config.py` add: `sound_enabled: bool = True`.

`lionos/kernel.py`:
- import `from .sound import SoundTheme`
- in `__init__` after `self.clipboard = Clipboard()`: `self.sound = SoundTheme(self.drivers.get("audio"))`, `self.sound.enabled = self.config.sound_enabled`.
- `show_toast` → `self.sound.play("toast")`.
- on boot completion (`self.booted = True`) → `self.sound.play("boot")`.
- on window open (in `launch`, after app created) → `self.sound.play("open")`.
- on window close → `self.sound.play("close")` (in the remove path).

- [x] **Step 6: Commit**

```bash
git add lionos/sound.py lionos/kernel.py lionos/config.py tests/test_sound.py
git commit -m "feat(sound): guarded sound theme on the audio driver"
```

---

### Task 2: Notification center

**Files:**
- Modify: `lionos/widgets.py` (add `NotificationCenter`), `lionos/kernel.py` (notify API, center panel, badge dots), `lionos/config.py`
- Test: `tests/test_notifications.py` (new)

**Interfaces:**
- Produces:
  - `kernel.notify(title, body, app=None, kind="info", action=None)` — adds a `Notification` with a timeout; persists in `self._notifications`.
  - `NotificationCenter` widget: `update(dt)`, `draw(surface, rect, theme)`, `clear_all()`, list of active notifications.
  - Taskbar/launcher icon badge dots from unread counts.

- [x] **Step 1: Write the failing test**

```python
# tests/test_notifications.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
from lionos.kernel import LionOS


def test_notify_adds_and_expires():
    os_ = LionOS()
    os_.notify("Title", "Body")
    assert len(os_._notifications) == 1
    os_._notifications[0].timeout = 0.001
    os_._update_notifications(0.01)
    assert len(os_._notifications) == 0


def test_notify_clear_all():
    os_ = LionOS()
    os_.notify("A", "1")
    os_.notify("B", "2")
    os_.clear_notifications()
    assert len(os_._notifications) == 0
```

- [x] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_notifications.py -v` → AttributeError.

- [x] **Step 3: Implement**

`lionos/widgets.py` add:

```python
class Notification:
    def __init__(self, title, body, app="", kind="info", timeout=5.0):
        self.title, self.body, self.app = title, body, app
        self.kind = kind
        self.timeout = timeout
        self.done = False
        self.t = 0.0
    def update(self, dt):
        self.t += dt
        if self.t >= self.timeout:
            self.done = True
```

`lionos/kernel.py`:
- `self._notifications: list[Notification] = []`, `self.notification_center_open = False`
- `def notify(self, title, body, app="", kind="info", action=None):` append a `Notification`, `self._needs_redraw = True`.
- `def clear_notifications(self): self._notifications = []`
- `_update_notifications(dt)`: update each, drop done.
- call `_update_notifications(dt)` in `_update` (logged-in path).
- draw a notification-center panel when open (list notifications, click to clear).
- `self.sound.play("toast")` in `notify`.

- [x] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_notifications.py -v` → 2 passed. Full suite + smoke.

- [x] **Step 5: Commit**

```bash
git add lionos/widgets.py lionos/kernel.py tests/test_notifications.py
git commit -m "feat(notifications): notification center + notify API"
```

---

### Task 3: Wallpaper gallery + accent picker + motion settings

**Files:**
- Modify: `lionos/theme.py` (accent override), `lionos/kernel.py` (wallpapers, accent apply, motion gating), `lionos/config.py`
- Test: `tests/test_theme_motion.py` (new)

**Interfaces:**
- Produces:
  - `LionConfig.wallpaper: str` (extend values: gradient|aurora|grid|dots|mountain), `LionConfig.accent_override: str | None`, `LionConfig.motion: str` (full|reduced|none).
  - `kernel.wallpaper_names()`, `kernel.apply_accent(rgb)`, `kernel.motion_ok()` (helper to gate animations).
  - `theme.accented(rgb)` returns a theme copy with accent/accent2/icon gradients overridden.

- [x] **Step 1: Write the failing test**

```python
# tests/test_theme_motion.py
from lionos.theme import THEMES, accented
from lionos.kernel import LionOS


def test_accent_override_changes_palette():
    t = accented(THEMES["dark"], (255, 0, 0))
    assert t.accent == (255, 0, 0)


def test_kernel_motion_setting():
    os_ = LionOS()
    os_.config.motion = "none"
    assert os_.motion_ok() is False
    os_.config.motion = "full"
    assert os_.motion_ok() is True


def test_kernel_apply_accent():
    os_ = LionOS()
    os_.apply_accent((0, 200, 0))
    assert os_.theme.accent == (0, 200, 0)
```

- [x] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_theme_motion.py -v` → ImportError (`accented`).

- [x] **Step 3: Implement**

`lionos/theme.py` add:

```python
def accented(theme, rgb):
    """Return a copy of ``theme`` with the accent family overridden."""
    from dataclasses import replace
    return replace(theme,
                   accent=rgb,
                   accent2=rgb,
                   icon_grad1=rgb,
                   glow=rgb,
                   taskbar_active=rgb,
                   selection=rgb[:3] + (70,),
                   icon_bg=rgb)
```

`lionos/config.py` add: `motion: str = "full"`, `accent_override: str = ""`.

`lionos/kernel.py`:
- `wallpaper_names()` returns `["gradient", "aurora", "grid", "dots", "mountain"]`.
- `_ensure_wallpaper` branches on `config.wallpaper` to draw the chosen pattern (aurora = radial glows; grid = lines; dots = dot grid; mountain = layered triangles).
- `apply_accent(rgb)`: `self.theme = accented(self.theme, tuple(rgb))`, `self.wm.theme = self.theme`, invalidate caches, `_needs_redraw = True`.
- `motion_ok()`: return `self.config.motion != "none"` and `self.config.anim_enabled`.
- Gate window animations (`begin_anim`) and theme transitions behind `motion_ok()`.

- [x] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_theme_motion.py -v` → 3 passed. Full suite + smoke.

- [x] **Step 5: Commit**

```bash
git add lionos/theme.py lionos/kernel.py lionos/config.py tests/test_theme_motion.py
git commit -m "feat(chrome): wallpaper gallery + accent picker + motion setting"
```

---

### Task 4: Catalog launcher + system tray + statusline widgets

**Files:**
- Modify: `lionos/kernel.py` (launcher catalog view, tray, statusline), `lionos/config.py`
- Test: `tests/test_catalog_tray.py` (new)

**Interfaces:**
- Produces:
  - `kernel.launcher_catalog()` — categorized app manifest rows `{name, desc, version}`.
  - `_draw_launcher_catalog()` — replaces the flat grid with category sections (desc + version badge).
  - System tray: `_draw_tray()` — network online/offline dot, sound toggle, notifications open, show-desktop.
  - Statusline widgets: clock/date/theme/CPU toggles via `config.statusline: list[str]`.

- [x] **Step 1: Write the failing test**

```python
# tests/test_catalog_tray.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
from lionos.kernel import LionOS


def test_catalog_has_all_apps():
    os_ = LionOS()
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    rows = os_.launcher_catalog()
    assert len(rows) >= 15
    assert all("name" in r and "desc" in r for r in rows)


def test_statusline_config():
    os_ = LionOS()
    os_.config.statusline = ["clock", "date", "theme"]
    assert os_.statusline_widgets() == ["clock", "date", "theme"]
```

- [x] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_catalog_tray.py -v` → AttributeError.

- [x] **Step 3: Implement**

`lionos/config.py` add: `statusline: list = field(default_factory=lambda: ["clock", "date", "theme"])`.

`lionos/kernel.py`:
- `launcher_catalog()`: build rows from `self.apps_registry.all()` with `{"name", "desc" (cls.description), "version" (getattr(cls, "version", "1.0"))}`.
- `statusline_widgets()` returns `self.config.statusline`.
- `_draw_launcher_catalog()`: replace/augment `_draw_launcher`'s grid with category sections when `config.catalog_view` is on; keep search filter.
- `_draw_tray()`: draw network dot (from `self.drivers.get("network").online()`), sound toggle icon, notifications icon, show-desktop.
- Extend `_draw_taskbar` to include the tray + statusline widgets (clock/date already there; add theme + CPU from psutil).

- [x] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_catalog_tray.py -v` → 2 passed. Full suite + smoke.

- [x] **Step 5: Commit**

```bash
git add lionos/kernel.py lionos/config.py tests/test_catalog_tray.py
git commit -m "feat(chrome): catalog launcher + system tray + statusline widgets"
```

---

### Task 5: Help app

**Files:**
- Create: `lionos/apps/help.py`
- Modify: `lionos/apps/__init__.py` (register)
- Test: `tests/test_help_app.py` (new)

**Interfaces:**
- Produces: `HelpApp` (`name="Help"`, `icon="Help"`), rendering a searchable catalog of every app's name + description + tips.

- [x] **Step 1: Write the failing test**

```python
# tests/test_help_app.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
from lionos.kernel import LionOS
from lionos.apps import get_apps


def test_help_app_registered():
    assert any(c.name == "Help" for c in get_apps())


def test_help_app_launches_and_draws():
    os_ = LionOS()
    os_._no_draw = False
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    inst = os_.launch("Help")
    for _ in range(4):
        os_._dt = 0.016
        os_._update(os_._dt)
    assert inst.hydrated
    os_._needs_redraw = True
    os_._draw()
    pygame.display.flip()
```

- [x] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_help_app.py -v` → FAIL (not registered).

- [x] **Step 3: Implement `lionos/apps/help.py`**

```python
"""Help app — a searchable catalog of every built-in app."""
from __future__ import annotations

import pygame

from .base import App
from ..widgets import draw_glass_panel, cached_font


class HelpApp(App):
    name = "Help"
    icon = "Help"
    category = "System"
    description = "Self-documenting catalog of every app"
    default_w = 780
    default_h = 520
    resizable = True
    min_w = 480
    min_h = 320

    def on_open(self):
        self._search = ""

    def _rows(self):
        from ..apps import get_apps
        rows = []
        for cls in get_apps():
            if self._search and self._search.lower() not in cls.name.lower():
                continue
            rows.append((cls.name, cls.description or "", cls.category))
        return rows

    def handle_event(self, event, local_pos):
        if event.type == pygame.TEXTINPUT:
            self._search += event.text
            return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_BACKSPACE:
            self._search = self._search[:-1]
            return True
        return False

    def draw(self, surface, rect):
        theme = self.theme
        draw_glass_panel(surface, rect, theme, radius=theme.radius)
        font = cached_font(18)
        title = font.render("Help & App Catalog", True, theme.text)
        surface.blit(title, (18, 14))
        search = cached_font(15).render(f"Search: {self._search or '…'}", True, theme.text_dim)
        surface.blit(search, (18, 46))
        y = 78
        for name, desc, cat in self._rows():
            r = pygame.Rect(14, y, rect.width - 28, 40)
            pygame.draw.rect(surface, theme.surface_alt, r, border_radius=6)
            n = cached_font(16).render(name, True, theme.text)
            surface.blit(n, (r.x + 12, r.y + 6))
            c = cached_font(13).render(cat, True, theme.text_dim)
            surface.blit(c, (r.x + 12 + n.get_width() + 10, r.y + 8))
            d = cached_font(13).render(desc or "…", True, theme.text_dim)
            surface.blit(d, (r.x + 12, r.y + 24))
            y += 46
```

Register in `apps/__init__.py`.

- [x] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_help_app.py -v` → 2 passed. Full suite + smoke.

- [x] **Step 5: Commit**

```bash
git add lionos/apps/help.py lionos/apps/__init__.py tests/test_help_app.py
git commit -m "feat(apps): Help app — self-documenting app catalog"
```

---

## Self-Review notes

- **Spec coverage:** Phase 4 covers §6.12 (catalog launcher), §6.13 (chrome: statusline/HUD/motion/progressive disclosure), §6.14 (notification center), §6.15 (wallpaper + accent), §6.16 (system tray), and the Help app (§6.22). Workspaces/tiling/search/screenshots/Media Player are Phase 5.
- **No placeholders:** every task has concrete test + implementation code.
- **Type consistency:** `notify/clear_notifications/_update_notifications`, `wallpaper_names/apply_accent/motion_ok`, `launcher_catalog/statusline_widgets`, and `HelpApp` are defined once and used consistently.
