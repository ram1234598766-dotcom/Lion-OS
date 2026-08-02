"""Reusable UI widgets for Lion-OS apps.

All widgets are plain classes that draw to a pygame Surface and process events
that fall within their local rect. The convention:

    widget.handle_event(event, rect) -> bool   (True if consumed)
    widget.draw(surface, rect)
    widget.update(dt)
"""

from __future__ import annotations

import math
import time
from typing import Callable, List, Optional, Tuple, Union

import pygame

from .theme import Theme

Color = Union[tuple, str]
Rect = pygame.Rect

# ---------------------------------------------------------------------------
# Shared caches (avoid per-frame allocations)
# ---------------------------------------------------------------------------
_font_cache: dict = {}
_tile_cache: dict = {}
_glass_cache: dict = {}


def cached_font(size: int, bold=False):
    """Return a cached default-font instance. Avoids re-creating a Font on
    every draw call, which churns memory and slows the loop."""
    key = (size, bold)
    f = _font_cache.get(key)
    if f is None:
        f = pygame.font.Font(None, size)
        if bold:
            f.set_bold(True)
        _font_cache[key] = f
    return f


def clear_font_cache():
    """Drop all cached Font objects.

    pygame.Font instances become invalid once the font module is quit (e.g.
    after ``pygame.quit()``); re-initializing the module does NOT resurrect
    them. Call this before re-initializing so fresh fonts are created."""
    _font_cache.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def rounded_rect(surface, rect, radius, color, width=0, border_radius=None):
    pygame.draw.rect(surface, color, rect, width=width,
                     border_radius=radius if border_radius is None else border_radius)


def tint(surface, color, alpha):
    """Overlay a translucent color over a surface."""
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    overlay.fill(color + (alpha,))
    surface.blit(overlay, (0, 0))


def text_size(text, font):
    return font.size(text)


def wrap_text(text, font, max_width):
    words = text.split(" ")
    lines = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        if font.size(trial)[0] <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------------------
# Widget base
# ---------------------------------------------------------------------------
class Widget:
    def __init__(self, rect: Rect = None):
        self.rect = rect or pygame.Rect(0, 0, 100, 30)
        self.visible = True
        self.enabled = True
        self.hovered = False
        self.pressed = False

    def contains(self, pos) -> bool:
        return self.visible and self.rect.collidepoint(pos)

    def handle_event(self, event, pos, theme: Theme) -> bool:
        return False

    def draw(self, surface: pygame.Surface, theme: Theme):
        pass

    def update(self, dt: float, theme: Theme):
        pass


# ---------------------------------------------------------------------------
# Label
# ---------------------------------------------------------------------------
class Label(Widget):
    def __init__(self, text="", rect=None, font=None, color=None, align="left",
                 valign="middle", auto_width=True, auto_height=True):
        super().__init__(rect or pygame.Rect(0, 0, 100, 20))
        self.text = text
        self.font = font
        self.color = color
        self.align = align
        self.valign = valign
        self.auto_width = auto_width
        self.auto_height = auto_height
        self.shadow = False

    def measure(self):
        f = self.font
        if f is None:
            return self.rect.size
        w, h = f.size(self.text)
        if self.auto_width:
            self.rect.width = w
        if self.auto_height:
            self.rect.height = h
        return w, h

    def draw(self, surface, theme):
        if not self.visible:
            return
        f = self.font
        if f is None:
            return
        text = self.text
        if not text:
            return
        color = self.color or theme.text
        img = f.render(text, True, color)
        rect = img.get_rect()
        if self.align == "center":
            rect.centerx = self.rect.centerx
        elif self.align == "right":
            rect.right = self.rect.right
        else:
            rect.left = self.rect.left
        if self.valign == "center" or self.valign == "middle":
            rect.centery = self.rect.centery
        elif self.valign == "top":
            rect.top = self.rect.top
        else:
            rect.bottom = self.rect.bottom
        if self.shadow:
            sh = f.render(text, True, theme.shadow[:3] if len(theme.shadow) == 4 else (0, 0, 0))
            surface.blit(sh, rect.move(1, 1))
        surface.blit(img, rect)


