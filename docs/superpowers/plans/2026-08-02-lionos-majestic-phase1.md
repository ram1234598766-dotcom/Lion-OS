# Lion-OS 2.0 "Majestic" — Phase 1 (Foundation: icons + smoothness + tokens) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace emoji icons with a procedural vector icon system, make rendering buttery-smooth (dirty-rects, vsync, fixed timestep, perf counters, two-phase startup), and formalize theme tokens with a WCAG-AA contrast guarantee — all while keeping the existing 35 tests + headless smoke green.

**Architecture:** Add a new `lionos/icons.py` (declarative icon-scene DSL + supersampled cached renderer), a `lionos/loop.py` (FrameBudget / DirtyTracker / PerfCounters — all unit-testable with no display), extend `Theme` with semantic tokens + a contrast utility, then wire icons into `widgets.draw_app_tile` and the kernel's desktop/launcher/taskbar/titlebar/Alt-Tab, and the loop helpers into `kernel.run()`. Evolutionary refactor: existing modules are modified in place.

**Tech Stack:** Python 3.9+, pygame-ce, pytest (headless via `SDL_VIDEODRIVER=dummy`).

## Global Constraints

- Python `>=3.9`; no new runtime dependencies (stdlib + pygame + existing psutil/requests only).
- Keep the existing 35 tests passing and `python -m lionos --headless` green after every task.
- Do not restructure `kernel.py`/`wm.py`/`widgets.py` into new layers; modify in place.
- Animations stay strictly additive; all new rendering is cache-backed; no per-frame `pygame.font.Font` creation (use `widgets.cached_font`).
- Run tests on Windows via `py -3 -m pytest tests/ -q` (the `python3` name is a store stub — never use it).
- Version stays `1.1.2` in code until the Phase 6 release bump to `2.0.0`.

---

### Task 1: Theme semantic tokens + contrast utilities

**Files:**
- Modify: `lionos/theme.py` (add tokens + helpers)
- Test: `tests/test_theme_tokens.py` (new)

**Interfaces:**
- Consumes: existing `Theme` dataclass fields and `blend()`.
- Produces:
  - `Theme.radius: int` (default 12), `Theme.spacing: int` (default 8), `Theme.text_disabled: Color` (default `text_dim`).
  - `relative_luminance(c: tuple) -> float`
  - `contrast_ratio(c1, c2) -> float`
  - `ensure_contrast(text, bg, min_ratio=4.5) -> Color` (brighten/darken text until it passes, returns the adjusted color)
  - `theme_contrast_report(theme) -> dict` (body text vs surface/wallpaper ratios).

- [x] **Step 1: Write the failing test**

```python
# tests/test_theme_tokens.py
import pytest
from lionos.theme import Theme, THEMES, contrast_ratio, ensure_contrast, theme_contrast_report

def test_theme_has_semantic_tokens():
    t = THEMES["dark"]
    assert isinstance(t.radius, int) and t.radius > 0
    assert isinstance(t.spacing, int) and t.spacing > 0
    assert isinstance(t.text_disabled, tuple) and len(t.text_disabled) == 3

def test_contrast_ratio_known_values():
    assert contrast_ratio((0, 0, 0), (255, 255, 255)) > 20
    assert contrast_ratio((0, 0, 0), (0, 0, 0)) == 1.0

def test_ensure_contrast_raises_to_minimum():
    out = ensure_contrast((140, 140, 150), (30, 30, 40), 4.5)
    assert contrast_ratio(out, (30, 30, 40)) >= 4.5

def test_all_themes_pass_body_contrast():
    for name, t in THEMES.items():
        report = theme_contrast_report(t)
        assert report["surface"] >= 4.5, f"{name} body text on surface fails: {report['surface']:.2f}"
        assert report["wallpaper"] >= 4.5, f"{name} body text on wallpaper fails: {report['wallpaper']:.2f}"

def test_theme_interpolates_tokens():
    a, b = THEMES["dark"], THEMES["light"]
    m = a.interpolate(b, 0.5)
    assert isinstance(m.radius, int) and m.radius == a.radius  # ints pass through
```

- [x] **Step 2: Run the test to verify it fails**

Run: `py -3 -m pytest tests/test_theme_tokens.py -v`
Expected: FAIL — `relative_luminance` / `contrast_ratio` undefined.

- [x] **Step 3: Implement tokens + contrast in `theme.py`**

Append to `lionos/theme.py`:

```python
# -- semantic tokens + contrast -------------------------------------------
def _srgb_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(c):
    """WCAG relative luminance of an RGB color (0.0-1.0)."""
    r, g, b = (_srgb_linear(ch) for ch in c[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(c1, c2):
    """WCAG contrast ratio between two RGB colors (>=1.0)."""
    l1, l2 = relative_luminance(c1), relative_luminance(c2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def ensure_contrast(text, bg, min_ratio=4.5):
    """Lighten (dark themes) or darken (light themes) ``text`` until it reaches
    ``min_ratio`` against ``bg``. Returns the adjusted color."""
    text, bg = tuple(text[:3]), tuple(bg[:3])
    out = list(text)
    lum_bg = relative_luminance(bg)
    for _ in range(30):
        if contrast_ratio(out, bg) >= min_ratio:
            break
        lum_t = relative_luminance(out)
        if lum_bg > 0.5:
            # light bg -> darken text
            out = [max(0, int(v * 0.86)) for v in out]
        else:
            # dark bg -> lighten text
            out = [min(255, int(v + (255 - v) * 0.5)) for v in out]
    return tuple(out)


def theme_contrast_report(t):
    """Body text contrast vs the main surfaces of a theme."""
    text = tuple(t.text[:3])
    return {
        "surface": contrast_ratio(text, tuple(t.surface[:3])),
        "wallpaper": contrast_ratio(text, tuple(t.wallpaper_top[:3])),
    }
```

