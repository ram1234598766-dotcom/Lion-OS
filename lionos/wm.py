"""Window manager for Lion-OS — windows, dragging, resizing, snapping, focus.

The window chrome (shadow / body / titlebar) is rendered once into cached
surfaces and only re-rendered when the appearance actually changes
(resize, focus, state, theme, title). Per-frame draw then just blits.
Windows also carry lightweight animations (open / close / minimize)
driven by ``step_anim``.
"""

from __future__ import annotations

import random
import time
from typing import List, Optional, TYPE_CHECKING

import pygame

from .theme import Theme, blend
from .anim import ease_in_out

if TYPE_CHECKING:
    from .apps.base import App

WINDOW_STATE_NORMAL = "normal"
WINDOW_STATE_MAXIMIZED = "maximized"
WINDOW_STATE_MINIMIZED = "minimized"

TITLEBAR_H = 38
RESIZE_EDGE = 6

_ANIM_OPEN = "open"
_ANIM_CLOSE = "close"
_ANIM_MINIMIZE = "minimize"
_ANIM_MAXIMIZE = "maximize"


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
        self.snapped = False          # "left" | "right" | "tl" ... | None
        self.visible = True
        self.workspace = 0            # virtual-desktop index
        self.anim_scale = 1.0
        self.anim_alpha = 255
        self.anim_slide = 0.0
        self._rect_from = None
        self._rect_to = None
        self._rect_t = 0.0
        self._rect_dur = 0.16
        self._rect_active = False
        self._anim_target = 1.0
        self._anim_kind = None        # None | "open" | "close" | "minimize" | "maximize"
        self._anim_t = 0.0
        self._anim_dur = 0.12
        self._drag_mode = None        # None | "move" | edge name
        self._drag_offset = (0, 0)
        self._focus_grab_time = 0.0
        self.background = None        # optional cached background
        self._dirty = True
        self.on_close = None

        # cached chrome surfaces
        self._chrome = {}             # kind -> Surface
        self._chrome_key = None

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

    # -- animations ----------------------------------------------------------
    def begin_anim(self, kind: str):
        self._anim_kind = kind
        self._anim_t = 0.0
        self._dirty = True

    def anim_active(self) -> bool:
        return self._anim_kind is not None

    def morph_rect(self, to_rect, dur: float = 0.16):
        """Glide the window rect to ``to_rect`` instead of snapping."""
        self._rect_from = pygame.Rect(self.rect)
        self._rect_to = pygame.Rect(to_rect)
        self._rect_t = 0.0
        self._rect_dur = dur
        self._rect_active = True
        self._dirty = True

    def step_anim(self, dt: float) -> bool:
        """Advance an active animation. Returns True while still animating."""
        if self._anim_kind is None and not self._rect_active:
            return False
        self._anim_t += dt
        t = min(1.0, self._anim_t / self._anim_dur)
        ease = 1.0 - (1.0 - t) ** 3          # ease-out cubic
        kind = self._anim_kind
        if kind == _ANIM_OPEN:
            self.anim_scale = 0.86 + 0.14 * ease
            self.anim_alpha = int(60 + 195 * ease)
            self.anim_slide = (1.0 - ease) * 24
        elif kind == _ANIM_CLOSE:
            self.anim_scale = 1.0 - 0.16 * ease
            self.anim_alpha = int(255 * (1.0 - ease))
        elif kind == _ANIM_MINIMIZE:
            self.anim_scale = 1.0 - 0.35 * ease
            self.anim_alpha = int(255 * (1.0 - 0.6 * ease))
            self.anim_slide = (1.0 - ease) * -36   # slide down toward the taskbar
        elif kind == _ANIM_MAXIMIZE:
            self.anim_scale = 0.92 + 0.08 * ease
            self.anim_alpha = 255
        # rect morph (maximize / snap / restore glide instead of jump)
        if self._rect_active and self._rect_from is not None and self._rect_to is not None:
            self._rect_t += dt
            rt = min(1.0, self._rect_t / self._rect_dur)
            e = ease_in_out(rt)
            f, to = self._rect_from, self._rect_to
            self.rect = pygame.Rect(
                int(f.x + (to.x - f.x) * e),
                int(f.y + (to.y - f.y) * e),
                int(f.width + (to.width - f.width) * e),
                int(f.height + (to.height - f.height) * e))
            self._dirty = True
            if rt >= 1.0:
                self.rect = pygame.Rect(to)
                self._rect_active = False
        self._dirty = True
        if t >= 1.0:
            self._finish_anim(kind)
            return False
        return True

    def _finish_anim(self, kind: str):
        self._anim_kind = None
        self.anim_scale = 1.0
        self.anim_alpha = 255
        if kind == _ANIM_CLOSE and self.app:
            self.app.close()
        elif kind == _ANIM_MINIMIZE:
            self.state = WINDOW_STATE_MINIMIZED
        self._dirty = True

    # -- chrome cache ----------------------------------------------------------
    def ensure_chrome(self, theme: Theme, focused: bool, font, font_size: int):
        """Render cached shadow/body/titlebar surfaces if the key changed."""
        key = (self.rect.size, focused, self.state, theme.name, self.title)
        if key == self._chrome_key and self._chrome:
            return
        w, h = self.rect.size
        self._chrome = {}

        # shadow (normal state only; maximized has none)
        if self.state != WINDOW_STATE_MAXIMIZED:
            pad = 12
            sh = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
            pygame.draw.rect(sh, theme.shadow[:3] + (150,),
                             (pad - 3, pad - 3, w + 6, h + 6), border_radius=14)
            pygame.draw.rect(sh, theme.shadow[:3] + (60,),
                             (pad, pad, w, h), border_radius=12)
            self._chrome["shadow"] = sh

        # body
        body = pygame.Surface((w, h), pygame.SRCALPHA)
        bg = theme.surface if len(theme.surface) == 3 else theme.surface
        bg_a = bg + (246,) if len(bg) == 3 else bg
        pygame.draw.rect(body, bg_a, body.get_rect(), border_radius=12)
        if focused:
            border = theme.accent + (70,) if len(theme.accent) == 3 else theme.accent
            pygame.draw.rect(body, border, body.get_rect(), 1, border_radius=12)
        else:
            pygame.draw.rect(body, (255, 255, 255, 30), body.get_rect(), 1, border_radius=12)
        self._chrome["body"] = body

        # titlebar (gradient + title text)
        tb = pygame.Surface((w, TITLEBAR_H), pygame.SRCALPHA)
        for yy in range(TITLEBAR_H):
            tt = yy / max(1, TITLEBAR_H - 1)
            col = blend(theme.titlebar_top, theme.titlebar_bottom, tt)
            pygame.draw.line(tb, col, (0, yy), (w, yy))
        if not focused:
            dim = pygame.Surface((w, TITLEBAR_H), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 28))
            tb.blit(dim, (0, 0))
        pygame.draw.line(tb, (255, 255, 255, 14), (0, TITLEBAR_H - 1), (w, TITLEBAR_H - 1))
        tcol = theme.text if focused else theme.text_dim
        img = font.render(self.title or (self.app.name if self.app else "Window"), True, tcol)
        tb.blit(img, (12, TITLEBAR_H // 2 - img.get_height() // 2))
        self._chrome["titlebar"] = tb

        self._chrome_key = key

    def invalidate_chrome(self):
        self._chrome = {}
        self._chrome_key = None
        self._dirty = True

    # -- state ---------------------------------------------------------------
    def maximize(self, screen_rect: pygame.Rect):
        if not self.maximizable:
            return
        self.restore_rect = pygame.Rect(self.rect)
        self.state = WINDOW_STATE_MAXIMIZED
        self.snapped = None
        self.morph_rect(screen_rect)
        self.begin_anim(_ANIM_MAXIMIZE)
        self.invalidate_chrome()

    def restore(self):
        if self.state == WINDOW_STATE_MAXIMIZED:
            self.morph_rect(self.restore_rect)
            self.state = WINDOW_STATE_NORMAL
        elif self.state == WINDOW_STATE_MINIMIZED:
            self.state = WINDOW_STATE_NORMAL
            self.begin_anim(_ANIM_OPEN)
        self.snapped = None
        self.invalidate_chrome()

    def toggle_maximize(self, screen_rect):
        if self.state == WINDOW_STATE_MAXIMIZED:
            self.restore()
        else:
            self.maximize(screen_rect)

    def minimize(self):
        if not self.minimizable:
            return
        if self._anim_kind == _ANIM_MINIMIZE:
            return
        self.begin_anim(_ANIM_MINIMIZE)
        self.invalidate_chrome()

    def snap(self, side, screen_rect: pygame.Rect):
        """Snap window to a half (left/right) or a corner (tl/tr/bl/br)."""
        if self.state == WINDOW_STATE_MAXIMIZED:
            self.restore()
        sr = screen_rect
        w2 = sr.width // 2
        h2 = sr.height // 2
        x = sr.x
        y = sr.y
        if side == "left":
            target = pygame.Rect(x, y, w2, sr.height)
        elif side == "right":
            target = pygame.Rect(x + w2, y, w2, sr.height)
        elif side == "tl":
            target = pygame.Rect(x, y, w2, h2)
        elif side == "tr":
            target = pygame.Rect(x + w2, y, w2, h2)
        elif side == "bl":
            target = pygame.Rect(x, y + h2, w2, h2)
        elif side == "br":
            target = pygame.Rect(x + w2, y + h2, w2, h2)
        else:
            target = pygame.Rect(self.rect)
        self.snapped = side
        self.state = WINDOW_STATE_NORMAL
        self.morph_rect(target)
        self.begin_anim(_ANIM_MAXIMIZE)
        self.invalidate_chrome()

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
        self.invalidate_chrome()


class WindowManager:
    """Owns all windows: z-order, focus, drag/resize state, snapping, alt-tab."""

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
        self._snap_preview_surf = None   # cached snap-preview surface
        self._snap_preview_size = None
        # alt-tab switcher
        self.alt_tab_active = False
        self._alt_tab_idx = 0
        self._alt_tab_order: List[Window] = []

    def windows_in(self, ws: int):
        """Windows belonging to a given workspace."""
        return [w for w in self.windows if w.workspace == ws]

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
        win.invalidate_chrome()
        if win.state == WINDOW_STATE_MINIMIZED:
            win.state = WINDOW_STATE_NORMAL
            win.begin_anim(_ANIM_OPEN)

    def top_at(self, pos) -> Optional[Window]:
        for w in reversed(self.windows):
            if w.visible and w.state != WINDOW_STATE_MINIMIZED and w.rect.collidepoint(pos):
                return w
        return None

    def visible_windows(self) -> List[Window]:
        return [w for w in self.windows if w.visible and w.state != WINDOW_STATE_MINIMIZED]

    def __iter__(self):
        return iter(self.windows)

    # -- alt-tab switcher -------------------------------------------------------
    def start_alt_tab(self):
        order = self.visible_windows()
        if not order:
            return
        self._alt_tab_order = order
        self._alt_tab_idx = 0
        self.alt_tab_active = True

    def alt_tab_cycle(self):
        if not self.alt_tab_active or not self._alt_tab_order:
            return
        self._alt_tab_idx = (self._alt_tab_idx + 1) % len(self._alt_tab_order)

    def alt_tab_activate(self):
        if not self.alt_tab_active or not self._alt_tab_order:
            return
        win = self._alt_tab_order[self._alt_tab_idx]
        self.focus(win)
        self.alt_tab_active = False
        self._alt_tab_order = []

    def alt_tab_cancel(self):
        self.alt_tab_active = False
        self._alt_tab_order = []

    # -- event handling ---------------------------------------------------------
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
                    if side in ("left", "right", "tl", "tr", "bl", "br", "max"):
                        if side == "max":
                            w.maximize(self.screen_rect)
                        else:
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
        x, y = pos
        sr = self.screen_rect
        self._snap_preview = None
        w2 = sr.width // 2
        h2 = sr.height // 2
        m = self.SNAP_MARGIN
        near_l = x <= sr.left + m
        near_r = x >= sr.right - m
        near_t = y <= sr.top + m
        near_b = y >= sr.bottom - m
        if near_l and near_t:
            self._snap_preview = {"side": "tl", "rect": pygame.Rect(sr.left, sr.top, w2, h2), "label": "Top-left"}
        elif near_r and near_t:
            self._snap_preview = {"side": "tr", "rect": pygame.Rect(sr.left + w2, sr.top, w2, h2), "label": "Top-right"}
        elif near_l and near_b:
            self._snap_preview = {"side": "bl", "rect": pygame.Rect(sr.left, sr.top + h2, w2, h2), "label": "Bottom-left"}
        elif near_r and near_b:
            self._snap_preview = {"side": "br", "rect": pygame.Rect(sr.left + w2, sr.top + h2, w2, h2), "label": "Bottom-right"}
        elif near_l:
            self._snap_preview = {"side": "left", "rect": pygame.Rect(sr.left, sr.top, w2, sr.height), "label": "Left"}
        elif near_r:
            self._snap_preview = {"side": "right", "rect": pygame.Rect(sr.left + w2, sr.top, w2, sr.height), "label": "Right"}
        elif win.rect.y <= sr.top + self.SNAP_MARGIN and y <= sr.top + self.SNAP_MARGIN:
            self._snap_preview = {"side": "max", "rect": pygame.Rect(sr), "label": "Maximize"}

    def draw_snap_preview(self, surface, theme):
        sp = self._snap_preview
        if not sp:
            return
        r = sp["rect"]
        if self._snap_preview_size != r.size:
            self._snap_preview_surf = pygame.Surface(r.size, pygame.SRCALPHA)
            self._snap_preview_size = r.size
        s = self._snap_preview_surf
        s.fill((0, 0, 0, 0))
        accent = theme.accent
        pygame.draw.rect(s, accent + (70,), s.get_rect(), border_radius=10)
        pygame.draw.rect(s, accent + (200,), s.get_rect(), 2, border_radius=10)
        surface.blit(s, r.topleft)