# ---------------------------------------------------------------------------
# Button
# ---------------------------------------------------------------------------
class Button(Widget):
    def __init__(self, text="", rect=None, font=None, on_click: Callable = None,
                 color=None, radius=8, align="center", icon=None):
        super().__init__(rect or pygame.Rect(0, 0, 90, 32))
        self.text = text
        self.font = font
        self.on_click = on_click
        self.color = color          # override accent
        self.radius = radius
        self.align = align
        self.icon = icon            # optional glyph drawn before text
        self._down = False

    def handle_event(self, event, pos, theme):
        if not self.visible or not self.enabled:
            return False
        inside = self.rect.collidepoint(pos)
        if event.type == pygame.MOUSEMOTION:
            self.hovered = inside
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and inside:
            self._down = True
            self.pressed = True
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was = self._down
            self._down = False
            self.pressed = False
            if was and inside:
                if self.on_click:
                    self.on_click()
                return True
        return False

    def draw(self, surface, theme):
        if not self.visible:
            return
        r = self.rect
        base = self.color or theme.accent
        if self.hovered and not self.pressed:
            base = theme.accent_alt if self.color is None else blend_color(base, (255, 255, 255), 0.12)
        if self.pressed:
            base = blend_color(base, (0, 0, 0), 0.15)
        if not self.enabled:
            base = blend_color(base, theme.bg_alt, 0.5)
        rounded_rect(surface, r, self.radius, base)
        if self.text:
            f = self.font
            if f:
                col = theme.text
                img = f.render(self.text, True, col)
                ir = img.get_rect(center=r.center)
                if self.icon:
                    ir.left = r.left + 12
                    ir.centery = r.centery
                surface.blit(img, ir)


def blend_color(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1[:3], c2[:3]))


# ---------------------------------------------------------------------------
# IconButton (square / circular)
# ---------------------------------------------------------------------------
class IconButton(Widget):
    def __init__(self, glyph, rect=None, on_click=None, color=None, radius=6):
        super().__init__(rect or pygame.Rect(0, 0, 28, 28))
        self.glyph = glyph
        self.on_click = on_click
        self.color = color
        self.radius = radius
        self._down = False

    def handle_event(self, event, pos, theme):
        if not self.visible or not self.enabled:
            return False
        inside = self.rect.collidepoint(pos)
        if event.type == pygame.MOUSEMOTION:
            self.hovered = inside
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and inside:
            self._down = True
            self.pressed = True
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was = self._down
            self._down = False
            self.pressed = False
            if was and inside:
                if self.on_click:
                    self.on_click()
                return True
        return False

    def draw(self, surface, theme):
        if not self.visible:
            return
        r = self.rect
        bg = None
        if self.pressed:
            bg = theme.active
        elif self.hovered:
            bg = theme.hover
        if bg:
            rounded_rect(surface, r, self.radius, bg)
        f = cached_font(int(r.height * 0.8))
        img = f.render(self.glyph, True, self.color or theme.text)
        surface.blit(img, img.get_rect(center=r.center))


# ---------------------------------------------------------------------------
# TextInput
# ---------------------------------------------------------------------------
class TextInput(Widget):
    def __init__(self, rect=None, font=None, placeholder="", initial="",
                 on_submit: Callable = None, on_change: Callable = None,
                 password=False, radius=8):
        super().__init__(rect or pygame.Rect(0, 0, 200, 34))
        self.font = font
        self.placeholder = placeholder
        self.text = initial
        self.cursor = len(initial)
        self.on_submit = on_submit
        self.on_change = on_change
        self.password = password
        self.radius = radius
        self.focused = False
        self._blink = 0.0
        self.scroll = 0

    def _display_text(self):
        if self.password:
            return "*" * len(self.text)
        return self.text

    def handle_event(self, event, pos, theme):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.focused = self.rect.collidepoint(pos)
            if self.focused:
                self.cursor = len(self.text)
            return self.focused
        if not self.focused:
            return False
        if event.type == pygame.KEYDOWN:
            k = event.key
            if k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.on_submit:
                    self.on_submit(self.text)
                return True
            if k == pygame.K_BACKSPACE:
                if self.cursor > 0:
                    self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
                    self.cursor -= 1
                    self._changed()
                return True
            if k == pygame.K_DELETE:
                self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]
                self._changed()
                return True
            if k == pygame.K_LEFT:
                self.cursor = max(0, self.cursor - 1)
                return True
            if k == pygame.K_RIGHT:
                self.cursor = min(len(self.text), self.cursor + 1)
                return True
            if k == pygame.K_HOME:
                self.cursor = 0
                return True
            if k == pygame.K_END:
                self.cursor = len(self.text)
                return True
            if k == pygame.K_a and (event.mod & pygame.KMOD_CTRL):
                self.cursor = len(self.text)
                return True
            if event.unicode and event.unicode.isprintable():
                self.text = self.text[:self.cursor] + event.unicode + self.text[self.cursor:]
                self.cursor += 1
                self._changed()
                return True
        return False

    def _changed(self):
        if self.on_change:
            self.on_change(self.text)

    def update(self, dt, theme):
        self._blink += dt

    def draw(self, surface, theme):
        if not self.visible:
            return
        r = self.rect
        bg = theme.surface_alt if not self.focused else theme.surface
        rounded_rect(surface, r, self.radius, bg)
        border = theme.accent if self.focused else theme.glass_border
        if len(border) == 4:
            pygame.draw.rect(surface, border[:3], r, 1, border_radius=self.radius)
        else:
            pygame.draw.rect(surface, border, r, 1, border_radius=self.radius)
        f = self.font
        txt = self._display_text()
        shown = txt
        col = theme.text if txt else theme.text_dim
        img = f.render(shown, True, col)
        text_rect = img.get_rect(midleft=(r.left + 10, r.centery))
        # crop to fit
        crop = pygame.Rect(text_rect)
        crop.right = min(crop.right, r.right - 8)
        if crop.width > 0:
            surface.blit(img, crop, area=(0, 0, crop.width - text_rect.left, crop.height))
        if self.focused and int(self._blink * 2) % 2 == 0:
            cx = min(text_rect.right + 2, r.right - 4)
            pygame.draw.line(surface, theme.accent, (cx, r.centery - 8), (cx, r.centery + 8), 2)