Add token fields to the `Theme` dataclass and defaults in `__post_init__`:

```python
    # --- semantic tokens ---
    radius: int = 12
    spacing: int = 8
    text_disabled: Color = None
```

In `__post_init__`, add:

```python
        if self.text_disabled is None:
            self.text_disabled = ensure_contrast(self.text_dim, self.surface, 3.0)
```

Also make `as_dict()` skip `radius`, `spacing` (they are ints, not colors):

```python
        skip = {"name", "is_dark", "radius", "spacing", "text_disabled"}
```

**Note on failing themes:** `test_all_themes_pass_body_contrast` may surface a theme whose `text` vs `surface` or `wallpaper` ratio is < 4.5. Fix by nudging that theme's `text` (or `wallpaper_top`) via `ensure_contrast` in the theme's literal. Verify with the test — do not weaken the assertion.

- [x] **Step 4: Run the test to verify it passes**

Run: `py -3 -m pytest tests/test_theme_tokens.py -v`
Expected: PASS (adjust any theme palette that fails the contrast assertion).

- [x] **Step 5: Run the full suite + smoke**

Run: `py -3 -m pytest tests/ -q` then `LION_OS_HEADLESS=1 py -3 -m lionos --headless`
Expected: 35+ passing; smoke prints `[ok] booted + logged in`.

- [x] **Step 6: Commit**

```bash
git add lionos/theme.py tests/test_theme_tokens.py
git commit -m "feat(theme): semantic tokens + WCAG-AA contrast utilities"
```

---

### Task 2: Icon framework (`icons.py`)

**Files:**
- Create: `lionos/icons.py`
- Test: `tests/test_icons.py` (new)

**Interfaces:**
- Consumes: `Theme` (for the palette), `pygame`.
- Produces:
  - `Scene = List[Tuple[str, dict]]`
  - Scene builders: `s_rect(x,y,w,h,color,radius)`, `s_circle(cx,cy,r,color,width)`,
    `s_line(x1,y1,x2,y2,color,width)`, `s_arc(x,y,w,h,a1,a2,color,width)`,
    `s_poly(points,color)`, `s_ellipse(x,y,w,h,color,width)`, `s_glyph(char,size,color,cx,cy)`.
    Coordinates live in a normalized **0..64** box; `color` is a **token name**
    string resolved against the palette.
  - `palette_for(theme) -> dict[str, Color]`
  - `IconCache.render(scene, scene_id, size, theme) -> pygame.Surface` (2× supersampled, cached by `(scene_id, size, fingerprint)`).
  - `glyph_scene(char) -> Scene` — fallback that renders a glyph centered.

- [x] **Step 1: Write the failing test**

```python
# tests/test_icons.py
import pygame
from lionos.icons import (s_rect, s_circle, s_line, s_glyph, glyph_scene,
                          IconCache, palette_for)
from lionos.theme import THEMES

def _term_scene():
    return [
        s_rect(10, 18, 44, 34, "panel", radius=6),
        s_glyph(">", 16, "accent", cx=20, cy=32),
        s_line(30, 32, 50, 32, "muted", 3),
    ]

def test_palette_has_tokens():
    p = palette_for(THEMES["dark"])
    for k in ("accent", "accent2", "panel", "text", "muted", "highlight", "success", "warn", "danger"):
        assert k in p and len(p[k]) in (3, 4)

def test_render_returns_correct_size():
    cache = IconCache()
    surf = cache.render(_term_scene(), "terminal", 32, THEMES["dark"])
    assert surf.get_size() == (32, 32)

def test_cache_hits_are_identical_surface():
    cache = IconCache()
    a = cache.render(_term_scene(), "terminal", 32, THEMES["dark"])
    b = cache.render(_term_scene(), "terminal", 32, THEMES["dark"])
    assert a is b  # cached object identity

def test_theme_change_invalidates():
    cache = IconCache()
    a = cache.render(_term_scene(), "terminal", 32, THEMES["dark"])
    b = cache.render(_term_scene(), "terminal", 32, THEMES["ocean"])
    assert a is not b

def test_glyph_fallback_renders():
    cache = IconCache()
    surf = cache.render(glyph_scene("☺"), "fallback", 24, THEMES["dark"])
    assert surf.get_size() == (24, 24)
```

- [x] **Step 2: Run the test to verify it fails**

Run: `py -3 -m pytest tests/test_icons.py -v`
Expected: FAIL — `lionos.icons` has no module.

- [x] **Step 3: Implement `lionos/icons.py`**

