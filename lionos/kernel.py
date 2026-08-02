"""Lion-OS kernel — the main desktop environment and event loop.

Refined for performance (cached window chrome, prerendered wallpaper,
dirty-flag redraw), a complete shell (desktop icons, power menu, Alt-Tab,
window animations) and an evolved identity (animated theme transitions,
shared app-icon tiles, upgraded launcher and login).
"""

from __future__ import annotations

import os
import random
import sys
import time
from typing import Dict, List, Optional

import pygame

from . import __version__
from .config import ConfigStore, LionConfig, ensure_config_dir
from .theme import Theme, THEMES, blend, accented
from .wizard import WIZARD_STEPS, load_profile, save_profile
from . import activity as _activity
from . import session as _session
from .clipboard import Clipboard
from .sound import SoundTheme
from .wm import (Window, WindowManager, TITLEBAR_H,
                 WINDOW_STATE_MAXIMIZED, WINDOW_STATE_MINIMIZED)
from .widgets import Menu, Toast, Notification, draw_app_tile, draw_glass_panel, rounded_rect
from .icons import APP_ICONS, IconCache, glyph_scene
from .loop import MAX_DT, FrameBudget, DirtyTracker, PerfCounters
from .drivers import build_driver_bus

BOOT_LINES = [
    ("Lion-OS Kernel v" + __version__, True),
    ("Initializing graphics subsystem...", False),
    ("Loading window manager...", False),
    ("Mounting virtual filesystem...", False),
    ("Starting services...", False),
    ("Loading desktop environment...", False),
    ("Pride edition ready.", True),
]

# Desktop icons shown on the wallpaper. Each is (label, app name).
DESKTOP_ICONS = [
    ("Calculator", "Calculator"),
    ("Terminal", "Terminal"),
    ("File Manager", "File Manager"),
    ("Text Editor", "Text Editor"),
    ("Notes", "Notes"),
    ("Paint", "Paint"),
    ("Settings", "Settings"),
    ("Media Player", "Media Player"),
]

DESKTOP_TILE = 84          # desktop icon tile size
DESKTOP_GAP = 12
DESKTOP_START = 16

THEME_TRANSITION_TIME = 0.4

WORKSPACE_COUNT = 4


