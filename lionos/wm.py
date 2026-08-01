"""Window manager for Lion-OS — windows, dragging, resizing, snapping, focus."""

from __future__ import annotations

import random
import time
from typing import List, Optional, TYPE_CHECKING

import pygame

from .theme import Theme

if TYPE_CHECKING:
    from .apps.base import App

WINDOW_STATE_NORMAL = "normal"
WINDOW_STATE_MAXIMIZED = "maximized"
WINDOW_STATE_MINIMIZED = "minimized"

TITLEBAR_H = 38
RESIZE_EDGE = 6


class Window:
    """A single application window."""

    def __init__(self, app: "App", x=80, y=60, w=720, h=480, title="Window",
                 theme: Theme = None, resizable=True, min_w=320, min_h=220):
        self.app = app
        self.title = title
        self.rect = pygame.Rect(x, y, w, h)
        self.restore_rect = pygame.Rect(x, y, w, h)   # used when maximizing
        self.state = WINDOW_STATE_NORMAL
        self.resizable = resizable
        self.min_w = min_w
        self.min_h = min_h
        self.theme = theme
        self.closable = True
        self.maximizable = True
        self.minimizable = True
        self.snapped = False          # "left" | "right" | None
        self.visible = True
        self.anim_scale = 1.0
        self._anim_target = 1.0
        self._drag_mode = None        # None | "move" | edge name
        self._drag_offset = (0, 0)
        self._focus_grab_time = 0.0
        self.background = None        # optional cached background
        self._dirty = True
        self.on_close = None

    # -- properties ---------------------------------------------------------
    @property
    def titlebar_rect(self):
        return pygame.Rect(self.rect.x, self.rect.y, self.rect.width, TITLEBAR_H)

    @property
    def content_rect(self):
        if self.state == WINDOW_STATE_MINIMIZED:
            return pygame.Rect(0, 0, 0, 0)
        return pygame.Rect(self.rect.x, self.rect.y + TITLEBAR_H,
                           self.rect.width, self.rect.height - TITLEBAR_H)

    # -- state ---------------------------------------------------------------
    def maximize(self, screen_rect: pygame.Rect):
        if not self.maximizable:
            return
        self.restore_rect = pygame.Rect(self.rect)
        self.rect = pygame.Rect(screen_rect)
        self.state = WINDOW_STATE_MAXIMIZED
        self.snapped = None
        self._dirty = True

    def restore(self):
        if self.state == WINDOW_STATE_MAXIMIZED:
            self.rect = pygame.Rect(self.restore_rect)
            self.state = WINDOW_STATE_NORMAL
        elif self.state == WINDOW_STATE_MINIMIZED:
            self.state = WINDOW_STATE_NORMAL
        self.snapped = None
        self._dirty = True

    def toggle_maximize(self, screen_rect):
        if self.state == WINDOW_STATE_MAXIMIZED:
            self.restore()
        else:
            self.maximize(screen_rect)

    def minimize(self):
        if not self.minimizable:
            return
        self.state = WINDOW_STATE_MINIMIZED
        self._dirty = True

    def snap(self, side, screen_rect: pygame.Rect):
        """Snap window to left/right half or to a corner."""
        if self.state == WINDOW_STATE_MAXIMIZED:
            self.restore()
        w = screen_rect.width // 2
        h = screen_rect.height - 0  # keep full height
        if side == "left":
            self.rect = pygame.Rect(screen_rect.x, screen_rect.y, w, screen_rect.height)
        elif side == "right":
            self.rect = pygame.Rect(screen_rect.x + w, screen_rect.y, w, screen_rect.height)
        elif side == "tl":
            self.rect = pygame.Rect(screen_rect.x, screen_rect.y, w, h)
        elif side == "tr":
            self.rect = pygame.Rect(screen_rect.x + w, screen_rect.y, w, h)
        elif side == "bl":
            self.rect = pygame.Rect(screen_rect.x, screen_rect.y + 0, w, h)
        elif side == "br":
            self.rect = pygame.Rect(screen_rect.x + w, screen_rect.y + 0, w, h)
        self.snapped = side
        self.state = WINDOW_STATE_NORMAL
        self._dirty = True

    # -- hit testing ----------------------------------------------------------
    def hit_test(self, pos) -> Optional[str]:
        """Return interaction mode for a point: 'title', 'edge', or 'client'."""
        if self.state != WINDOW_STATE_NORMAL:
            return "title" if self.titlebar_rect.collidepoint(pos) else "client"
        if not self.rect.collidepoint(pos):
            return None
        x, y = pos
        r = self.rect
        if not self.resizable:
            if self.titlebar_rect.collidepoint(pos):
                return "title"
            return "client"
        # edges
        if y <= r.top + RESIZE_EDGE:
            if x <= r.left + RESIZE_EDGE:
                return "tl"
            if x >= r.right - RESIZE_EDGE:
                return "tr"
            return "top"
        if y >= r.bottom - RESIZE_EDGE:
            if x <= r.left + RESIZE_EDGE:
                return "bl"
            if x >= r.right - RESIZE_EDGE:
                return "br"
            return "bottom"
        if x <= r.left + RESIZE_EDGE:
            return "left"
        if x >= r.right - RESIZE_EDGE:
            return "right"
        if self.titlebar_rect.collidepoint(pos):
            return "title"
        return "client"

    def resize_with(self, mode, dx, dy, screen_rect: pygame.Rect):
        r = self.rect
        if "l" in mode:
            new_l = min(r.right - self.min_w, r.left + dx)
            new_l = max(screen_rect.left, new_l)
            r.width = r.right - new_l
            r.x = new_l
        if "r" in mode:
            r.width = max(self.min_w, min(screen_rect.right, r.width + dx) - r.x)
        if "t" in mode:
            new_t = min(r.bottom - self.min_h, r.top + dy)
            new_t = max(screen_rect.top, new_t)
            r.height = r.bottom - new_t
            r.y = new_t
        if "b" in mode:
            r.height = max(self.min_h, min(screen_rect.bottom, r.height + dy) - r.y)
        self.rect = r
        self._dirty = True