```python
"""Procedural vector icon system for Lion-OS.

Apps declare a small scene of shape primitives in a normalized 0..64 box.
``IconCache.render`` draws the scene at 2x and smoothscales it down, giving
crisp antialiased icons at any size. Colors are semantic token names resolved
through the active theme, so every icon re-themes automatically.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Tuple

import pygame

from .theme import Theme

Color = Tuple[int, int, int]
RGBA = Tuple[int, int, int, int]
Scene = List[Tuple[str, dict]]

# --- scene builders (normalized 0..64 box) --------------------------------
def s_rect(x=0, y=0, w=16, h=16, color="accent", radius=3):
    return ("rect", dict(x=x, y=y, w=w, h=h, color=color, radius=radius))


def s_circle(cx=32, cy=32, r=8, color="accent", width=0):
    return ("circle", dict(cx=cx, cy=cy, r=r, color=color, width=width))


def s_line(x1=0, y1=0, x2=64, y2=64, color="text", width=2):
    return ("line", dict(x1=x1, y1=y1, x2=x2, y2=y2, color=color, width=width))


def s_arc(x=0, y=0, w=16, h=16, a1=0.0, a2=6.28, color="accent", width=2):
    return ("arc", dict(x=x, y=y, w=w, h=h, a1=a1, a2=a2, color=color, width=width))


def s_poly(points, color="accent"):
    return ("poly", dict(points=list(points), color=color))


def s_ellipse(x=0, y=0, w=16, h=16, color="accent", width=0):
    return ("ellipse", dict(x=x, y=y, w=w, h=h, color=color, width=width))


def s_glyph(char, size=10, color="text", cx=32, cy=32):
    return ("glyph", dict(char=char, size=size, color=color, cx=cx, cy=cy))


def glyph_scene(char):
    return [s_glyph(char, 40, "text", cx=32, cy=32)]


# --- palette --------------------------------------------------------------
def palette_for(theme: Theme) -> Dict[str, Color]:
    return {
        "accent": theme.accent,
        "accent2": theme.accent2,
        "panel": theme.surface_alt,
        "text": theme.text,
        "muted": theme.text_dim,
        "highlight": theme.glow,
        "success": theme.success,
        "warn": theme.warn,
        "danger": theme.danger,
        "white": (255, 255, 255),
        "black": (0, 0, 0),
    }


def _fingerprint(theme: Theme) -> tuple:
    return tuple(getattr(theme, f)
                 for f in ("accent", "accent2", "surface_alt", "text",
                           "text_dim", "glow", "success", "warn", "danger"))


# --- renderer -------------------------------------------------------------
def _draw_primitive(surf, kind, p, pal, s):
    scale = lambda v: int(v * s)
    px = lambda k: pal.get(p.get(k), (255, 255, 255))
    if kind == "rect":
        pygame.draw.rect(surf, px("color"),
                         pygame.Rect(scale(p["x"]), scale(p["y"]),
                                     scale(p["w"]), scale(p["h"])),
                         border_radius=scale(p.get("radius", 3)))
    elif kind == "circle":
        pygame.draw.circle(surf, px("color"),
                           (scale(p["cx"]), scale(p["cy"])),
                           scale(p["r"]), scale(p.get("width", 0)))
    elif kind == "line":
        pygame.draw.line(surf, px("color"),
                         (scale(p["x1"]), scale(p["y1"])),
                         (scale(p["x2"]), scale(p["y2"])),
                         max(1, scale(p.get("width", 2))))
    elif kind == "arc":
        pygame.draw.arc(surf, px("color"),
                        pygame.Rect(scale(p["x"]), scale(p["y"]),
                                    scale(p["w"]), scale(p["h"])),
                        p["a1"], p["a2"], max(1, scale(p.get("width", 2))))
    elif kind == "poly":
        pts = [(scale(x), scale(y)) for x, y in p["points"]]
        pygame.draw.polygon(surf, px("color"), pts)
    elif kind == "ellipse":
        pygame.draw.ellipse(surf, px("color"),
                            pygame.Rect(scale(p["x"]), scale(p["y"]),
                                        scale(p["w"]), scale(p["h"])),
                            scale(p.get("width", 0)))
    elif kind == "glyph":
        from .widgets import cached_font
        f = cached_font(scale(p.get("size", 16)))
        img = f.render(p["char"], True, px("color"))
        surf.blit(img, img.get_rect(center=(scale(p["cx"]), scale(p["cy"]))))


def _render_scene(scene, size, pal):
    ss = 2  # supersample factor
    base = 64
    big = pygame.Surface((base * ss, base * ss), pygame.SRCALPHA)
    for kind, p in scene:
        _draw_primitive(big, kind, p, pal, ss)
    return pygame.transform.smoothscale(big, (size, size))


class IconCache:
    def __init__(self):
        self._cache: Dict[tuple, pygame.Surface] = {}

    def render(self, scene, scene_id, size, theme):
        key = (scene_id, size, _fingerprint(theme))
        surf = self._cache.get(key)
        if surf is None:
            surf = _render_scene(scene, size, palette_for(theme))
            self._cache[key] = surf
        return surf
```

- [x] **Step 4: Run the test to verify it passes**

Run: `py -3 -m pytest tests/test_icons.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add lionos/icons.py tests/test_icons.py
git commit -m "feat(icons): procedural vector icon framework with supersampled cache"
```

---

### Task 3: App icon scenes for every app

**Files:**
- Modify: `lionos/icons.py` (add `APP_ICONS` dict)
- Test: `tests/test_icons.py` (extend)

**Interfaces:**
- Consumes: `Scene` builders from Task 2.
- Produces: `APP_ICONS: Dict[str, Scene]` keyed by app `name` for all 15 current apps + the 5 planned new apps ("Help", "System Health", "Inbox", "Today", "Devices"). A missing key falls back to `glyph_scene(cls.icon)`.

- [x] **Step 1: Write the failing test (extend `tests/test_icons.py`)**

```python
from lionos.icons import APP_ICONS, IconCache, glyph_scene
from lionos.apps import get_apps  # helper added in step 3

def test_every_registered_app_has_an_icon():
    cache = IconCache()
    for cls in get_apps():
        scene = APP_ICONS.get(cls.name) or glyph_scene(cls.icon)
        surf = cache.render(scene, cls.name, 32, THEMES["dark"])
        assert surf.get_size() == (32, 32), cls.name

def test_all_scenes_render_at_three_sizes():
    cache = IconCache()
    for name, scene in APP_ICONS.items():
        for size in (16, 32, 64):
            surf = cache.render(scene, name, size, THEMES["dark"])
            assert surf.get_size() == (size, size), (name, size)
```