# ---------------------------------------------------------------------------
# Toggle switch
# ---------------------------------------------------------------------------
class Toggle(Widget):
    def __init__(self, rect=None, state=False, on_toggle: Callable = None):
        super().__init__(rect or pygame.Rect(0, 0, 44, 22))
        self.state = state
        self.on_toggle = on_toggle

    def handle_event(self, event, pos, theme):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(pos):
            self.state = not self.state
            if self.on_toggle:
                self.on_toggle(self.state)
            return True
        return False

    def draw(self, surface, theme):
        r = self.rect
        track = self.rect.inflate(-4, -4)
        on_color = theme.accent
        off_color = theme.surface_alt
        rounded_rect(surface, track, track.height // 2,
                     on_color if self.state else off_color)
        knob_r = track.height // 2 - 2
        if self.state:
            cx = track.right - knob_r - 3
        else:
            cx = track.left + knob_r + 3
        pygame.draw.circle(surface, (255, 255, 255), (cx, track.centery), knob_r)


# ---------------------------------------------------------------------------
# Slider
# ---------------------------------------------------------------------------
class Slider(Widget):
    def __init__(self, rect=None, value=0.0, min_v=0.0, max_v=1.0,
                 on_change: Callable = None, step=None):
        super().__init__(rect or pygame.Rect(0, 0, 160, 24))
        self.value = value
        self.min = min_v
        self.max = max_v
        self.on_change = on_change
        self.step = step
        self._drag = False

    @property
    def ratio(self):
        if self.max == self.min:
            return 0.0
        return (self.value - self.min) / (self.max - self.min)

    def set_ratio(self, r):
        r = max(0.0, min(1.0, r))
        v = self.min + r * (self.max - self.min)
        if self.step:
            v = round(v / self.step) * self.step
        if v != self.value:
            self.value = v
            if self.on_change:
                self.on_change(v)

    def handle_event(self, event, pos, theme):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(pos):
            self._drag = True
            self.set_ratio((pos[0] - self.rect.left) / self.rect.width)
            return True
        if event.type == pygame.MOUSEMOTION and self._drag:
            self.set_ratio((pos[0] - self.rect.left) / self.rect.width)
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._drag:
            self._drag = False
            return True
        return False

    def draw(self, surface, theme):
        r = self.rect
        cy = r.centery
        pygame.draw.line(surface, theme.surface_alt, (r.left, cy), (r.right, cy), 4)
        fill_w = int(r.width * self.ratio)
        if fill_w > 0:
            pygame.draw.line(surface, theme.accent, (r.left, cy), (r.left + fill_w, cy), 4)
        knob_x = r.left + fill_w
        pygame.draw.circle(surface, theme.accent, (knob_x, cy), 8)
        pygame.draw.circle(surface, (255, 255, 255), (knob_x, cy), 3)


