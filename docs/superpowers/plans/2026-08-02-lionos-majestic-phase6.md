# Lion-OS 2.0 "Majestic" — Phase 6 (Settings overhaul + release) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul the Settings app to expose every new capability (Appearance/Devices/Motion/Sound/Statusline/System), bump to **2.0.0 "Majestic"**, overhaul the README, then build, verify in a fresh venv, and publish to GitHub + PyPI.

**Architecture:** Extend `lionos/apps/settings.py` with new sections wiring to the kernel's new APIs (`apply_accent`, `wallpaper_names`, `motion_ok`, `set_workspace`, drivers bus, statusline). Bump version in `pyproject.toml` + `lionos/__init__.py`. Rewrite README. Build → fresh-venv verify → publish (GitHub tag → release workflow; PyPI via twine).

**Tech Stack:** Python 3.9+, pygame, setuptools/build, twine.

## Global Constraints

- Python `>=3.9`; no new runtime dependencies.
- Keep all 120 existing tests + headless smoke green.
- Version bump must be consistent everywhere: `pyproject.toml`, `lionos/__init__.py`, README badge + release URL.
- Publish flow identical to v1.1.2: commit → push → tag `v2.0.0` → GitHub release (auto) → twine → PyPI as `lion-os-desktop`.
- Test via `py -3 -m pytest tests/ -q`.

---

### Task 1: Settings app overhaul

**Files:**
- Modify: `lionos/apps/settings.py`
- Test: `tests/test_settings_app.py` (new)

**Interfaces:**
- Produces: Settings sections: **Appearance** (theme, accent picker, wallpaper), **Devices & Drivers** (re-probe, enable/disable), **Motion** (Full/Reduced/None), **Sound** (toggle + volume), **Statusline** (widget toggles), **System** (session resume, focus off, reset, About/Health).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_settings_app.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
from lionos.kernel import LionOS


def test_settings_launches_and_draws():
    os_ = LionOS()
    os_._no_draw = False
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    inst = os_.launch("Settings")
    for _ in range(4):
        os_._dt = 0.016
        os_._update(os_._dt)
    assert inst.hydrated
    os_._needs_redraw = True
    os_._draw()
    pygame.display.flip()


def test_settings_sections_exposed():
    os_ = LionOS()
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    inst = os_.launch("Settings")
    assert hasattr(inst, "sections") and len(inst.sections) >= 4
```

- [ ] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_settings_app.py -v` → FAIL (no `sections`).

- [ ] **Step 3: Implement** — rewrite `settings.py` with a section-tab layout and controls wiring to kernel APIs: theme dropdown → `os.set_theme`, accent swatches → `os.apply_accent`, wallpaper list → `config.wallpaper` + invalidate, motion radio → `config.motion`, sound toggle → `config.sound_enabled` + `os.sound.enabled`, statusline checkboxes → `config.statusline`, session resume toggle, focus-off list, Devices re-probe, reset button.

- [ ] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_settings_app.py -v` → 2 passed. Full suite + smoke.

- [ ] **Step 5: Commit**

```bash
git add lionos/apps/settings.py tests/test_settings_app.py
git commit -m "feat(apps): Settings overhaul — Appearance/Devices/Motion/Sound/Statusline/System"
```

---

### Task 2: Version bump to 2.0.0

**Files:**
- Modify: `pyproject.toml`, `lionos/__init__.py`, `README.md`

**Interfaces:**
- Produces: `version = "2.0.0"` everywhere; `__version__`/`__build__ = "2.0.0"`; `__codename__ = "Majestic"`; README badge `version-2.0.0`; release wheel URL `lion_os_desktop-2.0.0-...`.

- [ ] **Step 1: Update `pyproject.toml`** — `version = "2.0.0"`, description unchanged.
- [ ] **Step 2: Update `lionos/__init__.py`** — `__version__ = "2.0.0"`, `__build__ = "2.0.0"`, `__codename__ = "Majestic"`.
- [ ] **Step 3: Update `README.md`** — badge → `version-2.0.0`; release URL → `v2.0.0/lion_os_desktop-2.0.0-py3-none-any.whl`; add a v2.0.0 "Majestic" note summarizing the driver framework, vector icons, persistence, chrome, and power features.
- [ ] **Step 4: Verify consistency** — `grep -rn "2.0.0\|v2.0.0" README.md pyproject.toml lionos/__init__.py | head`.
- [ ] **Step 5: Commit**

```bash
git add pyproject.toml lionos/__init__.py README.md
git commit -m "chore: bump to Lion-OS 2.0.0 Majestic"
```

---

### Task 3: Build + fresh-venv verify + release

**Files:**
- N/A (process)

**Interfaces:**
- Produces: `dist/lion_os_desktop-2.0.0-py3-none-any.whl` + `.tar.gz`; GitHub Release `v2.0.0` with assets; PyPI `lion-os-desktop 2.0.0` live.

- [ ] **Step 1: Clean build** — `rm -rf build dist *.egg-info && py -3 -m build`
- [ ] **Step 2: Fresh-venv verify** — install the wheel in a clean venv; run `python -m lionos --headless`; check `lionos --version` → `Lion-OS 2.0.0`.
- [ ] **Step 3: Full suite + smoke**
- [ ] **Step 4: Push + tag** — `git push origin main`, `git tag v2.0.0`, `git push origin v2.0.0` (release workflow builds + attaches assets).
- [ ] **Step 5: Publish PyPI** — `twine upload dist/*` with the token (env var only, never committed).
- [ ] **Step 6: Final verification** — `pip install --no-cache-dir lion-os-desktop` in a clean venv → `lionos --version` → `Lion-OS 2.0.0`; confirm GitHub release assets + PyPI files.
- [ ] **Step 7: Commit** (any docs)

---

## Self-Review notes

- **Spec coverage:** Phase 6 covers §6.25 (Settings overhaul), §6.26 (config hardening — largely done across prior phases), §6.28 (release 2.0.0). The full spec's features are implemented across Phases 1-6.
- **No placeholders:** concrete steps + commands.
- **Type consistency:** all kernel APIs used by Settings (`set_theme`, `apply_accent`, `wallpaper_names`, `motion_ok`, `drivers`, `statusline`) were defined in Phases 1-5.