- [x] **Step 2: Run to verify it fails**

Run: `py -3 -m pytest tests/test_icons.py -v`
Expected: FAIL — `APP_ICONS`/`get_apps` undefined.

- [x] **Step 3: Implement `APP_ICONS` and `get_apps`**

Add to `lionos/apps/__init__.py` (module already imports the app classes and builds the registry):

```python
def get_apps():
    """Return the list of registered app classes (stable order)."""
    reg = registry
    return [reg.get(n) for n in reg.all()]
```

Add to `lionos/icons.py` (after `glyph_scene`):

```python
APP_ICONS: Dict[str, Scene] = {
    # Terminal: prompt + underscore line on a dark panel
    "Terminal": [
        s_rect(10, 18, 44, 34, "panel", radius=6),
        s_glyph(">", 16, "accent", cx=22, cy=32),
        s_line(32, 32, 52, 32, "muted", 3),
    ],
    # Calculator: rounded body + 3x4 key grid
    "Calculator": [
        s_rect(14, 10, 36, 46, "panel", radius=6),
        s_rect(20, 16, 24, 6, "muted", radius=2),
        *[s_circle(cx=22 + (i % 3) * 10, cy=30 + (i // 3) * 10, r=3,
                   color=("accent" if i in (0, 1, 2, 3) else "muted"))
          for i in range(9)],
    ],
    # File Manager: folder with tab
    "File Manager": [
        s_rect(12, 20, 16, 8, "accent2", radius=3),
        s_rect(10, 24, 44, 28, "accent", radius=4),
        s_line(18, 34, 46, 34, "white", 2),
        s_line(18, 40, 40, 40, "white", 2),
    ],
    # Notes: page with lines + folded corner
    "Notes": [
        s_rect(18, 12, 30, 42, "panel", radius=4),
        s_line(24, 24, 42, 24, "muted", 2),
        s_line(24, 32, 42, 32, "muted", 2),
        s_line(24, 40, 36, 40, "muted", 2),
        s_poly([(44, 40), (48, 40), (48, 36), (44, 40)], "accent"),
    ],
    # Settings: gear (circle + spokes)
    "Settings": [
        s_circle(cx=32, cy=32, r=9, "accent", width=3),
        s_circle(cx=32, cy=32, r=4, "accent"),
        *[s_line(cx0, cy0, cx1, cy1, "accent", 3)
          for (cx0, cy0, cx1, cy1) in [
              (32, 10, 32, 17), (32, 47, 32, 54), (10, 32, 17, 32),
              (47, 32, 54, 32), (16, 16, 21, 21), (43, 43, 48, 48),
              (43, 21, 48, 16), (16, 43, 21, 48)]],
    ],
    # Browser: globe
    "Browser": [
        s_circle(cx=32, cy=32, r=18, "accent", width=3),
        s_ellipse(14, 18, 36, 28, "accent", width=2),
        s_line(14, 32, 50, 32, "accent", 2),
        s_line(32, 14, 32, 50, "accent", 2),
    ],
    # Media Player: two music notes
    "Media Player": [
        s_circle(cx=20, cy=46, r=6, "accent"),
        s_line(24, 46, 24, 18, "accent", 3),
        s_line(24, 18, 44, 12, "accent", 3),
        s_line(44, 12, 44, 32, "accent", 3),
        s_circle(cx=44, cy=32, r=6, "accent"),
    ],
    # Paint: palette with dots
    "Paint": [
        s_circle(cx=32, cy=32, r=20, "accent", width=3),
        s_circle(cx=32, cy=32, r=13, "accent"),
        s_circle(cx=24, cy=38, r=4, "success"),
        s_circle(cx=34, cy=42, r=4, "warn"),
        s_circle(cx=42, cy=34, r=4, "danger"),
    ],
    # AI Assistant: chat bubble with dots
    "AI Assistant": [
        s_rect(12, 14, 40, 28, "accent", radius=8),
        s_poly([(16, 40), (16, 50), (26, 40)], "accent"),
        s_circle(cx=24, cy=28, r=3, "white"),
        s_circle(cx=32, cy=28, r=3, "white"),
        s_circle(cx=40, cy=28, r=3, "white"),
    ],
    # System Monitor: bar chart
    "System Monitor": [
        s_line(12, 52, 52, 52, "muted", 3),
        s_rect(16, 34, 8, 18, "accent", radius=2),
        s_rect(28, 22, 8, 30, "success", radius=2),
        s_rect(40, 12, 8, 40, "warn", radius=2),
    ],
    # Text Editor: page with pencil
    "Text Editor": [
        s_rect(18, 10, 30, 44, "panel", radius=4),
        s_line(24, 22, 42, 22, "muted", 2),
        s_line(24, 30, 42, 30, "muted", 2),
        s_line(24, 38, 36, 38, "muted", 2),
        s_line(40, 40, 50, 30, "accent", 3),
        s_line(50, 30, 54, 34, "accent", 3),
    ],
    # About: info ring
    "About": [
        s_circle(cx=32, cy=32, r=20, "accent", width=3),
        s_circle(cx=32, cy=24, r=3, "accent"),
        s_line(32, 30, 32, 44, "accent", 3),
    ],
    # App Store: shopping bag
    "App Store": [
        s_arc(26, 12, 12, 10, 3.14, 6.28, "accent", 3),
        s_rect(18, 22, 28, 30, "accent", radius=4),
        s_line(26, 22, 26, 30, "white", 2),
        s_line(38, 22, 38, 30, "white", 2),
    ],
    # Welcome: sparkle star
    "Welcome": [
        s_poly([(32, 10), (37, 27), (54, 32), (37, 37), (32, 54),
                (27, 37), (10, 32), (27, 27)], "accent"),
    ],
    # UI Toolkit: 2x2 grid of rounded squares
    "UI Toolkit": [
        s_rect(12, 12, 16, 16, "accent", radius=4),
        s_rect(36, 12, 16, 16, "success", radius=4),
        s_rect(12, 36, 16, 16, "warn", radius=4),
        s_rect(36, 36, 16, 16, "muted", radius=4),
    ],
    # --- planned Phase-5 apps (scenes defined now so Phase 1 tests cover them)
    "Help": [
        s_circle(cx=32, cy=32, r=20, "accent", width=3),
        s_glyph("?", 24, "accent", cx=32, cy=34),
    ],
    "System Health": [
        s_circle(cx=18, cy=32, r=9, "danger", width=3),
        s_poly([(32, 32), (38, 26), (44, 30), (54, 22), (52, 34),
                (44, 36), (36, 40)], "success"),
        s_line(52, 34, 56, 38, "warn", 3),
    ],
    "Inbox": [
        s_rect(10, 18, 44, 30, "accent", radius=6),
        s_line(14, 24, 32, 36, "white", 3),
        s_line(50, 24, 32, 36, "white", 3),
    ],
    "Today": [
        s_circle(cx=32, cy=32, r=20, "accent", width=3),
        s_line(32, 14, 32, 32, "accent", 3),
        s_line(32, 32, 44, 40, "accent", 3),
    ],
    "Devices": [
        s_rect(10, 24, 30, 18, "panel", radius=4),
        s_circle(cx=30, cy=33, r=5, "accent", width=3),
        s_line(46, 22, 52, 22, "accent", 3),
        s_line(46, 34, 52, 34, "accent", 3),
        s_line(52, 22, 52, 34, "accent", 3),
        s_rect(36, 26, 8, 14, "accent", radius=2),
    ],
}
```