# ---------------------------------------------------------------------------
# Scroll area
# ---------------------------------------------------------------------------
class ScrollArea(Widget):
    """Draws a clipped region with vertical scrollbar around its child widgets."""

    def __init__(self, rect=None):
        super().__init__(rect or pygame.Rect(0, 0, 200, 200))
        self.content_height = 0
        self.offset = 0          # scroll offset in px
        self.scrollbar_w = 8
        self._drag = False
        self.dragging = False
        self.hover_scroll = False

    @property
    def max_offset(self):
        return max(0, self.content_height - self.rect.height)

    def handle_event(self, event, pos, theme):
        if not self.visible:
            return False
        if not self.rect.collidepoint(pos):
            return False
        # scroll wheel
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5) and self.rect.collidepoint(pos):
            direction = -40 if event.button == 4 else 40
            self.offset = max(0, min(self.max_offset, self.offset + direction))
            return True
        if event.type == pygame.MOUSEWHEEL and self.rect.collidepoint(pos):
            self.offset = max(0, min(self.max_offset, self.offset - event.y * 40))
            return True
        # scrollbar drag
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.max_offset > 0:
                sb = self._scrollbar_rect()
                if sb.collidepoint(pos):
                    self._drag = True
                    self.dragging = True
                    self._set_from_mouse(pos[1])
                    return True
        if event.type == pygame.MOUSEMOTION and self._drag:
            self._set_from_mouse(pos[1])
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._drag:
            self._drag = False
            self.dragging = False
            return True
        return False

    def _scrollbar_rect(self):
        h = max(30, int(self.rect.height * self.rect.height / max(1, self.content_height)))
        ratio = self.offset / max(1, self.max_offset)
        y = self.rect.top + ratio * (self.rect.height - h)
        return pygame.Rect(self.rect.right - self.scrollbar_w - 2, y, self.scrollbar_w, h)

    def _set_from_mouse(self, my):
        if self.max_offset <= 0:
            return
        h = max(30, int(self.rect.height * self.rect.height / max(1, self.content_height)))
        track = self.rect.height - h
        ratio = (my - self.rect.top) / max(1, track)
        self.offset = max(0, min(self.max_offset, int(ratio * self.max_offset)))

    def draw(self, surface, theme):
        if not self.visible:
            return
        if self.max_offset > 0:
            sb = self._scrollbar_rect()
            rounded_rect(surface, sb, 4, theme.scrollbar)
        # children are drawn by callers into a clipped surface


# ---------------------------------------------------------------------------
# List (selectable rows)
# ---------------------------------------------------------------------------
class ListItem:
    def __init__(self, text, data=None, icon=None, color=None):
        self.text = text
        self.data = data
        self.icon = icon
        self.color = color