class WindowManager:
    """Owns all windows: z-order, focus, drag/resize state, snapping."""

    SNAP_EDGE = 12          # px from screen edge to trigger snap
    SNAP_MARGIN = 60        # px near edge to show snap preview

    def __init__(self, screen_rect: pygame.Rect, theme: Theme):
        self.screen_rect = screen_rect
        self.theme = theme
        self.windows: List[Window] = []       # z-order: back to front
        self.focused: Optional[Window] = None
        self._drag_win: Optional[Window] = None
        self._drag_mode: Optional[str] = None
        self._drag_offset = (0, 0)
        self._snap_preview = None             # dict with rect + label
        self._down_pos = None
        self._down_win = None
        self._maximize_drag = False

    def set_screen(self, rect):
        self.screen_rect = rect
        for w in self.windows:
            w.rect = w.rect.clamp(rect)

    def create_window(self, app, x=None, y=None, w=None, h=None, title=None):
        if x is None:
            x = 80 + random.randint(0, 120)
        if y is None:
            y = 60 + random.randint(0, 80)
        if w is None:
            w = app.default_w
        if h is None:
            h = app.default_h
        win = Window(app, x=x, y=y, w=w, h=h,
                     title=title or app.name,
                     theme=self.theme,
                     resizable=app.resizable,
                     min_w=app.min_w, min_h=app.min_h)
        self.add_window(win)
        return win

    def add_window(self, win: Window):
        self.windows.append(win)
        self.focus(win)
        return win

    def remove_window(self, win: Window):
        if win in self.windows:
            self.windows.remove(win)
        if self.focused is win:
            self.focused = self.windows[-1] if self.windows else None
        if self._drag_win is win:
            self._drag_win = None

    def focus(self, win: Window):
        if win in self.windows:
            self.windows.remove(win)
            self.windows.append(win)
        self.focused = win
        win._focus_grab_time = time.time()
        if win.state == WINDOW_STATE_MINIMIZED:
            win.state = WINDOW_STATE_NORMAL

    def top_at(self, pos) -> Optional[Window]:
        for w in reversed(self.windows):
            if w.visible and w.state != WINDOW_STATE_MINIMIZED and w.rect.collidepoint(pos):
                return w
        return None

    def __iter__(self):
        return iter(self.windows)

    def handle_event(self, event) -> bool:
        """Handle window-manager-level events. Returns True if consumed."""
        # --- mouse down ------------------------------------------------------
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            win = self.top_at(pos)
            if win:
                self.focus(win)
                # window chrome buttons take priority
                btn = self._hit_chrome(win, pos)
                if btn:
                    return True
                mode = win.hit_test(pos)
                if mode in ("title", "client") and win.titlebar_rect.collidepoint(pos):
                    self._drag_win = win
                    self._drag_mode = "move"
                    self._drag_offset = (pos[0] - win.rect.x, pos[1] - win.rect.y)
                    self._down_pos = pos
                    self._down_win = win
                    return True
                if mode in ("top", "bottom", "left", "right", "tl", "tr", "bl", "br"):
                    self._drag_win = win
                    self._drag_mode = mode
                    self._down_pos = pos
                    self._down_win = win
                    return True
                # client-area click: focus handled above, but let the app see it
                self._down_pos = pos
                self._down_win = win
                return False
            return False  # click on desktop handled elsewhere

        # --- mouse motion ------------------------------------------------------
        if event.type == pygame.MOUSEMOTION:
            if self._drag_win and self._drag_mode == "move":
                pos = event.pos
                nw = pos[0] - self._drag_offset[0]
                nh = pos[1] - self._drag_offset[1]
                self._drag_win.rect.x = max(self.screen_rect.left - self._drag_win.rect.width + 40,
                                            min(nw, self.screen_rect.right - 40))
                self._drag_win.rect.y = max(self.screen_rect.top, min(nh, self.screen_rect.bottom - 30))
                self._drag_win._dirty = True
                self._update_snap_preview(self._drag_win, pos)
                return True
            if self._drag_win and self._drag_mode not in ("move", None):
                dx, dy = event.rel
                self._drag_win.resize_with(self._drag_mode, dx, dy, self.screen_rect)
                return True
            # cursor feedback
            if not self._drag_win:
                win = self.top_at(event.pos)
                return False
            return True

        # --- mouse up ----------------------------------------------------------
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._drag_win:
                w = self._drag_win
                if self._drag_mode == "move" and self._snap_preview:
                    # apply snap
                    side = self._snap_preview.get("side")
                    if side in ("left", "right"):
                        w.snap(side, self.screen_rect)
                    self._snap_preview = None
                self._drag_win = None
                self._drag_mode = None
                self._snap_preview = None
                return True
            return False

        return False

    def _hit_chrome(self, win: Window, pos) -> Optional[str]:
        """Handle clicks on the close/min/max buttons. Returns the button name."""
        if win.state == WINDOW_STATE_MAXIMIZED:
            return None
        tr = win.titlebar_rect
        b = 16
        right = tr.right - 8
        cy = tr.centery
        close_r = pygame.Rect(right - b, cy - b // 2, b, b)
        min_r = pygame.Rect(right - 2 * b - 8, cy - b // 2, b, b)
        max_r = pygame.Rect(right - 3 * b - 8, cy - b // 2, b, b)
        if close_r.collidepoint(pos):
            if win.closable:
                if win.app:
                    win.app.close()
                else:
                    self.remove_window(win)
            return "close"
        if max_r.collidepoint(pos):
            if win.maximizable:
                win.toggle_maximize(self.screen_rect)
            return "max"
        if min_r.collidepoint(pos):
            if win.minimizable:
                win.minimize()
            return "min"
        return None

    def _update_snap_preview(self, win, pos):
        if win.state == WINDOW_STATE_MAXIMIZED:
            self._snap_preview = None
            return
        x = pos[0]
        sr = self.screen_rect
        self._snap_preview = None
        if x <= sr.left + self.SNAP_MARGIN:
            self._snap_preview = {"side": "left",
                                  "rect": pygame.Rect(sr.left, sr.top, sr.width // 2, sr.height),
                                  "label": "Left"}
        elif x >= sr.right - self.SNAP_MARGIN:
            self._snap_preview = {"side": "right",
                                  "rect": pygame.Rect(sr.left + sr.width // 2, sr.top, sr.width // 2, sr.height),
                                  "label": "Right"}
        elif win.rect.y <= sr.top + self.SNAP_MARGIN and pos[1] <= sr.top + self.SNAP_MARGIN:
            self._snap_preview = {"side": "max", "rect": pygame.Rect(sr),
                                  "label": "Maximize"}

    def draw_snap_preview(self, surface, theme):
        sp = self._snap_preview
        if not sp:
            return
        r = sp["rect"]
        s = pygame.Surface((r.width, r.height), pygame.SRCALPHA)
        accent = theme.accent
        pygame.draw.rect(s, accent + (70,), s.get_rect(), border_radius=10)
        pygame.draw.rect(s, accent + (200,), s.get_rect(), 2, border_radius=10)
        surface.blit(s, r.topleft)