- [x] **Step 4: Run to verify it passes**

Run: `py -3 -m pytest tests/test_icons.py -v`
Expected: PASS (all 20 apps render at 16/32/64).

- [x] **Step 5: Commit**

```bash
git add lionos/icons.py lionos/apps/__init__.py tests/test_icons.py
git commit -m "feat(icons): app icon scenes for all apps"
```

---

### Task 4: Integrate icons into the shell

**Files:**
- Modify: `lionos/widgets.py` (`draw_app_tile`), `lionos/kernel.py` (desktop icons, launcher, taskbar, titlebar, Alt-Tab)
- Test: `tests/test_shell_icons.py` (new, headless)

**Interfaces:**
- Consumes: `IconCache` + `APP_ICONS`/`glyph_scene` from Tasks 2-3; `cached_font`.
- Produces: `LionOS.icon_cache: IconCache`; `draw_app_tile(..., icon_cache=None, scene=None, scene_id=None)` — when `scene` is provided, draws the vector icon instead of the emoji glyph; when not, falls back to the glyph.

- [x] **Step 1: Write the failing test**

```python
# tests/test_shell_icons.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("LION_OS_HEADLESS", "1")
import pygame
import pytest
from lionos.theme import THEMES
from lionos.icons import APP_ICONS, glyph_scene, IconCache
from lionos.widgets import draw_app_tile


@pytest.fixture()
def surf():
    return pygame.Surface((400, 400), pygame.SRCALPHA)


def test_draw_app_tile_accepts_scene(surf):
    cache = IconCache()
    r = pygame.Rect(0, 0, 32, 32)
    draw_app_tile(surf, r, "☺", THEMES["dark"], icon_cache=cache,
                  scene=APP_ICONS["Terminal"], scene_id="Terminal")
    assert r is not None  # no exception; rect returned


def test_draw_app_tile_uses_vector_icon_not_glyph(surf):
    cache = IconCache()
    # Render tile with the Terminal scene on a transparent surf and assert
    # some non-transparent pixels exist (proves something was drawn).
    draw_app_tile(surf, pygame.Rect(0, 0, 48, 48), "☺", THEMES["dark"],
                  icon_cache=cache, scene=APP_ICONS["Terminal"], scene_id="Terminal")
    has_pixels = any(surf.get_at((x, y))[3] > 0 for x in range(0, 48, 4) for y in range(0, 48, 4))
    assert has_pixels


def test_draw_app_tile_falls_back_to_glyph_without_scene(surf):
    cache = IconCache()
    draw_app_tile(surf, pygame.Rect(0, 0, 32, 32), "☺", THEMES["dark"], icon_cache=cache)
    # should not raise
```

- [x] **Step 2: Run to verify it fails**

Run: `py -3 -m pytest tests/test_shell_icons.py -v`
Expected: FAIL — `draw_app_tile` has no `icon_cache`/`scene` params.

- [x] **Step 3: Implement**

Modify `draw_app_tile` in `lionos/widgets.py` (replace the glyph render block):