class ListBox(Widget):
    def __init__(self, rect=None, font=None, on_select: Callable = None,
                 on_activate: Callable = None):
        super().__init__(rect or pygame.Rect(0, 0, 200, 200))
        self.items: List[ListItem] = []
        self.selected: Optional[int] = None
        self.font = font
        self.on_select = on_select
        self.on_activate = on_activate
        self.scroll = 0
        self.row_h = 30
        self.scroll_area = ScrollArea(rect)

    def set_items(self, items: List[ListItem]):
        self.items = items
        self.selected = None
        if self.on_select:
            self.on_select(None)

    def clear(self):
        self.items.clear()
        self.selected = None

    def handle_event(self, event, pos, theme):
        if not self.visible or not self.rect.collidepoint(pos):
            return False
        # scroll wheel
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5) and self.rect.collidepoint(pos):
            self.scroll = max(0, min(self.max_scroll, self.scroll + (-40 if event.button == 4 else 40)))
            return True
        if event.type == pygame.MOUSEWHEEL and self.rect.collidepoint(pos):
            self.scroll = max(0, min(self.max_scroll, self.scroll - event.y * 40))
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(pos):
            idx = self.index_at(pos)
            if idx is not None:
                self.selected = idx
                if self.on_select:
                    self.on_select(self.items[idx])
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3 and self.rect.collidepoint(pos):
            idx = self.index_at(pos)
            if idx is not None:
                self.selected = idx
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.on_activate and self.rect.collidepoint(pos):
                idx = self.index_at(pos)
                if idx is not None and self.selected == idx:
                    self.on_activate(self.items[idx])
            return False
        return False

    @property
    def max_scroll(self):
        return max(0, len(self.items) * self.row_h - self.rect.height)

    def index_at(self, pos):
        if not self.rect.collidepoint(pos):
            return None
        y = pos[1] - self.rect.top + self.scroll
        idx = y // self.row_h
        if 0 <= idx < len(self.items):
            return idx
        return None

    def draw(self, surface, theme):
        if not self.visible:
            return
        r = self.rect
        clip = pygame.Rect(r)
        old = surface.get_clip()
        surface.set_clip(clip)
        f = self.font
        start = self.scroll // self.row_h
        for i in range(start, len(self.items)):
            y = r.top - (self.scroll % self.row_h) + i * self.row_h
            if y > r.bottom:
                break
            item = self.items[i]
            row = pygame.Rect(r.left, y, r.width, self.row_h)
            if i == self.selected:
                pygame.draw.rect(surface, theme.selection if len(theme.selection) == 3
                                 else theme.selection[:3], row)
                if len(theme.selection) == 4:
                    ov = pygame.Surface(row.size, pygame.SRCALPHA)
                    ov.fill(theme.selection)
                    surface.blit(ov, row.topleft)
            elif row.collidepoint(pygame.mouse.get_pos()) and self.rect.collidepoint(pygame.mouse.get_pos()):
                pygame.draw.rect(surface, theme.hover if len(theme.hover) == 3 else theme.hover[:3], row)
            if item.icon:
                ig = f.render(item.icon, True, item.color or theme.text_dim)
                surface.blit(ig, ig.get_rect(midleft=(r.left + 10, y + self.row_h // 2)))
                tx = r.left + 34
            else:
                tx = r.left + 12
            img = f.render(item.text, True, item.color or theme.text)
            surface.blit(img, img.get_rect(midleft=(tx, y + self.row_h // 2)))
        surface.set_clip(old)
        if self.max_scroll > 0:
            sh = max(30, int(r.height * r.height / max(1, len(self.items) * self.row_h)))
            ratio = self.scroll / self.max_scroll
            sy = r.top + ratio * (r.height - sh)
            pygame.draw.rect(surface, theme.scrollbar,
                             pygame.Rect(r.right - 10, sy, 6, sh), border_radius=3)


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------
class ProgressBar(Widget):
    def __init__(self, rect=None, value=0.0, max_v=1.0, color=None):
        super().__init__(rect or pygame.Rect(0, 0, 200, 12))
        self.value = value
        self.max_v = max_v
        self.color = color
        self.label = None

    def draw(self, surface, theme):
        r = self.rect
        rounded_rect(surface, r, r.height // 2, theme.surface_alt)
        if self.max_v > 0:
            ratio = min(1.0, self.value / self.max_v)
            if ratio > 0:
                fr = pygame.Rect(r.left, r.top, int(r.width * ratio), r.height)
                rounded_rect(surface, fr, r.height // 2, self.color or theme.accent)
        if self.label:
            f = cached_font(int(r.height * 0.8))
            img = f.render(self.label, True, theme.text)
            surface.blit(img, img.get_rect(center=r.center))


# ---------------------------------------------------------------------------
# Dropdown / Menu (popup)
# ---------------------------------------------------------------------------
class Menu:
    """A simple popup menu rendered on the screen surface."""

    def __init__(self, items: List[Tuple[str, Optional[Callable]]],
                 pos, font, theme, width=180, on_close: Callable = None):
        self.items = items
        self.pos = pos
        self.font = font
        self.theme = theme
        self.width = width
        self.row_h = 30
        self.selected = None
        self.on_close = on_close
        self.visible = True
        self.height = len(items) * self.row_h + 8
        self.rect = pygame.Rect(pos[0], pos[1], width, self.height)

    def handle_event(self, event, pos, theme):
        if not self.visible:
            return False
        if event.type == pygame.MOUSEMOTION:
            self.selected = None
            if self.rect.collidepoint(pos):
                idx = (pos[1] - self.rect.top - 4) // self.row_h
                if 0 <= idx < len(self.items):
                    self.selected = idx
            return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(pos):
                return True
            self.close()
            return False
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.rect.collidepoint(pos):
                idx = (pos[1] - self.rect.top - 4) // self.row_h
                if 0 <= idx < len(self.items):
                    text, cb = self.items[idx]
                    self.close()
                    if cb:
                        cb()
                return True
            self.close()
        return False

    def close(self):
        self.visible = False
        if self.on_close:
            self.on_close()

    def draw(self, surface, theme):
        if not self.visible:
            return
        # clamp to screen
        scr = surface.get_rect()
        rect = self.rect.clamp(scr)
        sh = pygame.Surface(rect.size, pygame.SRCALPHA)
        base = theme.glass if len(theme.glass) == 4 else theme.surface
        pygame.draw.rect(sh, base[:4], sh.get_rect(), border_radius=10)
        pygame.draw.rect(sh, (255, 255, 255, 40), sh.get_rect(), 1, border_radius=10)
        for i, (text, cb) in enumerate(self.items):
            y = 4 + i * self.row_h
            if i == self.selected:
                pygame.draw.rect(sh, theme.active, (4, y, rect.width - 8, self.row_h - 4), border_radius=6)
            img = self.font.render(text, True, theme.text)
            sh.blit(img, (14, y + (self.row_h - img.get_height()) // 2))
        surface.blit(sh, rect.topleft)


# ---------------------------------------------------------------------------
# Toast / notification
# ---------------------------------------------------------------------------
class Toast:
    def __init__(self, title, message, theme, on_done=None, kind="info"):
        self.title = title
        self.message = message
        self.theme = theme
        self.on_done = on_done
        self.kind = kind
        self.created = time.time()
        self.lifetime = 4.0
        self.anim = 0.0
        self.slide = 0.0
        self.done = False

    def update(self, dt):
        self.slide = min(1.0, self.slide + dt * 4)
        age = time.time() - self.created
        self.anim = max(0.0, min(1.0, (self.lifetime - age)))
        if age >= self.lifetime:
            self.done = True

    def draw(self, surface, theme, pos):
        if self.done:
            return
        w = 320
        h = 72
        font = cached_font(18)
        small = cached_font(15)
        x = pos[0]
        y = int(pos[1] - (1 - self.slide) * 30 - (1 - self.slide) * h * 0.2)
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(s, (30, 30, 40, 235), s.get_rect(), border_radius=12)
        pygame.draw.rect(s, (255, 255, 255, 40), s.get_rect(), 1, border_radius=12)
        color = {"info": (82, 156, 222), "success": (46, 204, 113),
                 "warn": (241, 196, 15), "error": (231, 76, 60)}.get(self.kind, (82, 156, 222))
        pygame.draw.circle(s, color, (28, h // 2), 8)
        t = font.render(self.title, True, (235, 235, 245))
        s.blit(t, (48, 12))
        m = small.render(self.message, True, (170, 170, 185))
        s.blit(m, (48, 38))
        surface.blit(s, (x, y))
        # fade out
        if self.anim < 1.0:
            s.set_alpha(int(self.anim * 255))


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


# ---------------------------------------------------------------------------
# Window chrome drawing helpers
# ---------------------------------------------------------------------------
def draw_glass_panel(surface, rect, theme, radius=12, border=True):
    """Draw a translucent glassmorphism panel (cached by size + theme)."""
    key = (rect.size, theme.glass, theme.glass_border, radius, border)
    s = _glass_cache.get(key)
    if s is None:
        s = pygame.Surface(rect.size, pygame.SRCALPHA)
        base = theme.glass if len(theme.glass) == 4 else theme.surface + (220,)
        pygame.draw.rect(s, base, s.get_rect(), border_radius=radius)
        if border:
            bc = theme.glass_border
            pygame.draw.rect(s, bc if len(bc) == 4 else bc + (60,), s.get_rect(), 1, border_radius=radius)
        _glass_cache[key] = s
    surface.blit(s, rect.topleft)


def draw_app_tile(surface, rect, glyph, theme, hovered=False, pressed=False,
                  selected=False, font_size=None, label=None,
                  icon_cache=None, scene=None, scene_id=None):
    """Draw a gradient app-icon tile, used across the desktop.

    The gradient base is cached per (size, colors) so desktop icons, launcher
    tiles and taskbar icons reuse one surface instead of allocating a new
    gradient (and a new font) on every frame.

    When ``icon_cache`` and ``scene`` are provided, the procedural vector icon
    is drawn as the artwork; ``glyph`` is then only the emoji fallback.
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
    # clip glyph to tile rect (matches original behavior)
    old = surface.get_clip()
    clip = pygame.Rect(r)
    surface.set_clip(clip)
    surface.blit(tile, r.topleft)
    # hover/press overlay drawn directly (cheap) without re-rendering the base
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
