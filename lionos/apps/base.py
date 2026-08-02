"""App base class + registry for Lion-OS."""

from __future__ import annotations

import time
from typing import Dict, List, Optional, TYPE_CHECKING

import pygame

from ..theme import Theme
from ..wm import Window, WINDOW_STATE_MINIMIZED

if TYPE_CHECKING:
    from ..kernel import LionOS


class App:
    """Base class for all Lion-OS applications.

    Subclasses implement handle_event / update / draw against the window's
    content rect. ``name`` and ``icon`` drive the launcher and taskbar.
    """

    name = "App"
    icon = "◈"                     # glyph used on desktop / launcher
    description = ""
    category = "Utilities"
    default_w = 720
    default_h = 480
    resizable = True
    min_w = 320
    min_h = 220
    singleton = False              # True = only one instance at a time
    supports_focus = True

    def __init__(self, os: "LionOS", window: Window = None):
        self.os = os
        self.theme: Theme = os.theme
        self.window = window or os.wm.create_window(self)
        self.rect = self.window.content_rect
        self._last = pygame.Rect(self.rect)
        self.closed = False
        self.hydrated = False        # two-phase startup: content ready after ~3 frames
        self._hydrate_timer = 0.0

    # -- lifecycle ---------------------------------------------------------
    def on_open(self):
        """Called once when the app starts."""
        pass

    def on_activate(self):
        """Called when window gains focus."""
        pass

    def on_deactivate(self):
        """Called when window loses focus."""
        pass

    def on_resize(self, rect: pygame.Rect):
        """Called when the content rect changes size."""
        pass

    def on_close(self):
        """Called when the user closes the window."""
        pass

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.on_close()
        finally:
            self.os.wm.remove_window(self.window)

    # -- event loop ----------------------------------------------------------
    def handle_event(self, event, local_pos):
        """Handle an event. local_pos is relative to content rect. Return True if consumed."""
        return False

    def handle_global_event(self, event):
        """Handle events even when window not focused (e.g. hotkeys)."""
        return False

    def update(self, dt: float):
        pass

    def draw(self, surface: pygame.Surface, rect: pygame.Rect):
        pass

    def step_hydration(self, dt: float):
        """Advance two-phase startup: content becomes available after a short
        structural pass (~3 frames), so window chrome appears instantly."""
        if not self.hydrated:
            self._hydrate_timer += dt
            if self._hydrate_timer >= 0.05:
                self.hydrated = True

    # -- helpers ---------------------------------------------------------------
    def set_title(self, title: str):
        self.window.title = title

    def show_toast(self, title, message, kind="info"):
        self.os.show_toast(title, message, kind)

    def open_app(self, name, **kwargs):
        return self.os.launch(name, **kwargs)

    def redraw(self):
        self.window._dirty = True

    def rel_pos(self, pos):
        """Convert a screen pos to content-local coordinates."""
        cr = self.window.content_rect
        return pos[0] - cr.x, pos[1] - cr.y


class AppRegistry:
    def __init__(self):
        self._apps: Dict[str, type] = {}

    def register(self, cls: type):
        self._apps[cls.name] = cls
        return cls

    def register_all(self, classes):
        for c in classes:
            self.register(c)

    def all(self) -> Dict[str, type]:
        return dict(self._apps)

    def get(self, name: str):
        return self._apps.get(name)

    def by_category(self) -> Dict[str, List[type]]:
        out: Dict[str, List[type]] = {}
        for cls in self._apps.values():
            out.setdefault(cls.category, []).append(cls)
        return out


registry = AppRegistry()