```python
def draw_app_tile(surface, rect, glyph, theme, hovered=False, pressed=False,
                  selected=False, font_size=None, label=None,
                  icon_cache=None, scene=None, scene_id=None):
    """... (keep existing docstring, add:)
    When ``icon_cache`` and ``scene`` are given, the scene is rendered as the
    tile artwork instead of ``glyph`` (which then acts as a fallback only).
    """
    r = pygame.Rect(rect)
    radius = max(6, int(r.height * 0.22))
    key = (r.size, theme.icon_grad1, theme.icon_grad2)
    tile = _tile_cache.get(key)
    if tile is None:
        tile = pygame.Surface(r.size, pygame.SRCALPHA)
        g1 = theme.icon_grad1
        g2 = theme.icon_grad2
        for yy in range(r.height):
            tt = yy / max(1, r.height - 1)
            col = blend_color(g1, g2, tt)
            pygame.draw.line(tile, col, (0, yy), (r.width, yy))
        pygame.draw.rect(tile, (255, 255, 255, 46), tile.get_rect(), 1, border_radius=radius)
        _tile_cache[key] = tile
    old = surface.get_clip()
    clip = pygame.Rect(r)
    surface.set_clip(clip)
    surface.blit(tile, r.topleft)
    if pressed:
        pygame.draw.rect(surface, (0, 0, 0, 40), r, border_radius=radius)
    elif hovered or selected:
        pygame.draw.rect(surface, (255, 255, 255, 26), r, border_radius=radius)

    # Vector icon when available, else glyph fallback.
    if scene is not None and icon_cache is not None:
        pad = max(2, int(r.height * 0.08))
        inner = pygame.Rect(r.x + pad, r.y + pad, r.width - 2 * pad, r.height - 2 * pad)
        size = max(4, inner.width)
        img = icon_cache.render(scene, scene_id or "scene", size, theme)
        surface.blit(img, img.get_rect(center=inner.center))
    else:
        f = cached_font(font_size or int(r.height * 0.62))
        img = f.render(glyph, True, (255, 255, 255))
        surface.blit(img, img.get_rect(center=r.center))
    surface.set_clip(old)
    if label:
        lf = cached_font(15)
        limg = lf.render(label, True, theme.text)
        surface.blit(limg, limg.get_rect(midtop=(r.centerx, r.bottom + 6)))
    return r
```

In `lionos/kernel.py`:
- In `__init__`, add `from .icons import IconCache, APP_ICONS, glyph_scene` and `self.icon_cache = IconCache()`.
- Add a helper `_app_icon_scene(cls)`:

```python
    def _app_icon_scene(self, cls):
        if cls is None:
            return None
        return APP_ICONS.get(cls.name)
```

- In `_draw_desktop_icons` (replace the `draw_app_tile` call):

```python
            draw_app_tile(self.screen, tile, glyph, self.theme,
                          hovered=hovered, selected=selected,
                          icon_cache=self.icon_cache,
                          scene=APP_ICONS.get(app) or (glyph_scene(glyph) if glyph else None),
                          scene_id=app)
```

- In the launcher / taskbar / titlebar / Alt-Tab draw calls, pass `icon_cache=self.icon_cache, scene=APP_ICONS.get(name), scene_id=name` wherever `draw_app_tile` is called (kernel.py lines near 1057, 1092). Where glyphs are rendered directly (titlebar `font.render(win.app.icon ...)` at ~1142 and Alt-Tab), leave glyphs as-is for this task (they are small) — note for Phase 4 chrome polish.

- [x] **Step 4: Run tests + smoke**

Run: `py -3 -m pytest tests/ -q` then `LION_OS_HEADLESS=1 py -3 -m lionos --headless`
Expected: all pass (including the new shell-icon tests); smoke `[ok]`.

- [x] **Step 5: Commit**

```bash
git add lionos/widgets.py lionos/kernel.py tests/test_shell_icons.py
git commit -m "feat(icons): vector icons in desktop, launcher, taskbar shell"
```

---

### Task 5: Smoothness — FrameBudget, DirtyTracker, PerfCounters

**Files:**
- Create: `lionos/loop.py`
- Modify: `lionos/kernel.py` (use the loop helpers in `run()`)
- Test: `tests/test_loop.py` (new)

**Interfaces:**
- Consumes: nothing from prior tasks.
- Produces:
  - `FrameBudget(fps=60)` with `.tick(dt) -> float` (clamped dt), `.frame_ms`, `.fps()`.
  - `DirtyTracker(max_rects=32)` with `.mark(rect)`, `.clear()`, `.consume_full() -> bool`, `.consume_rects() -> list[pygame.Rect]`; unions overlapping rects and flips to full when exhausted.
  - `PerfCounters` with `.begin_frame()`, `.end_frame()`, `.frame_ms`, `.fps`, `.redraw_count`, `.mark_redraw()`.

- [x] **Step 1: Write the failing test**

```python
# tests/test_loop.py
import pygame
from lionos.loop import FrameBudget, DirtyTracker, PerfCounters


def test_frame_budget_clamps_dt():
    fb = FrameBudget(60)
    assert fb.tick(0.5) <= 0.05  # clamped to max dt
    assert fb.tick(0.016) <= 0.05


def test_dirty_tracker_small_updates_partial():
    dt = DirtyTracker()
    dt.mark(pygame.Rect(0, 0, 40, 40))
    dt.mark(pygame.Rect(50, 50, 40, 40))
    assert not dt.consume_full()
    rects = dt.consume_rects()
    assert len(rects) >= 1
    assert pygame.Rect(0, 0, 40, 40).inflate(4, 4).colliderect(rects[0])


def test_dirty_tracker_full_when_many():
    dt = DirtyTracker(max_rects=4)
    for i in range(10):
        dt.mark(pygame.Rect(i * 40, 0, 40, 40))
    assert dt.consume_full()


def test_perf_counters():
    pc = PerfCounters()
    pc.begin_frame()
    pc.end_frame()
    assert pc.fps > 0
    pc.mark_redraw()
    assert pc.redraw_count == 1
```

- [x] **Step 2: Run to verify it fails**

Run: `py -3 -m pytest tests/test_loop.py -v`
Expected: FAIL — `lionos.loop` has no module.

- [x] **Step 3: Implement `lionos/loop.py`**