class LionOS:
    """The main desktop environment."""

    def __init__(self, config: LionConfig = None):
        self.config_store = ConfigStore()
        self.config = config or self.config_store.cfg
        self.theme: Theme = THEMES.get(self.config.theme, THEMES["dark"])

        pygame.init()
        pygame.font.init()
        pygame.display.set_caption("Lion-OS — Pride Edition")
        self.screen_w = self.config.screen_w
        self.screen_h = self.config.screen_h

        flags = 0
        if self.config.resolution == "fullscreen":
            flags = pygame.FULLSCREEN | pygame.SCALED
        try:
            self.screen = pygame.display.set_mode(
                (self.screen_w, self.screen_h), flags,
                vsync=1 if self.config.vsync else 0)
        except (TypeError, ValueError):
            self.screen = pygame.display.set_mode((self.screen_w, self.screen_h), flags)
        self.screen_rect = self.screen.get_rect()

        self.clock = pygame.time.Clock()
        self.icon_cache = IconCache()
        self._frame_budget = FrameBudget(60)
        self._dirty = DirtyTracker()
        self._perf = PerfCounters()
        self.fps = 60.0
        # driver bus — auto-probes and auto-configures every driver at boot
        self.drivers = build_driver_bus(self.config)
        self.driver_probe_lines = self.drivers.probe_all()
        self._write_driver_auto_config()
        self.running = True
        self.booted = False
        self.logged_in = False
        self.shutdown = False

        # state
        self.wm = WindowManager(self.screen_rect, self.theme)
        self.apps_registry = None          # set by apps loader
        self.launched: Dict[str, object] = {}   # singleton instances
        self.instances: List = []          # all running app instances
        self.toasts: List[Toast] = []
        self._notifications: List[Notification] = []
        self.notification_center_open = False
        self.menus: List[Menu] = []
        self.launcher_open = False
        self.launcher_search = ""
        self.launcher_filter = ""
        self.launcher_category = "All"
        self.workspace = 0
        self._launcher_idx = 0
        self.power_menu_open = False
        self.context_menu = None           # (pos, items)

        # boot state
        self._boot_progress = 0.0
        self._boot_lines_done = 0
        self._boot_ready = False
        self._boot_glow = 0.0

        # login state
        self._login_attempt = 0
        self._login_pw = ""
        self._login_error = ""
        self._login_focus = 0
        self._login_clock = time.time()
        self._login_shake = 0.0

        # first-boot wizard
        self.wizard_active = not self.config.wizard_done
        self._wizard_step = 0
        self._wizard_input = ""
        self.wizard_profile = load_profile()

        # persistence & identity
        self.clipboard = Clipboard()
        self._summary = ""
        self._summary_t = 0.0
        self.sound = SoundTheme(self.drivers.get("audio") if hasattr(self, "drivers") else None)
        self.sound.enabled = self.config.sound_enabled
        self.sound.set_volume(self.config.volume)

        # theme transition
        self._theme_from: Optional[Theme] = None
        self._theme_to: Optional[Theme] = None
        self._theme_t = 0.0

        # desktop icons
        self._desktop_sel = None           # selected icon label
        self._desktop_click_time = 0.0
        self._desktop_click_icon = None

        # power / reboot
        self._shutting_down = False
        self._restarting = False
        self._power_fade = 0.0

        # decorations
        self._show_clock_sec = False

        self._bg_shift = 0.0
        self._dt = 0.016

        # performance
        self._font_cache: Dict[tuple, pygame.font.Font] = {}
        self._wallpaper_surf = None
        self._wallpaper_glow = None
        self._wallpaper_key = None
        self._needs_redraw = True

        # reusable full-screen overlays (avoid a fresh screen-sized SRCALPHA
        # surface allocation on every frame)
        self._dim_surf = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        self._glow_surf = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        self._fade_surf = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        self._taskbar_surf = pygame.Surface((self.screen_w, 46), pygame.SRCALPHA)
        self._window_fade_cache: Dict[tuple, pygame.Surface] = {}
        self._content_ph_cache: Dict[tuple, pygame.Surface] = {}
        self._tooltip_surf = None      # reusable tooltip background

        # hidden for testing
        self._no_draw = os.environ.get("LION_OS_HEADLESS") == "1"
        self._smoke_test_done = False

        self._load_apps()

    # ------------------------------------------------------------------ fonts
    def get_font(self, size: int, bold=False):
        key = (size, bold)
        if key not in self._font_cache:
            self._font_cache[key] = pygame.font.Font(None, size)
            if bold:
                self._font_cache[key].set_bold(True)
        return self._font_cache[key]

    # ------------------------------------------------------------------ apps
    def _load_apps(self):
        from .apps import load_apps
        self.apps_registry = load_apps()

    def launch(self, name: str, **kwargs):
        cls = self.apps_registry.get(name)
        if cls is None:
            self.show_toast("Lion-OS", f"App '{name}' not found", "error")
            return None
        if cls.singleton and name in self.launched and self.launched[name]:
            inst = self.launched[name]
            if inst.window.state == WINDOW_STATE_MINIMIZED:
                inst.window.restore()
            self.wm.focus(inst.window)
            return inst
        inst = cls(self, **kwargs)
        self.instances.append(inst)
        if cls.singleton:
            self.launched[name] = inst
        inst.on_open()
        self.sound.play("open")
        _activity.log_event("app_launch", name)
        # remember app in MRU
        mru = list(self.config.mru_apps)
        if name in mru:
            mru.remove(name)
        mru.insert(0, name)
        self.config_store.set(mru_apps=mru[:8])
        self._needs_redraw = True
        return inst

    # -------------------------------------------------------------- chrome
    def wallpaper_names(self):
        return ["gradient", "aurora", "grid", "dots", "mountain"]

    def motion_ok(self):
        """Whether animations/transitions should run (accessibility gate)."""
        return self.config.motion != "none" and self.config.anim_enabled

    def apply_accent(self, rgb):
        self.config.accent_override = "#{:02x}{:02x}{:02x}".format(*rgb[:3])
        self.theme = accented(self.theme, tuple(rgb[:3]))
        self.wm.theme = self.theme
        self._wallpaper_key = None
        self._needs_redraw = True

    def launcher_catalog(self):
        """Data-driven app manifest rows for the catalog launcher."""
        rows = []
        for name, cls in self.apps_registry.all().items():
            rows.append({
                "name": name,
                "desc": getattr(cls, "description", "") or "",
                "version": getattr(cls, "version", "1.0"),
                "category": getattr(cls, "category", "Utilities"),
            })
        return rows

    def statusline_widgets(self):
        return list(self.config.statusline)

    def set_workspace(self, n):
        self.workspace = max(0, min(WORKSPACE_COUNT - 1, int(n)))
        self._needs_redraw = True

    def tile_window(self, direction):
        win = self.wm.focused
        if win is None:
            return
        sr = self.screen_rect
        hw, hh = sr.width // 2, sr.height // 2
        if direction == "left":
            win.rect = pygame.Rect(sr.x, sr.y, hw, sr.height)
        elif direction == "right":
            win.rect = pygame.Rect(sr.x + hw, sr.y, hw, sr.height)
        elif direction == "up":
            win.rect = pygame.Rect(sr.x, sr.y, sr.width, hh)
        elif direction == "down":
            win.rect = pygame.Rect(sr.x, sr.y + hh, sr.width, hh)
        elif direction == "center":
            win.rect = pygame.Rect(sr.x + sr.width // 4, sr.y + sr.height // 4,
                                   sr.width // 2, sr.height // 2)
        else:
            return
        win.restore_rect = pygame.Rect(win.rect)
        self._dirty.mark(win.rect)
        self._needs_redraw = True

    # ------------------------------------------------------------------ utils
    def show_toast(self, title, message, kind="info"):
        self.toasts.append(Toast(title, message, self.theme, kind=kind))
        self.sound.play("toast")

    # ------------------------------------------------------- notifications
    def notify(self, title, body, app="", kind="info", action=None):
        self._notifications.append(Notification(title, body, app=app, kind=kind))
        self.sound.play("toast")
        self._needs_redraw = True

    def clear_notifications(self):
        self._notifications = []
        self._needs_redraw = True

    def _update_notifications(self, dt):
        for n in self._notifications:
            n.update(dt)
        self._notifications = [n for n in self._notifications if not n.done]
        if len(self.toasts) > 4:
            self.toasts.pop(0)
        self._needs_redraw = True

    def open_menu(self, items, pos):
        font = self.get_font(self.config.font_size)
        m = Menu(items, pos, font, self.theme)
        self.menus.append(m)
        self._needs_redraw = True

    def close_menus(self):
        for m in self.menus:
            m.visible = False
        self.menus = []
        self.context_menu = None
        self._needs_redraw = True

    def set_theme(self, name: str):
        if name not in THEMES:
            return
        _activity.log_event("theme_change", name)
        self.config_store.set(theme=name)
        self.config.theme = name
        target = THEMES[name]
        if self.motion_ok() and not self._no_draw:
            self._theme_from = self.theme
            self._theme_to = target
            self._theme_t = 0.0
        else:
            self._theme_from = self._theme_to = None
        # switch immediately (existing contract); transition blends via _theme_from
        self.theme = target
        self.wm.theme = self.theme
        self._wallpaper_key = None
        for w in self.wm.windows:
            w.invalidate_chrome()
        self._needs_redraw = True

    def set_wallpaper(self, kind=None, color=None):
        if kind:
            self.config_store.set(wallpaper=kind)
            self.config.wallpaper = kind
        if color:
            self.config_store.set(wallpaper_color=color)
            self.config.wallpaper_color = color
        self._wallpaper_key = None
        self._needs_redraw = True

    # ------------------------------------------------------------------ boot
    def _update_boot(self, dt):
        self._boot_progress += dt * 14
        self._boot_lines_done = min(len(BOOT_LINES) - 1,
                                    int(self._boot_progress / (100 / len(BOOT_LINES))))
        if self._boot_progress >= 100:
            self._boot_ready = True

    # ------------------------------------------------------------------ loop
    def run(self):
        # graceful shutdown: persist the session on SIGINT/SIGTERM
        import signal as _signal

        def _on_term(*_a):
            self._save_session_on_exit()
            self.running = False

        try:
            _signal.signal(_signal.SIGINT, _on_term)
            _signal.signal(_signal.SIGTERM, _on_term)
        except (ValueError, OSError):
            pass
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
                    # Present only the dirty regions when few, else full-screen.
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
        self._save_session_on_exit()
        self.shutdown = True
        pygame.quit()
        return 0

    def _any_animating(self) -> bool:
        for w in self.wm.windows:
            if w.anim_active():
                return True
        return False

    def _headless_tick(self):
        """When LION_OS_HEADLESS=1, keep the loop alive without rendering
        so automated smoke tests can drive it."""
        if self._boot_progress >= 100 and self.logged_in:
            if self._smoke_test_done:
                self.running = False

    def _update(self, dt):
        self._bg_shift += dt * 0.05
        self._boot_glow += dt * 1.6
        if not self.booted:
            self._update_boot(dt)
            if self._boot_ready:
                self.booted = True
                self.sound.play("boot")
                self._needs_redraw = True
            return

        if not self.logged_in:
            self._login_clock += dt
            if self._login_shake > 0:
                self._login_shake = max(0.0, self._login_shake - dt * 6)
            return

        self._update_theme_transition(dt)

        # tick running drivers each frame
        self.drivers.update(dt)

        # session summary fades out over time
        if self._summary_t > 0:
            self._summary_t -= dt
        self._update_notifications(dt)

        # power-off fade
        if self._shutting_down or self._restarting:
            self._power_fade = min(1.0, self._power_fade + dt * 1.2)
            if self._power_fade >= 1.0:
                if self._restarting:
                    self._restart()
                else:
                    self.running = False
            self._needs_redraw = True
            return

        for t in self.toasts:
            t.update(dt)
        self.toasts = [t for t in self.toasts if not t.done]

        # step window animations
        animating = False
        for w in self.wm.windows:
            if w.anim_active():
                w.step_anim(dt)
                animating = True
        if animating:
            self._needs_redraw = True

        for inst in list(self.instances):
            if inst.closed:
                if inst in self.instances:
                    self.instances.remove(inst)
                if self.apps_registry and inst.window.app and \
                   self.launched.get(inst.window.app.name) is inst:
                    self.launched.pop(inst.window.app.name, None)
                self._needs_redraw = True
                continue
            inst.step_hydration(dt)
            if inst.window.state != WINDOW_STATE_MINIMIZED:
                inst.update(dt)
            # window content rect may have changed
            if inst.window.content_rect != inst.rect:
                self._dirty.mark(inst.window.rect)
                inst.rect = pygame.Rect(inst.window.content_rect)
                inst.on_resize(inst.rect)
            inst._last = pygame.Rect(inst.window.content_rect)
            if inst.window._dirty:
                self._needs_redraw = True
                inst.window._dirty = False

    def _update_theme_transition(self, dt):
        if self._theme_from is None or self._theme_to is None:
            return
        self._theme_t = min(1.0, self._theme_t + dt / THEME_TRANSITION_TIME)
        self.theme = self._theme_from.interpolate(self._theme_to, self._theme_t)
        self.wm.theme = self.theme
        for w in self.wm.windows:
            w.invalidate_chrome()
        self._wallpaper_key = None
        self._needs_redraw = True
        if self._theme_t >= 1.0:
            self.theme = self._theme_to
            self.wm.theme = self.theme
            self._theme_from = self._theme_to = None
            self._needs_redraw = True

    def _restart(self):
        self._restarting = False
        self._power_fade = 0.0
        self.booted = False
        self.logged_in = False
        self._boot_progress = 0.0
        self._boot_lines_done = 0
        self._boot_ready = False
        # close all windows and start fresh
        for inst in list(self.instances):
            inst.closed = True
        self.instances = []
        self.launched = {}
        self.wm.windows = []
        self.wm.focused = None
        self._needs_redraw = True

    # ------------------------------------------------------------------ event
    def _handle_event(self, event):
        if event.type == pygame.QUIT:
            self._request_quit()
            return

        if not self.booted:
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_SPACE, pygame.K_RETURN):
                    self._skip_boot()
            return

        if not self.logged_in:
            self._handle_login_event(event)
            return

        self._needs_redraw = True

        # context menu
        if self.context_menu:
            consumed = self.context_menu[2].handle_event(event, event.pos, self.theme) if hasattr(self.context_menu[2], "handle_event") else False
            if not consumed:
                self.context_menu = None
            return

        # Alt-Tab switcher
        if self.wm.alt_tab_active:
            self._handle_alt_tab_event(event)
            return

        if event.type == pygame.KEYDOWN:
            # global hotkeys
            if event.key == pygame.K_LSUPER or event.key == pygame.K_RSUPER:
                self.launcher_open = not self.launcher_open
                self.power_menu_open = False
                self.launcher_search = ""
                return
            if event.key == pygame.K_TAB and (event.mod & pygame.KMOD_ALT):
                self.wm.start_alt_tab()
                return
            if event.key == pygame.K_ESCAPE:
                if self.launcher_open:
                    self.launcher_open = False
                    return
                if self.menus:
                    self.close_menus()
                    return

        # power menu
        if self.power_menu_open:
            self._handle_power_menu(event)
            return

        # launcher (fullscreen overlay) gets priority when open
        if self.launcher_open:
            self._handle_launcher_event(event)
            return

        # desktop right-click context menu
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            if not self.wm.top_at(event.pos):
                self._open_desktop_menu(event.pos)
                return

        # desktop icon interactions (left-click, double-click)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.wm.top_at(event.pos):
                self._handle_desktop_click(event)
                return

        # taskbar interactions
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) and event.button == 1:
            tb_h = 46
            tb_top = self.screen_h - tb_h
            pos = event.pos
            if pos[1] >= tb_top:
                start_r = pygame.Rect(10, tb_top + 6, 34, 34)
                if start_r.collidepoint(pos):
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        self.launcher_open = not self.launcher_open
                        self.power_menu_open = False
                        return
                # power menu toggle (right of start)
                power_r = pygame.Rect(48, tb_top + 6, 24, 24)
                if power_r.collidepoint(pos):
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        self.power_menu_open = not self.power_menu_open
                        self.launcher_open = False
                        return
                # running app icons
                x = 82
                for inst in list(self.instances):
                    if inst.closed:
                        continue
                    item = pygame.Rect(x, tb_top + 6, 44, 34)
                    if item.collidepoint(pos):
                        if event.type == pygame.MOUSEBUTTONDOWN:
                            if inst.window.state == WINDOW_STATE_MINIMIZED:
                                inst.window.restore()
                                self.wm.focus(inst.window)
                            elif inst.window is self.wm.focused:
                                inst.window.minimize()
                            else:
                                self.wm.focus(inst.window)
                        return
                    x += 52
                    if x > self.screen_w - 260:
                        break
                # clock area right-click opens power? keep simple: ignore

        # window manager first
        if self.wm.handle_event(event):
            return

        # dispatch to focused app
        win = self.wm.focused
        if win and win.state != WINDOW_STATE_MINIMIZED and win.app:
            local = event.pos if hasattr(event, "pos") else None
            cr = win.content_rect
            if local and cr.collidepoint(local):
                local_pos = (local[0] - cr.x, local[1] - cr.y)
            elif local and win.titlebar_rect.collidepoint(local):
                local_pos = None
            else:
                local_pos = None
            if local_pos is not None and win.app.handle_event(event, local_pos):
                return

    # ---------------------------------------------------------------- boot UI
    def _skip_boot(self):
        self._boot_progress = 100
        self._boot_ready = True
        self.booted = True
        self._needs_redraw = True

    # --------------------------------------------------------------- login UI
    def _handle_login_event(self, event):
        if getattr(self, "wizard_active", False):
            self._handle_wizard_event(event)
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self._login_attempt += 1
                if self.config.auto_login or not self.config.password or \
                   self._login_pw == self.config.password:
                    self._do_login()
                else:
                    self._login_error = "Incorrect password. Try again."
                    self._login_pw = ""
                    self._login_shake = 0.6
            elif event.key == pygame.K_BACKSPACE:
                self._login_pw = self._login_pw[:-1]
            elif getattr(event, "unicode", "") and event.unicode.isprintable():
                self._login_pw += event.unicode

    def _do_login(self):
        self.logged_in = True
        self._login_error = ""
        self.launcher_open = False
        # reopen running apps after login
        from .apps import AUTO_LAUNCH
        for app_name in AUTO_LAUNCH:
            try:
                self.launch(app_name)
            except Exception:
                pass
        self.show_toast("Welcome", f"Welcome back, {self.config.username}!", "success")
        if self.config.session_resume:
            self._restore_session(_session.recover_session())
        _activity.log_event("login", self.config.username)
        summary = _activity.session_summary()
        if summary:
            self._summary = summary
            self._summary_t = 5.0

    # ----------------------------------------------------------- persistence
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
                "workspace": self.workspace}

    def _restore_session(self, data):
        if not data or not data.get("windows"):
            return
        if data.get("theme") and data["theme"] in THEMES:
            self.config.theme = data["theme"]
        for w in data["windows"]:
            cls = self.apps_registry.get(w["app"]) if self.apps_registry else None
            if cls is None:
                continue
            try:
                inst = cls(self)
                if len(w.get("rect", [])) == 4:
                    inst.window.rect = pygame.Rect(*w["rect"])
                    inst.rect = pygame.Rect(inst.window.content_rect)
                inst.window.begin_anim("open")
                if w.get("minimized"):
                    inst.window.state = WINDOW_STATE_MINIMIZED
                if inst not in self.instances:
                    self.instances.append(inst)
            except Exception:
                continue

    def _save_session_on_exit(self):
        if not getattr(self, "logged_in", False):
            return
        data = self._collect_session()
        _session.save_session(data)
        _session.checkpoint_session(data)

    def clipboard_copy(self, value):
        if self.config.clipboard_enabled:
            self.clipboard.copy("text", value)

    def clipboard_paste(self):
        if self.config.clipboard_enabled:
            return self.clipboard.paste()
        return ""

    def _draw_session_summary(self):
        alpha = min(1.0, self._summary_t)
        s = pygame.Surface((self.screen_w, 70), pygame.SRCALPHA)
        s.fill((20, 20, 30, int(200 * alpha)))
        font = self.get_font(18)
        img = font.render(self._summary, True, self.theme.text)
        s.blit(img, (24, 24))
        self.screen.blit(s, (0, self.screen_h - 90))

    # ----------------------------------------------------------- wizard UI
    def _handle_wizard_event(self, event):
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._advance_wizard()
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_LEFT:
            self._cycle_theme(-1)
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_RIGHT:
            self._cycle_theme(1)
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_BACKSPACE:
            self._wizard_input = self._wizard_input[:-1]
        elif getattr(event, "unicode", "") and event.unicode.isprintable():
            self._wizard_input += event.unicode

    def _cycle_theme(self, delta):
        names = list(THEMES)
        idx = names.index(self.config.theme) if self.config.theme in names else 0
        self.config.theme = names[(idx + delta) % len(names)]
        self._needs_redraw = True

    def _advance_wizard(self):
        step = WIZARD_STEPS[self._wizard_step]
        if step == "name" and self._wizard_input:
            self.wizard_profile["name"] = self._wizard_input
            self.config.username = self._wizard_input
        elif step == "theme":
            self.wizard_profile["theme"] = self.config.theme
        elif step == "pin":
            self.wizard_profile["pinned"] = self.config.pinned_apps or \
                ["Terminal", "File Manager", "Notes"]
        elif step == "matters":
            self.wizard_profile["matters"] = "general"
        self._wizard_step += 1
        self._wizard_input = ""
        self._needs_redraw = True
        if self._wizard_step >= len(WIZARD_STEPS):
            save_profile(self.wizard_profile)
            self.config.wizard_done = True
            self.config.save()
            self.wizard_active = False
            if self.config.auto_login or not self.config.password:
                self._do_login()
        self._needs_redraw = True

    # ---------------------------------------------------------- desktop icons
    def _desktop_icon_rects(self):
        out = []
        x = DESKTOP_START
        y = DESKTOP_START
        for label, app in DESKTOP_ICONS:
            if app not in self.apps_registry.all():
                continue
            out.append(((label, app), pygame.Rect(x, y, DESKTOP_TILE, DESKTOP_TILE + 22)))
            x += DESKTOP_TILE + DESKTOP_GAP
            if x + DESKTOP_TILE > self.screen_w - 40:
                x = DESKTOP_START
                y += DESKTOP_TILE + 40
        return out

    def _handle_desktop_click(self, event):
        pos = event.pos
        now = time.time()
        for (label, app), rect in self._desktop_icon_rects():
            if rect.collidepoint(pos):
                if label == self._desktop_click_icon and now - self._desktop_click_time < 0.4:
                    self.launch(app)
                    self._desktop_click_icon = None
                else:
                    self._desktop_click_icon = label
                    self._desktop_click_time = now
                self._desktop_sel = label
                return
        self._desktop_sel = None
        self._desktop_click_icon = None

    def _open_desktop_menu(self, pos):
        items = [
            ("Open Terminal", lambda: self.launch("Terminal")),
            ("Open Settings", lambda: self.launch("Settings")),
            ("Refresh", lambda: self._needs_redraw or None),
        ]
        self.context_menu = (pos, items)
        self.open_menu(items, pos)

    # ------------------------------------------------------------- launcher UI
    def _handle_launcher_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.launcher_open = False
                return
            if event.key == pygame.K_BACKSPACE:
                self.launcher_search = self.launcher_search[:-1]
                self.launcher_category = "All"
                return
            if event.key == pygame.K_DOWN or event.key == pygame.K_UP:
                results = self._launcher_results()
                if results:
                    n = len(results)
                    step = 1 if event.key == pygame.K_DOWN else -1
                    self._launcher_idx = (self._launcher_idx + step) % n
                return
            if event.key == pygame.K_RIGHT or event.key == pygame.K_LEFT:
                cols = 8
                results = self._launcher_results()
                if results:
                    n = len(results)
                    step = 1 if event.key == pygame.K_RIGHT else -1
                    self._launcher_idx = (self._launcher_idx + step * cols) % n
                return
            if getattr(event, "unicode", "") and (event.unicode.isprintable() or event.unicode == " "):
                self.launcher_search += event.unicode
                self.launcher_category = "All"
                self._launcher_idx = 0
                return
            if event.key == pygame.K_RETURN:
                results = self._launcher_results()
                if results:
                    idx = getattr(self, "_launcher_idx", 0) % len(results)
                    self.launch(results[idx].name)
                    self.launcher_open = False
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # category tabs
            tab = self._launcher_tab_at(event.pos)
            if tab is not None:
                self.launcher_category = tab
                self._launcher_idx = 0
                return
            # click on app tile
            name = self._launcher_tile_at(event.pos)
            if name is not None:
                self.launch(name)
                self.launcher_open = False

    def _launcher_categories(self):
        cats = ["All"]
        for a in self.apps_registry.all().values():
            if a.category not in cats:
                cats.append(a.category)
        return cats

    def _launcher_results(self):
        q = self.launcher_search.lower()
        apps = list(self.apps_registry.all().values())
        if self.launcher_category != "All":
            apps = [a for a in apps if a.category == self.launcher_category]
        if q:
            apps = [a for a in apps if q in a.name.lower() or q in a.category.lower() or
                    q in a.description.lower()]
        return apps

    def _launcher_tab_at(self, x, y):
        if not self.launcher_open:
            return None
        cats = self._launcher_categories()
        fx = self.get_font(16)
        tx = self.screen_w // 2 - 200
        for c in cats:
            w = fx.size(c)[0] + 24
            r = pygame.Rect(tx, 148, w, 30)
            if r.collidepoint((x, y)):
                return c
            tx += w + 6
        return None

    def _launcher_tile_at(self, x, y):
        if not self.launcher_open:
            return None
        results = self._launcher_results()
        if not results:
            return None
        cols = 8
        size = 96
        start_x = (self.screen_w - cols * size) // 2
        for i, app in enumerate(results):
            cx = start_x + (i % cols) * size
            cy = 210 + (i // cols) * size
            if x in range(cx, cx + size) and y in range(cy, cy + size):
                return app.name
        return None

    # -------------------------------------------------------------- power menu
    def _handle_power_menu(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.power_menu_open = False
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if not self._power_menu_panel().collidepoint(pos):
                self.power_menu_open = False
                return
            action = self._power_menu_action_at(pos)
            if action == "lock":
                self._do_lock()
            elif action == "restart":
                self._restarting = True
                self.power_menu_open = False
                self._power_fade = 0.0
            elif action == "shutdown":
                self._shutting_down = True
                self.power_menu_open = False
                self._power_fade = 0.0
            elif action == "sleep":
                self._do_lock()

    def _do_lock(self):
        self.logged_in = False
        self.power_menu_open = False
        self.launcher_open = False
        self._login_pw = ""
        self._login_error = ""
        self._login_clock = time.time()
        self._needs_redraw = True

    def _power_menu_panel(self):
        w, h = 260, 300
        return pygame.Rect(self.screen_w // 2 - w // 2, self.screen_h // 2 - h // 2, w, h)

    def _power_menu_actions(self):
        return [("lock", "Lock", "🔒"), ("sleep", "Sleep", "😴"),
                ("restart", "Restart", "🔄"), ("shutdown", "Shut Down", "⏻")]

    def _power_menu_action_at(self, pos):
        panel = self._power_menu_panel()
        for i, (key, label, icon) in enumerate(self._power_menu_actions()):
            r = pygame.Rect(panel.x + 20, panel.y + 60 + i * 56, panel.width - 40, 44)
            if r.collidepoint(pos):
                return key
        return None

    # ----------------------------------------------------------- alt-tab event
    def _handle_alt_tab_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_TAB and (event.mod & pygame.KMOD_ALT):
                self.wm.alt_tab_cycle()
                return
        if event.type == pygame.KEYUP:
            if event.key == pygame.K_TAB or event.key in (pygame.K_LALT, pygame.K_RALT):
                self.wm.alt_tab_activate()
                return

    def _request_quit(self):
        self.running = False

    # ------------------------------------------------------------- window chrome
    def _hit_window_button(self, win: Window, pos) -> Optional[str]:
        """Return which chrome button was clicked: close/min/max."""
        if win.state == WINDOW_STATE_MAXIMIZED:
            return None
        tr = win.titlebar_rect
        b = 16
        right = tr.right - 8
        close_rect = pygame.Rect(right - b, tr.centery - b // 2, b, b)
        max_rect = pygame.Rect(right - 3 * b - 8, tr.centery - b // 2, b, b)
        min_rect = pygame.Rect(right - 2 * b - 8, tr.centery - b // 2, b, b)
        if close_rect.collidepoint(pos):
            if win.app:
                win.app.close()
            else:
                self.wm.remove_window(win)
            return "close"
        if max_rect.collidepoint(pos):
            win.toggle_maximize(self.screen_rect)
            return "max"
        if min_rect.collidepoint(pos):
            win.minimize()
            return "min"
        return None

    # ------------------------------------------------------------------ draw
    def _draw(self):
        self._draw_wallpaper()
        self._draw_desktop_icons()
        self._draw_windows()
        self._draw_launcher()
        self._draw_power_menu()
        self._draw_alt_tab()
        self._draw_context_menu()
        self._draw_taskbar()
        self._draw_toasts()
        if self._summary and self._summary_t > 0:
            self._draw_session_summary()
        if self._shutting_down:
            self._draw_power_fade("Shutting down…")
        elif self._restarting:
            self._draw_power_fade("Restarting…")
        if not self.booted:
            self._draw_boot()
        elif not self.logged_in:
            self._draw_login()
        if self.config.show_fps:
            f = self.get_font(14)
            img = f.render(f"{self.fps:.0f} fps", True, self.theme.text)
            self.screen.blit(img, (8, 8))

    def _draw_power_fade(self, label):
        s = self._fade_surf
        s.fill((0, 0, 0, int(255 * self._power_fade)))
        self.screen.blit(s, (0, 0))
        if self._power_fade > 0.5:
            font = self.get_font(30)
            img = font.render(label, True, (255, 255, 255))
            self.screen.blit(img, img.get_rect(center=(self.screen_w // 2, self.screen_h // 2)))

    def _ensure_wallpaper(self):
        key = (self.theme.name, self.theme.wallpaper_top, self.theme.wallpaper_bottom,
               self.theme.accent, self.screen_w, self.screen_h, self.config.wallpaper)
        if key == self._wallpaper_key and self._wallpaper_surf is not None:
            return
        surf = pygame.Surface((self.screen_w, self.screen_h))
        top = self.theme.wallpaper_top
        bottom = self.theme.wallpaper_bottom
        h = self.screen_h
        w = self.screen_w
        style = self.config.wallpaper
        # base vertical gradient
        for y in range(0, h, 2):
            t = y / max(1, h)
            pygame.draw.line(surf, blend(top, bottom, t), (0, y), (w, y))
        if style == "aurora":
            for i in range(4):
                cx0 = (w * (i + 0.5)) // 4
                cy0 = h // 2
                for rr in range(h // 2, 0, -10):
                    a = 0.10 * (1 - rr / (h // 2))
                    col = blend((0, 0, 0), self.theme.glow, a)
                    pygame.draw.circle(surf, col, (cx0, cy0), rr, 2)
        elif style == "grid":
            line_c = blend(bottom, (255, 255, 255), 0.07)
            for gx in range(0, w, 48):
                pygame.draw.line(surf, line_c, (gx, 0), (gx, h))
            for gy in range(0, h, 48):
                pygame.draw.line(surf, line_c, (0, gy), (w, gy))
        elif style == "dots":
            dot_c = blend(bottom, (255, 255, 255), 0.12)
            for gx in range(24, w, 48):
                for gy in range(24, h, 48):
                    pygame.draw.circle(surf, dot_c, (gx, gy), 2)
        elif style == "mountain":
            import random as _rnd
            layers = [self.theme.accent, self.theme.accent_alt, self.theme.glow]
            for i, col in enumerate(layers):
                rnd = _rnd.Random(42 + i)
                pts = [(0, h)]
                for j in range(1, 6):
                    pts.append((w * j / 6, h * (0.55 + rnd.random() * 0.22)))
                pts += [(w, h)]
                pygame.draw.polygon(surf, col, pts)
        self._wallpaper_surf = surf
        self._wallpaper_key = key

    def _draw_wallpaper(self):
        self._ensure_wallpaper()
        self.screen.blit(self._wallpaper_surf, (0, 0))
        # animated glow (drawn onto a single reusable surface, not a fresh one)
        cx = self.screen_w // 2
        cy = self.screen_h // 2
        g = self._glow_surf
        g.fill((0, 0, 0, 0))
        for i in range(3):
            radius = int(160 + (self._bg_shift % 1.0) * 60 + i * 80)
            alpha = 8 - i * 2
            pygame.draw.circle(g, self.theme.glow[:3] + (alpha,), (cx, cy), radius, 1)
        self.screen.blit(g, (0, 0))

    def _draw_desktop_icons(self):
        if not self.logged_in:
            return
        for (label, app), rect in self._desktop_icon_rects():
            cls = self.apps_registry.get(app)
            glyph = cls.icon if cls else "◈"
            hovered = rect.collidepoint(pygame.mouse.get_pos())
            selected = self._desktop_sel == label
            tile = pygame.Rect(rect.x, rect.y, rect.width, rect.height - 22)
            draw_app_tile(self.screen, tile, glyph, self.theme,
                          hovered=hovered, selected=selected,
                          icon_cache=self.icon_cache,
                          scene=APP_ICONS.get(app) or (glyph_scene(glyph) if glyph else None),
                          scene_id=app)
            font = self.get_font(14)
            limg = font.render(label, True,
                               self.theme.text if selected else self.theme.text_dim)
            self.screen.blit(limg, limg.get_rect(midtop=(tile.centerx, tile.bottom + 6)))

    def _draw_windows(self):
        # draw from back to front, only the active workspace
        for win in self.wm.windows:
            if not win.visible or win.state == WINDOW_STATE_MINIMIZED:
                continue
            if win.workspace != self.workspace:
                continue
            self._draw_window(win)
        self.wm.draw_snap_preview(self.screen, self.theme)

    def _draw_window(self, win: Window):
        rect = win.rect
        focused = win is self.wm.focused
        font = self.get_font(self.config.font_size)

        # scale for open/close/minimize animations
        scale = win.anim_scale
        alpha = win.anim_alpha
        if scale != 1.0:
            w = max(1, int(rect.width * scale))
            h = max(1, int(rect.height * scale))
            sx = rect.x + (rect.width - w) // 2
            sy = rect.y + (rect.height - h) // 2
            scaled_rect = pygame.Rect(sx, sy, w, h)
        else:
            scaled_rect = rect

        win.ensure_chrome(self.theme, focused, font, self.config.font_size)

        shadow = win._chrome.get("shadow")
        if shadow:
            self.screen.blit(shadow, (scaled_rect.x - 12, scaled_rect.y - 12))
        body = win._chrome.get("body")
        if body:
            self.screen.blit(body, scaled_rect.topleft)
        titlebar = win._chrome.get("titlebar")
        if titlebar:
            self.screen.blit(titlebar, (scaled_rect.x, scaled_rect.y))

        # window buttons (drawn per-frame for hover states)
        tr = pygame.Rect(scaled_rect.x, scaled_rect.y, scaled_rect.width, TITLEBAR_H)
        self._draw_window_buttons(win, tr)

        # content
        cr = pygame.Rect(scaled_rect.x, scaled_rect.y + TITLEBAR_H,
                         scaled_rect.width, max(0, scaled_rect.height - TITLEBAR_H))
        if cr.width > 0 and cr.height > 0 and win.app:
            if getattr(win.app, "hydrated", True):
                clip = pygame.Rect(cr)
                old = self.screen.get_clip()
                self.screen.set_clip(clip)
                try:
                    win.app.draw(self.screen, cr)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self._draw_error_screen(cr, e)
                self.screen.set_clip(old)
            else:
                # Structural pass: window chrome is visible immediately; app
                # content hydrates over the next frames.
                ph = self._content_placeholder_surf(cr.size, self.theme)
                self.screen.blit(ph, cr.topleft)

        # apply fade for close/minimize (reuse a cached size-keyed surface)
        if alpha < 255:
            fade = self._window_fade_cache.get(scaled_rect.size)
            if fade is None:
                fade = pygame.Surface(scaled_rect.size, pygame.SRCALPHA)
                self._window_fade_cache[scaled_rect.size] = fade
            fade.fill((0, 0, 0, 255 - alpha))
            self.screen.blit(fade, scaled_rect.topleft)

    def _draw_error_screen(self, rect, error):
        font = self.get_font(18)
        s = pygame.Surface(rect.size, pygame.SRCALPHA)
        s.fill((40, 20, 20, 220))
        img = font.render("Application error", True, (255, 200, 200))
        s.blit(img, (20, 20))
        detail = font.render(str(error)[:80], True, (255, 230, 230))
        s.blit(detail, (20, 50))
        self.screen.blit(s, rect.topleft)

    def _write_driver_auto_config(self):
        """Snapshot what the bus auto-configured (so overrides are a visible
        diff). Best-effort; never blocks boot."""
        try:
            from .config import ensure_config_dir
            import json as _json
            import os as _os
            snap = self.drivers.auto_config_snapshot()
            path = _os.path.join(ensure_config_dir(), "drivers.auto.json")
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(snap, f, indent=2)
        except Exception:
            pass

    def _content_placeholder_surf(self, size, theme):
        key = (size, theme.surface)
        s = self._content_ph_cache.get(key)
        if s is None:
            s = pygame.Surface(size, pygame.SRCALPHA)
            pygame.draw.rect(s, theme.surface + (255,), s.get_rect(),
                             border_radius=max(4, theme.radius // 2))
            self._content_ph_cache[key] = s
        return s

    def _draw_window_buttons(self, win: Window, tr):
        font = self.get_font(16)
        b = 16
        right = tr.right - 8
        cy = tr.centery
        mouse = pygame.mouse.get_pos()
        # minimize
        min_rect = pygame.Rect(right - 2 * b - 8, cy - b // 2, b, b)
        if min_rect.collidepoint(mouse):
            pygame.draw.rect(self.screen, self.theme.hover[:3] if len(self.theme.hover) == 3 else self.theme.hover, min_rect, border_radius=4)
        pygame.draw.line(self.screen, self.theme.text_dim, (min_rect.centerx - 4, min_rect.centery), (min_rect.centerx + 4, min_rect.centery), 2)
        # maximize
        max_rect = pygame.Rect(right - 3 * b - 8, cy - b // 2, b, b)
        if max_rect.collidepoint(mouse):
            pygame.draw.rect(self.screen, self.theme.hover[:3] if len(self.theme.hover) == 3 else self.theme.hover, max_rect, border_radius=4)
        if win.state == WINDOW_STATE_MAXIMIZED:
            pygame.draw.rect(self.screen, self.theme.text_dim, (max_rect.centerx - 4, max_rect.centery - 4, 8, 8), 1)
        else:
            pygame.draw.rect(self.screen, self.theme.text_dim, (max_rect.centerx - 4, max_rect.centery - 4, 8, 8), 1)
        # close
        close_rect = pygame.Rect(right - b, cy - b // 2, b, b)
        if close_rect.collidepoint(mouse):
            pygame.draw.rect(self.screen, self.theme.danger[:3], close_rect, border_radius=4)
        pygame.draw.line(self.screen, self.theme.text if close_rect.collidepoint(mouse) else self.theme.text_dim,
                         (close_rect.centerx - 4, close_rect.centery - 4),
                         (close_rect.centerx + 4, close_rect.centery + 4), 2)
        pygame.draw.line(self.screen, self.theme.text if close_rect.collidepoint(mouse) else self.theme.text_dim,
                         (close_rect.centerx - 4, close_rect.centery + 4),
                         (close_rect.centerx + 4, close_rect.centery - 4), 2)

    def _draw_taskbar(self):
        h = 46
        tb = pygame.Rect(0, self.screen_h - h, self.screen_w, h)
        # translucent bar (drawn onto a reusable surface)
        s = self._taskbar_surf
        s.fill((0, 0, 0, 0))
        base = self.theme.taskbar
        pygame.draw.rect(s, base[:4] if len(base) == 4 else base + (235,), s.get_rect())
        self.screen.blit(s, tb.topleft)
        pygame.draw.line(self.screen, (255, 255, 255, 30), (0, tb.top), (self.screen_w, tb.top))

        # start button
        start_r = pygame.Rect(10, tb.y + 6, 34, 34)
        self._draw_start_button(start_r)
        # power menu toggle
        power_r = pygame.Rect(48, tb.y + 6, 24, 24)
        pygame.draw.circle(self.screen, self.theme.text_dim, power_r.center, 9, 2)
        # running apps
        x = 82
        for inst in self.instances:
            if inst.closed:
                continue
            app = inst.window.app
            item = pygame.Rect(x, tb.y + 6, 44, 34)
            focused = inst.window is self.wm.focused
            if item.collidepoint(pygame.mouse.get_pos()):
                pygame.draw.rect(self.screen, self.theme.hover[:3] if len(self.theme.hover) == 3 else self.theme.hover, item, border_radius=6)
            elif focused:
                pygame.draw.rect(self.screen, self.theme.taskbar_active[:3] + (40,), item, border_radius=6)
            pygame.draw.rect(self.screen, self.theme.taskbar_active[:3] if focused else (100, 100, 120), (item.x + 14, item.bottom - 3, 16, 3), border_radius=2)
            font = self.get_font(self.config.font_size)
            img = font.render(app.icon, True, self.theme.text)
            self.screen.blit(img, img.get_rect(center=item.center))
            # tooltip (reuse cached background surface)
            if item.collidepoint(pygame.mouse.get_pos()):
                tip = font.render(app.name, True, self.theme.text)
                bg = self._tooltip_surf
                if bg is None or bg.get_width() < tip.get_width() + 16 or bg.get_height() < tip.get_height() + 8:
                    bg = pygame.Surface((tip.get_width() + 16, tip.get_height() + 8), pygame.SRCALPHA)
                    self._tooltip_surf = bg
                bg.fill((0, 0, 0, 0))
                pygame.draw.rect(bg, (40, 40, 50, 220), bg.get_rect(), border_radius=6)
                bg.blit(tip, (8, 4))
                self.screen.blit(bg, (item.x, tb.y - tip.get_height() - 16))
            x += 52
            if x > self.screen_w - 260:
                break

        # clock (shifted left to make room for the system tray)
        clock_font = self.get_font(18)
        now = time.localtime()
        if self.config.clock_24h:
            timestr = time.strftime("%H:%M", now)
        else:
            timestr = time.strftime("%I:%M %p", now).lstrip("0")
        date = time.strftime("%a %b %d", now)
        tc = self.theme.text
        t1 = clock_font.render(timestr, True, tc)
        t2 = clock_font.render(date, True, self.theme.text_dim)
        tx = self.screen_w - 160 - t1.get_width()
        self.screen.blit(t1, (tx, tb.y + 5))
        self.screen.blit(t2, (tx, tb.y + 24))
        # statusline widgets toggled via config.statusline
        wx = tx - 12
        for widget in reversed(self.statusline_widgets()):
            if widget == "theme":
                tf = self.get_font(14)
                tlbl = tf.render(self.theme.name, True, self.theme.accent)
                wx -= tlbl.get_width() + 12
                self.screen.blit(tlbl, (wx, tb.y + 15))
            elif widget == "cpu":
                try:
                    import psutil as _ps
                    cpu = _ps.cpu_percent(interval=None)
                except Exception:
                    cpu = 0.0
                cf = self.get_font(14)
                clbl = cf.render(f"CPU {cpu:.0f}%", True, self.theme.text_dim)
                wx -= clbl.get_width() + 12
                self.screen.blit(clbl, (wx, tb.y + 15))
        # system tray
        self._draw_tray(tb)

    def _draw_tray(self, tb):
        # network online/offline dot
        net = self.drivers.get("network") if hasattr(self, "drivers") else None
        online = bool(net and net.online())
        pygame.draw.circle(self.screen,
                           self.theme.success if online else self.theme.danger,
                           (tb.right - 20, tb.y + 18), 5)
        # sound toggle indicator
        if self.sound and self.sound.enabled:
            snd = pygame.Rect(tb.right - 52, tb.y + 8, 22, 20)
            pygame.draw.arc(self.screen, self.theme.text, snd, -0.7, 0.7, 2)
            pygame.draw.line(self.screen, self.theme.text,
                             (snd.x + 2, snd.centery), (snd.x + 8, snd.centery), 2)
        # notifications icon + unread dot
        if self._notifications:
            ntf = pygame.Rect(tb.right - 82, tb.y + 10, 22, 22)
            pygame.draw.circle(self.screen, self.theme.accent, (ntf.right, ntf.y), 4)
        # show-desktop
        show = pygame.Rect(tb.right - 110, tb.y + 10, 22, 22)
        pygame.draw.rect(self.screen, self.theme.text_dim,
                         pygame.Rect(show.x + 4, show.y + 4, 14, 14), 1, border_radius=3)

    def _draw_start_button(self, r):
        if r.collidepoint(pygame.mouse.get_pos()):
            pygame.draw.rect(self.screen, self.theme.hover[:3] if len(self.theme.hover) == 3 else self.theme.hover, r, border_radius=8)
        if self.launcher_open:
            pygame.draw.rect(self.screen, self.theme.active[:3] if len(self.theme.active) == 3 else self.theme.active, r, border_radius=8)
        pygame.draw.circle(self.screen, self.theme.accent, r.center, 13)
        pygame.draw.circle(self.screen, (255, 255, 255), (r.centerx - 3, r.centery - 3), 4)

    def _draw_launcher(self):
        if not self.launcher_open:
            return
        # dim background (reused surface)
        dim = self._dim_surf
        dim.fill((10, 10, 18, 180))
        self.screen.blit(dim, (0, 0))
        # title
        font = self.get_font(30)
        title = font.render("Lion-OS Launcher", True, self.theme.text)
        self.screen.blit(title, title.get_rect(midtop=(self.screen_w // 2, 50)))
        # search box
        font = self.get_font(self.config.font_size)
        search_r = pygame.Rect(self.screen_w // 2 - 200, 95, 400, 36)
        pygame.draw.rect(self.screen, self.theme.surface, search_r, border_radius=10)
        pygame.draw.rect(self.screen, self.theme.accent, search_r, 1, border_radius=10)
        txt = self.launcher_search or "Search apps..."
        col = self.theme.text if self.launcher_search else self.theme.text_dim
        img = font.render(txt, True, col)
        self.screen.blit(img, (search_r.x + 12, search_r.centery - img.get_height() // 2))
        # category tabs
        self._draw_launcher_tabs()
        # recent apps row
        self._draw_launcher_recent()
        # results grid
        results = self._launcher_results()
        if results:
            cols = 8
            size = 96
            start_x = (self.screen_w - cols * size) // 2
            sel = getattr(self, "_launcher_idx", 0) % len(results)
            for i, app in enumerate(results):
                cx = start_x + (i % cols) * size
                cy = 210 + (i // cols) * size
                tile = pygame.Rect(cx, cy, size, size)
                ic = pygame.Rect(cx + 18, cy + 12, 60, 60)
                hovered = tile.collidepoint(pygame.mouse.get_pos())
                draw_app_tile(self.screen, ic, app.icon, self.theme,
                              hovered=hovered, selected=(i == sel),
                              icon_cache=self.icon_cache,
                              scene=APP_ICONS.get(app.name), scene_id=app.name)
                lfont = self.get_font(15)
                limg = lfont.render(app.name, True, self.theme.text)
                self.screen.blit(limg, limg.get_rect(midtop=(tile.centerx, ic.bottom + 8)))
        else:
            img = font.render("No apps match your search.", True, self.theme.text_dim)
            self.screen.blit(img, img.get_rect(center=(self.screen_w // 2, self.screen_h // 2)))

    def _draw_launcher_tabs(self):
        cats = self._launcher_categories()
        fx = self.get_font(16)
        tx = self.screen_w // 2 - 200
        for c in cats:
            w = fx.size(c)[0] + 24
            r = pygame.Rect(tx, 148, w, 30)
            active = c == self.launcher_category
            if active:
                pygame.draw.rect(self.screen, self.theme.active[:3] if len(self.theme.active) == 3 else self.theme.active,
                                 r, border_radius=8)
            img = fx.render(c, True, self.theme.accent if active else self.theme.text_dim)
            self.screen.blit(img, img.get_rect(center=r.center))
            tx += w + 6

    def _draw_launcher_recent(self):
        mru = [n for n in self.config.mru_apps if n in self.apps_registry.all()]
        if not mru:
            mru = [n for n in _activity.app_counts() if n in self.apps_registry.all()][:6]
        if not mru:
            return
        font = self.get_font(16)
        label = font.render("Recent", True, self.theme.text_dim)
        self.screen.blit(label, (self.screen_w // 2 - 200, 190))
        x = self.screen_w // 2 - 200
        for name in mru[:6]:
            cls = self.apps_registry.get(name)
            tile = pygame.Rect(x, 212, 40, 40)
            draw_app_tile(self.screen, tile, cls.icon, self.theme,
                          hovered=tile.collidepoint(pygame.mouse.get_pos()),
                          icon_cache=self.icon_cache,
                          scene=APP_ICONS.get(name), scene_id=name)
            x += 46

    def _draw_power_menu(self):
        if not self.power_menu_open:
            return
        dim = self._dim_surf
        dim.fill((10, 10, 18, 180))
        self.screen.blit(dim, (0, 0))
        panel = self._power_menu_panel()
        draw_glass_panel(self.screen, panel, self.theme, radius=16)
        font = self.get_font(28)
        title = font.render("Power", True, self.theme.text)
        self.screen.blit(title, title.get_rect(midtop=(panel.centerx, panel.y + 16)))
        for i, (key, label, icon) in enumerate(self._power_menu_actions()):
            r = pygame.Rect(panel.x + 20, panel.y + 60 + i * 56, panel.width - 40, 44)
            hovered = r.collidepoint(pygame.mouse.get_pos())
            if hovered:
                pygame.draw.rect(self.screen, self.theme.hover[:3] if len(self.theme.hover) == 3 else self.theme.hover,
                                 r, border_radius=10)
            ifont = self.get_font(22)
            iimg = ifont.render(icon, True, self.theme.text)
            self.screen.blit(iimg, iimg.get_rect(midleft=(r.x + 14, r.centery)))
            limg = font.render(label, True, self.theme.text)
            self.screen.blit(limg, limg.get_rect(midleft=(r.x + 52, r.centery)))

    def _draw_alt_tab(self):
        if not self.wm.alt_tab_active:
            return
        order = self.wm._alt_tab_order
        if not order:
            return
        dim = self._dim_surf
        dim.fill((10, 10, 18, 120))
        self.screen.blit(dim, (0, 0))
        n = len(order)
        card_w, card_h = 140, 96
        total = n * (card_w + 12) - 12
        start_x = (self.screen_w - total) // 2
        for i, win in enumerate(order):
            x = start_x + i * (card_w + 12)
            y = self.screen_h // 2 - card_h // 2
            r = pygame.Rect(x, y, card_w, card_h)
            active = i == self.wm._alt_tab_idx
            draw_glass_panel(self.screen, r, self.theme,
                             radius=12, border=active)
            if active:
                pygame.draw.rect(self.screen, self.theme.accent, r, 2, border_radius=12)
            font = self.get_font(18)
            img = font.render(win.app.icon if win.app else "◈", True, self.theme.accent)
            self.screen.blit(img, img.get_rect(center=(r.centerx, r.y + 30)))
            tfont = self.get_font(15)
            t = win.title or (win.app.name if win.app else "")
            if tfont.size(t)[0] > card_w - 12:
                t = t[:12] + "…"
            timg = tfont.render(t, True, self.theme.text)
            self.screen.blit(timg, timg.get_rect(midtop=(r.centerx, r.y + 58)))

    def _draw_context_menu(self):
        if self.context_menu:
            menu = self.context_menu[2]
            menu.draw(self.screen, self.theme)

    def _draw_toasts(self):
        y = self.screen_h - 60
        for t in self.toasts:
            t.draw(self.screen, self.theme, (self.screen_w - 340, y))
            y -= 76

    def _draw_boot(self):
        # black boot screen with progress + shimmer
        self.screen.fill((8, 8, 12))
        font = self.get_font(40)
        logo = font.render("🦁 Lion-OS", True, self.theme.accent)
        self.screen.blit(logo, logo.get_rect(midtop=(self.screen_w // 2, self.screen_h // 2 - 110)))
        # progress bar
        bar_r = pygame.Rect(self.screen_w // 2 - 150, self.screen_h // 2 + 10, 300, 8)
        pygame.draw.rect(self.screen, (60, 60, 70), bar_r, border_radius=4)
        fill_w = int(bar_r.width * min(1, self._boot_progress / 100))
        if fill_w > 0:
            pygame.draw.rect(self.screen, self.theme.accent, (bar_r.x, bar_r.y, fill_w, bar_r.height), border_radius=4)
            # shimmer sweep
            shx = bar_r.x + int((self._boot_glow % 1.0) * bar_r.width)
            pygame.draw.rect(self.screen, (255, 255, 255), (shx, bar_r.y, 40, bar_r.height), border_radius=4)
        # boot lines
        lfont = self.get_font(16)
        for i, (line, important) in enumerate(BOOT_LINES[:self._boot_lines_done + 1]):
            col = self.theme.accent if important else (150, 150, 165)
            img = lfont.render(line, True, col)
            self.screen.blit(img, (self.screen_w // 2 - 150, self.screen_h // 2 + 30 + i * 22))

    def _draw_wizard(self):
        dim = self._dim_surf
        dim.fill((8, 8, 14, 210))
        self.screen.blit(dim, (0, 0))
        cx = self.screen_w // 2
        font = self.get_font(30)
        title = font.render("Welcome to Lion-OS", True, self.theme.text)
        self.screen.blit(title, title.get_rect(center=(cx, self.screen_h // 2 - 150)))
        # progress dots
        for i, _s in enumerate(WIZARD_STEPS):
            color = self.theme.accent if i == self._wizard_step else self.theme.text_dim
            pygame.draw.circle(self.screen, color, (cx - 60 + i * 40, self.screen_h // 2 - 110), 8)
        # step prompt
        prompts = {
            "name": "What should we call you?",
            "theme": "Pick a theme — press ←/→ to cycle, Enter to keep",
            "pin": "We'll pin your essentials",
            "matters": "You're all set!",
        }
        pfont = self.get_font(22)
        step_name = WIZARD_STEPS[self._wizard_step]
        pimg = pfont.render(prompts[step_name], True, self.theme.text)
        self.screen.blit(pimg, pimg.get_rect(center=(cx, self.screen_h // 2 - 50)))
        if step_name == "name":
            box = pygame.Rect(cx - 160, self.screen_h // 2 + 0, 320, 44)
            pygame.draw.rect(self.screen, (255, 255, 255, 40), box, border_radius=10)
            pygame.draw.rect(self.screen, self.theme.accent, box, 1, border_radius=10)
            val = self._wizard_input or "your name"
            vimg = pfont.render(val, True,
                                self.theme.text if self._wizard_input else self.theme.text_dim)
            self.screen.blit(vimg, vimg.get_rect(center=box.center))
        elif step_name == "theme":
            timg = pfont.render(f"  {self.config.theme.title()}  ", True, self.theme.accent)
            self.screen.blit(timg, timg.get_rect(center=(cx, self.screen_h // 2 + 20)))
        elif step_name == "pin":
            pinn = pfont.render("Terminal · File Manager · Notes", True, self.theme.text_dim)
            self.screen.blit(pinn, pinn.get_rect(center=(cx, self.screen_h // 2 + 20)))
        hint = self.get_font(15).render("Enter to continue", True, self.theme.text_dim)
        self.screen.blit(hint, hint.get_rect(center=(cx, self.screen_h // 2 + 90)))

    def _draw_login(self):
        if getattr(self, "wizard_active", False):
            self._draw_wizard()
            return
        dim = self._dim_surf
        dim.fill((8, 8, 14, 200))
        self.screen.blit(dim, (0, 0))
        cx = self.screen_w // 2
        shake = int(self._login_shake * 12)
        # clock
        tfont = self.get_font(60)
        now = time.localtime()
        timestr = time.strftime("%H:%M", now) if self.config.clock_24h else time.strftime("%I:%M %p", now).lstrip("0")
        cimg = tfont.render(timestr, True, (255, 255, 255))
        self.screen.blit(cimg, cimg.get_rect(center=(cx, self.screen_h // 2 - 120)))
        dfont = self.get_font(22)
        dimg = dfont.render(time.strftime("%A, %B %d, %Y", now), True, (220, 220, 230))
        self.screen.blit(dimg, dimg.get_rect(center=(cx, self.screen_h // 2 - 70)))
        # user icon with accent ring
        pygame.draw.circle(self.screen, self.theme.accent, (cx, self.screen_h // 2 - 10), 40)
        pygame.draw.circle(self.screen, self.theme.surface, (cx, self.screen_h // 2 - 10), 34)
        pygame.draw.circle(self.screen, self.theme.text, (cx, self.screen_h // 2 - 10), 14)
        ufont = self.get_font(24)
        uimg = ufont.render(self.config.username, True, (255, 255, 255))
        self.screen.blit(uimg, uimg.get_rect(center=(cx, self.screen_h // 2 + 44)))
        # password box (shakes on error)
        pw_r = pygame.Rect(cx - 140 + shake, self.screen_h // 2 + 70, 280, 40)
        pygame.draw.rect(self.screen, (255, 255, 255, 40), pw_r, border_radius=10)
        pygame.draw.rect(self.screen, self.theme.accent if self._login_attempt % 2 == 0 else (255, 255, 255, 80), pw_r, 1, border_radius=10)
        pfont = self.get_font(22)
        pw_txt = "*" * len(self._login_pw) if self._login_pw else "Password"
        pimg = pfont.render(pw_txt, True, (230, 230, 240) if self._login_pw else (170, 170, 185))
        self.screen.blit(pimg, pimg.get_rect(center=pw_r.center))
        if self._login_error:
            eimg = pfont.render(self._login_error, True, (255, 140, 140))
            self.screen.blit(eimg, eimg.get_rect(center=(cx, pw_r.bottom + 22)))
        hint = self.get_font(15).render("Press Enter to log in", True, (170, 170, 185))
        self.screen.blit(hint, hint.get_rect(center=(cx, pw_r.bottom + 48)))


def boot(config: LionConfig = None):
    """Entry point used by the CLI."""
    os_ = LionOS(config)
    return os_.run()