```python
"""Deterministic main-loop helpers: fixed timestep, dirty tracking, perf.

All classes are pure logic (no display calls) so the suite can test them
headlessly.
"""
from __future__ import annotations

import time
from typing import List, Optional

import pygame

MAX_DT = 0.05  # clamp to avoid the spiral-of-death after a hitch


class FrameBudget:
    def __init__(self, fps: int = 60):
        self.fps = fps
        self._last = time.perf_counter()
        self.frame_ms = 0.0

    def tick(self, dt: float) -> float:
        self.frame_ms = dt * 1000.0
        return min(MAX_DT, max(0.0001, dt))


class DirtyTracker:
    """Accumulate changed rects; union overlaps; degrade to a full redraw
    when too many regions accumulate."""

    def __init__(self, max_rects: int = 32):
        self.max_rects = max_rects
        self._rects: List[pygame.Rect] = []
        self._full = False

    def mark(self, rect: pygame.Rect):
        if self._full:
            return
        r = rect.inflate(4, 4)  # bleed for shadows/antialias
        for existing in self._rects:
            if existing.colliderect(r):
                existing.union_ip(r)
                return
        self._rects.append(r)
        if len(self._rects) > self.max_rects:
            self._full = True

    def clear(self):
        self._rects = []
        self._full = False

    def consume_full(self) -> bool:
        full = self._full
        self.clear()
        return full

    def consume_rects(self) -> List[pygame.Rect]:
        rects = list(self._rects)
        self.clear()
        return rects


class PerfCounters:
    def __init__(self, window: float = 0.5):
        self._window = window
        self._start = 0.0
        self._frames = 0
        self._acc = 0.0
        self.frame_ms = 0.0
        self.fps = 60.0
        self.redraw_count = 0

    def begin_frame(self):
        self._start = time.perf_counter()

    def end_frame(self):
        self.frame_ms = (time.perf_counter() - self._start) * 1000.0
        self._frames += 1
        self._acc += self.frame_ms
        if self._acc >= self._window * 1000.0:
            self.fps = self._frames / (self._acc / 1000.0)
            self._frames = 0
            self._acc = 0.0

    def mark_redraw(self):
        self.redraw_count += 1
```

- [x] **Step 4: Run to verify it passes**

Run: `py -3 -m pytest tests/test_loop.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add lionos/loop.py tests/test_loop.py
git commit -m "feat(loop): deterministic main-loop helpers (budget/dirty/perf)"
```

---

### Task 6: Smoothness — vsync, fixed timestep, dirty-present, perf in kernel

**Files:**
- Modify: `lionos/kernel.py` (`run`, `_draw`, `set_mode` init), `lionos/config.py` (add `vsync`, `show_fps` defaults)
- Test: extend `tests/test_loop.py` + headless smoke

**Interfaces:**
- Consumes: `FrameBudget`, `DirtyTracker`, `PerfCounters` from Task 5.
- Produces: `LionOS.fps` (float, live), `LionOS._perf: PerfCounters`, `LionOS._dirty: DirtyTracker`; `LionConfig.vsync: bool` (default False — SDL dummy driver has no vsync), `LionConfig.show_fps: bool` (default False).

- [x] **Step 1: Write the failing test (extend `tests/test_loop.py`)**

```python
from lionos.loop import FrameBudget, DirtyTracker, PerfCounters

def test_kernel_loop_helpers_wire_in():  # smoke that imports resolve
    import lionos.loop as L
    assert hasattr(L, "FrameBudget") and hasattr(L, "DirtyTracker") and hasattr(L, "PerfCounters")
```

- [x] **Step 2: Run to verify it fails**

Run: `py -3 -m pytest tests/test_loop.py -v`
Expected: already passing — this task's real verification is the headless smoke exercising `run()` (Step 4).

- [x] **Step 3: Implement**

In `lionos/config.py` `LionConfig`, add defaults (near the other resolution/fps defaults):

```python
    vsync: bool = False
    show_fps: bool = False
```

In `lionos/kernel.py`:
- Add imports: `from .loop import MAX_DT, FrameBudget, DirtyTracker, PerfCounters`.
- In `__init__`, after `self.clock = pygame.time.Clock()`:

```python
        self._frame_budget = FrameBudget(60)
        self._dirty = DirtyTracker()
        self._perf = PerfCounters()
        self.fps = 60.0
```

- In the video init (`set_mode`), when not headless and `self.config.vsync`:

```python
        flags = pygame.FULLSCREEN | pygame.SCALED if self.config.resolution == "fullscreen" else 0
        if self.config.vsync:
            flags |= pygame.SCALED
        try:
            self.screen = pygame.display.set_mode(
                (self.screen_w, self.screen_h), flags, vsync=1)
        except (TypeError, ValueError):
            self.screen = pygame.display.set_mode((self.screen_w, self.screen_h), flags)
```

- Replace `run()`:

```python
    def run(self):
        while self.running:
            dt = min(MAX_DT, self.clock.tick(60) / 1000.0)
            self._dt = self._frame_budget.tick(dt)
            self._perf.begin_frame()
            for event in pygame.event.get():
                self._handle_event(event)
            self._update(self._dt)
            if not self._no_draw:
                if self._needs_redraw or self._any_animating():
                    self._perf.mark_redraw()
                    self._draw()
                    self._needs_redraw = False
                    if self._dirty.consume_full():
                        pygame.display.flip()
                    else:
                        rects = self._dirty.consume_rects()
                        if rects:
                            pygame.display.update(rects)
                        else:
                            pygame.display.flip()
            else:
                self._headless_tick()
            self._perf.end_frame()
            self.fps = self._perf.fps
        self.shutdown = True
        pygame.quit()
        return 0
```

- Mark regions dirty when they change: in `_update`, whenever a window moves/resizes, `self._dirty.mark(win.rect)`. Add to the window loop in `_update`:

```python
            if inst.window.content_rect != inst.rect:
                self._dirty.mark(inst.window.rect)
                inst.rect = pygame.Rect(inst.window.content_rect)
                inst.on_resize(inst.rect)
```

- Draw the FPS when `self.config.show_fps` in `_draw` (top-left, via `get_font(14)`, cached surface not needed for this debug overlay).

- [x] **Step 4: Verify with headless smoke + suite**

Run: `LION_OS_HEADLESS=1 py -3 -m lionos --headless` and `py -3 -m pytest tests/ -q`
Expected: smoke `[ok]`; all tests pass. (Note: SDL dummy driver ignores vsync; the headless path never calls `set_mode`.)

- [x] **Step 5: Commit**

```bash
git add lionos/kernel.py lionos/config.py tests/test_loop.py
git commit -m "feat(loop): vsync + fixed timestep + dirty-present + perf in kernel"
```

---

### Task 7: Two-phase startup (skeleton now, hydrate later)

**Files:**
- Modify: `lionos/kernel.py` (defer app content draw a few frames after open), `lionos/apps/base.py` (add `_hydration_delay`/`hydrated` flags)
- Test: `tests/test_shell_icons.py` (extend) — headless check that a freshly opened window draws chrome before content.

**Interfaces:**
- Consumes: existing `_draw_window`.
- Produces: `App.hydrated: bool` (False until ~3 frames after open); `App._hydrate_timer: float`.

- [x] **Step 1: Write the failing test (extend `tests/test_shell_icons.py`)**

```python
def test_app_hydration_flag():
    from lionos.apps.base import App
    a = object.__new__(App)   # bare instance: we only test the timer contract
    a.hydrated = False
    a._hydrate_timer = 0.0
    for _ in range(4):
        a.step_hydration(0.016)   # 0.064s total > 0.05s threshold
    assert a.hydrated is True
    a.step_hydration(0.016)       # stays hydrated
    assert a.hydrated is True
```

The meaningful assertion lives in Step 4's headless integration check; the unit test above pins the flags' existence so future hydration logic has a stable contract.

- [x] **Step 2: Run to verify it fails**

Run: `py -3 -m pytest tests/test_shell_icons.py -v`
Expected: FAIL — `App` has no `_hydrate_timer`/`hydrated`.

- [x] **Step 3: Implement**

In `lionos/apps/base.py` `App.__init__`, add:

```python
        self.hydrated = False
        self._hydrate_timer = 0.0
```

Add a method:

```python
    def step_hydration(self, dt: float):
        """Advance the two-phase startup: content becomes available after a
        short structural pass (~3 frames)."""
        if not self.hydrated:
            self._hydrate_timer += dt
            if self._hydrate_timer >= 0.05:
                self.hydrated = True
```

In `lionos/kernel.py` `_update`, inside the instance loop, before `inst.update(dt)`:

```python
            inst.step_hydration(dt)
```

In `_draw_window`, render app content only once hydrated (chrome always shows):

```python
        if cr.width > 0 and cr.height > 0 and win.app and getattr(win.app, "hydrated", True):
            ... (existing clip + draw block)
        elif cr.width > 0 and cr.height > 0 and win.app:
            # Structural pass: draw a subtle empty-content placeholder so the
            # window appears instantly instead of as a blank gap.
            placeholder = self._content_placeholder_surf(cr.size, self.theme)
            self.screen.blit(placeholder, cr.topleft)
```

Add the placeholder helper (cached by size + theme):

```python
    _content_ph_cache: dict = {}

    def _content_placeholder_surf(self, size, theme):
        key = (size, theme.surface)
        s = self._content_ph_cache.get(key)
        if s is None:
            s = pygame.Surface(size, pygame.SRCALPHA)
            pygame.draw.rect(s, theme.surface + (255,), s.get_rect(),
                             border_radius=max(4, theme.radius // 2))
            self._content_ph_cache[key] = s
        return s
```

- [x] **Step 4: Verify with headless integration**

Run: `LION_OS_HEADLESS=1 py -3 -c "
import os
from lionos.kernel import LionOS
os_ = LionOS()
os_._no_draw = False
for _ in range(800):
    os_._dt = 0.016
    os_._update(os_._dt)
    if os_.booted and os_.logged_in:
        break
os_._do_login()
inst = os_.launch('Terminal')
for _ in range(4):
    os_._dt = 0.016
    os_._update(os_._dt)
assert inst.app.hydrated, 'app did not hydrate'
print('ok: hydration works')
"` then `py -3 -m pytest tests/ -q`
Expected: `ok: hydration works`; all tests pass.

- [x] **Step 5: Commit**

```bash
git add lionos/apps/base.py lionos/kernel.py tests/test_shell_icons.py
git commit -m "feat(loop): two-phase startup — chrome first, app content hydrates"
```

---

## Self-Review notes

- **Spec coverage:** Phase 1 covers spec §6.1 (icons), §6.2 (smoothness incl. dirty-rects/vsync/fixed-timestep/perf/two-phase), §6.3 (theme tokens + WCAG-AA contrast + focus states — focus states are deferred to Phase 4 chrome polish per the plan's scope note; the contrast half is fully covered). Background-work-with-debounce (§6.2) is deferred to Phase 3 where its consumers (session/activity) exist — avoiding speculative code.
- **No placeholders:** every task has concrete test + implementation code.
- **Type consistency:** `IconCache.render(scene, scene_id, size, theme)` is defined once (Task 2) and used identically in Tasks 3-4; `draw_app_tile(..., icon_cache, scene, scene_id)` signature is consistent across Task 4's test and implementation.
