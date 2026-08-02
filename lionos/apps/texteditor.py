"""Text editor app for Lion-OS with syntax highlighting."""

from __future__ import annotations

import os
import re

import pygame

from .base import App
from ..widgets import Button, cached_font, rounded_rect

# lightweight syntax highlighting for common languages
TOKEN_PATTERNS = [
    ("comment", r"(#.*|//.*|/\*.*?\*/)"),
    ("string", r"(\"[^\"]*\"|'[^']*')"),
    ("number", r"(\b\d+\.?\d*\b)"),
    ("keyword", r"(\b(?:def|class|import|from|return|if|elif|else|for|while|try|except|with|as|pass|break|continue|lambda|yield|global|nonlocal|and|or|not|in|is|None|True|False|print|self|super)\b)"),
    ("func", r"([a-zA-Z_]\w*(?=\())"),
]

TOKEN_COLORS = {
    "comment": (120, 130, 140),
    "string": (163, 191, 106),
    "number": (214, 157, 133),
    "keyword": (198, 120, 221),
    "func": (97, 175, 239),
}


class TextEditorApp(App):
    name = "Text Editor"
    icon = "✎"
    description = "Edit plain text and code files"
    category = "Utilities"
    default_w = 760
    default_h = 520
    resizable = True
    GUTTER_W = 40  # fixed width of the line-number gutter (px)

    def __init__(self, os, window=None, path=None):
        super().__init__(os, window)
        self.path = path
        self.lines = [""]
        self.cursor_line = 0
        self.cursor_col = 0
        self.scroll = 0
        self.scroll_x = 0
        self.font_size = self.os.config.font_size
        self._blink = 0.0
        self.dirty = False
        self.status = "Untitled"
        self._read_only_warning = ""
        self.find_active = False
        self.find_query = ""
        self.find_matches = []
        self.find_current = 0
        self._find_by_line = {}
        if path:
            self._load(path)

    def _load(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            self.lines = content.split("\n")
            self.path = path
            self.status = os.path.basename(path)
            self.dirty = False
            self._update_title()
        except OSError as e:
            self._read_only_warning = f"Cannot open: {e}"

    @property
    def dirty(self):
        return getattr(self, "_dirty", False)

    @dirty.setter
    def dirty(self, value):
        if getattr(self, "_dirty", False) != value:
            self._dirty = value
            self._update_title()

    def _update_title(self):
        """Window title shows a bullet when there are unsaved changes."""
        if not getattr(self, "path", None):
            return
        name = os.path.basename(self.path)
        self.set_title(name + (" •" if self.dirty else ""))

    def _font(self):
        """Font used for the text area, sized to the configured font size."""
        if hasattr(self.os, "get_font"):
            return self.os.get_font(self.font_size)
        return cached_font(self.font_size)

    def _fill_rgba(self, surface, rect, rgba):
        """Blit a translucent rectangle (theme RGBA colors need a temp surface)."""
        if rect.width <= 0 or rect.height <= 0:
            return
        tmp = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        tmp.fill(rgba)
        surface.blit(tmp, rect)

    def _text_x(self):
        """Document-relative x of the left edge of the text (after the gutter)."""
        return self._text_rect().x + self.GUTTER_W

    def on_resize(self, rect):
        self.rect = rect

    def handle_event(self, event, local_pos):
        if event.type == pygame.KEYDOWN:
            return self._handle_key(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._toolbar_rect().collidepoint(local_pos):
                return False
            # click to place cursor
            self._place_cursor(local_pos)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            self.scroll = max(0, min(self._max_scroll(), self.scroll + (-30 if event.button == 4 else 30)))
            return True
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(self._max_scroll(), self.scroll - event.y * 30))
            return True
        return False

    def _toolbar_rect(self):
        return pygame.Rect(self.rect.x, self.rect.y, self.rect.width, 40)

    def _text_rect(self):
        return pygame.Rect(self.rect.x, self.rect.y + 44, self.rect.width, self.rect.height - 60)

    def _line_h(self):
        return self.font_size + 6

    def _max_scroll(self):
        return max(0, len(self.lines) * self._line_h() - self._text_rect().height)

    def _place_cursor(self, pos):
        tr = self._text_rect()
        line_idx = (pos[1] - tr.y + self.scroll) // self._line_h()
        line_idx = max(0, min(len(self.lines) - 1, line_idx))
        self.cursor_line = line_idx
        line = self.lines[line_idx]
        # find nearest col (account for gutter + horizontal scroll offset)
        font = self._font()
        x0 = pos[0] + self.scroll_x - self._text_x()
        best_col = 0
        best_dist = 99999
        for c in range(len(line) + 1):
            w = font.size(line[:c])[0]
            d = abs(x0 - w)
            if d < best_dist:
                best_dist = d
                best_col = c
        self.cursor_col = best_col
        self._ensure_visible()

    def _handle_key(self, event):
        k = event.key
        mod = event.mod
        line = self.lines[self.cursor_line]
        if k == pygame.K_f and mod & pygame.KMOD_CTRL:
            self._toggle_find()
            return True
        if k == pygame.K_F3:
            self._toggle_find()
            return True
        if self.find_active:
            if k == pygame.K_ESCAPE:
                self.find_active = False
                return True
            if k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._find_next()
                return True
            if k == pygame.K_BACKSPACE:
                self.find_query = self.find_query[:-1]
                self._rebuild_find()
                return True
            if event.unicode and event.unicode.isprintable():
                self.find_query += event.unicode
                self._rebuild_find()
                return True
        if k == pygame.K_BACKSPACE:
            if self.cursor_col > 0:
                self.lines[self.cursor_line] = line[:self.cursor_col - 1] + line[self.cursor_col:]
                self.cursor_col -= 1
            elif self.cursor_line > 0:
                prev = self.lines[self.cursor_line - 1]
                self.cursor_col = len(prev)
                self.lines.pop(self.cursor_line)
                self.cursor_line -= 1
            self.dirty = True
            self._ensure_visible()
            return True
        if k == pygame.K_DELETE:
            if self.cursor_col < len(line):
                self.lines[self.cursor_line] = line[:self.cursor_col] + line[self.cursor_col + 1:]
            elif self.cursor_line < len(self.lines) - 1:
                self.lines[self.cursor_line] += self.lines.pop(self.cursor_line + 1)
            self.dirty = True
            self._ensure_visible()
            return True
        if k == pygame.K_RETURN:
            self.lines.insert(self.cursor_line + 1, line[self.cursor_col:])
            self.lines[self.cursor_line] = line[:self.cursor_col]
            self.cursor_line += 1
            self.cursor_col = 0
            self.dirty = True
            self._ensure_visible()
            return True
        if k == pygame.K_TAB:
            self.lines[self.cursor_line] = line[:self.cursor_col] + "    " + line[self.cursor_col:]
            self.cursor_col += 4
            self.dirty = True
            self._ensure_visible()
            return True
        if k == pygame.K_UP:
            if self.cursor_line > 0:
                self.cursor_line -= 1
                self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))
            self._ensure_visible()
            return True
        if k == pygame.K_DOWN:
            if self.cursor_line < len(self.lines) - 1:
                self.cursor_line += 1
                self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))
            self._ensure_visible()
            return True
        if k == pygame.K_LEFT:
            self.cursor_col = max(0, self.cursor_col - 1)
            self._ensure_visible()
            return True
        if k == pygame.K_RIGHT:
            self.cursor_col = min(len(line), self.cursor_col + 1)
            self._ensure_visible()
            return True
        if k == pygame.K_HOME:
            self.cursor_col = 0
            self._ensure_visible()
            return True
        if k == pygame.K_END:
            self.cursor_col = len(line)
            self._ensure_visible()
            return True
        if k == pygame.K_s and mod & pygame.KMOD_CTRL:
            self._save()
            return True
        if k == pygame.K_o and mod & pygame.KMOD_CTRL:
            self._open_dialog()
            return True
        if event.unicode and event.unicode.isprintable():
            self.lines[self.cursor_line] = line[:self.cursor_col] + event.unicode + line[self.cursor_col:]
            self.cursor_col += 1
            self.dirty = True
            self._ensure_visible()
            return True
        return False

    def _save(self):
        if not self.path:
            self._read_only_warning = "Use Ctrl+O to pick a file first (File Manager)"
            return
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.lines))
            self.dirty = False
            self.status = os.path.basename(self.path)
            self.show_toast("Text Editor", "Saved", "success")
        except OSError as e:
            self._read_only_warning = f"Save failed: {e}"

    def _open_dialog(self):
        self.show_toast("Text Editor",
                        "Tip: use File Manager → right-click a file → 'Open in Text Editor'",
                        "info")

    # -- find-in-text --------------------------------------------------------
    def _toggle_find(self):
        self.find_active = not self.find_active
        if self.find_active:
            self.find_query = ""
            self.find_matches = []
            self.find_current = 0
            self._find_by_line = {}

    def _rebuild_find(self):
        """Recompute every occurrence of the query across all lines."""
        q = self.find_query
        self.find_matches = []
        self._find_by_line = {}
        self.find_current = 0
        if not q:
            return
        lower = q.lower()
        for li, line in enumerate(self.lines):
            text = line.lower()
            start = 0
            while True:
                idx = text.find(lower, start)
                if idx == -1:
                    break
                self.find_matches.append((li, idx, idx + len(q)))
                self._find_by_line.setdefault(li, []).append((idx, idx + len(q)))
                start = idx + len(q)
        if self.find_matches:
            self._go_to_match(0)

    def _go_to_match(self, i):
        if not self.find_matches:
            return
        self.find_current = i % len(self.find_matches)
        li, cs, _ce = self.find_matches[self.find_current]
        self.cursor_line = li
        self.cursor_col = cs
        self._ensure_visible()

    def _find_next(self):
        if self.find_matches:
            self._go_to_match(self.find_current + 1)

    # -- scrolling -----------------------------------------------------------
    def _ensure_visible(self):
        """Scroll vertically/horizontally so the cursor line stays on screen."""
        tr = self._text_rect()
        line_h = self._line_h()
        top = self.cursor_line * line_h
        if top < self.scroll:
            self.scroll = top
        elif top + line_h > self.scroll + tr.height:
            self.scroll = top + line_h - tr.height
        self.scroll = max(0, min(self._max_scroll(), self.scroll))
        font = self._font()
        line = self.lines[self.cursor_line]
        cw = font.size(line[:self.cursor_col])[0]
        avail = tr.width - self.GUTTER_W - 24
        if cw < self.scroll_x:
            self.scroll_x = cw
        elif cw > self.scroll_x + avail:
            self.scroll_x = cw - avail
        self.scroll_x = max(0, self.scroll_x)

    def _find_rect(self):
        return pygame.Rect(self.rect.right - 316, self.rect.y + 48, 300, 32)

    def _draw_find_box(self, surface):
        r = self._find_rect()
        rounded_rect(surface, r, 8, self.theme.surface_alt)
        pygame.draw.rect(surface, self.theme.accent, r, 1, border_radius=8)
        font = self._font()
        label = font.render("Find:", True, self.theme.text_dim)
        surface.blit(label, (r.x + 10, r.centery - label.get_height() // 2))
        qx = r.x + 10 + label.get_width() + 8
        count_txt = ""
        if self.find_query:
            count_txt = (f"{self.find_current + 1}/{len(self.find_matches)}"
                         if self.find_matches else "0/0")
        cimg = None
        cw = 0
        if count_txt:
            cimg = font.render(count_txt, True, self.theme.text_dim)
            cw = cimg.get_width()
        disp = self.find_query
        if int(self._blink * 2) % 2 == 0:
            disp += "▏"
        qimg = font.render(disp, True, self.theme.text)
        old = surface.get_clip()
        surface.set_clip(pygame.Rect(qx, r.y, max(8, r.right - 10 - cw - qx), r.height))
        surface.blit(qimg, (qx, r.centery - qimg.get_height() // 2))
        surface.set_clip(old)
        if cimg:
            surface.blit(cimg, (r.right - 10 - cw, r.centery - cimg.get_height() // 2))

    def update(self, dt):
        self._blink += dt

    def _highlight(self, text):
        """Return list of (token_text, color) runs for a line."""
        if not text:
            return []
        # simple combined regex matcher
        combined = "|".join(pattern for _, pattern in TOKEN_PATTERNS)
        runs = []
        last = 0
        for m in re.finditer(combined, text):
            if m.start() > last:
                runs.append((text[last:m.start()], None))
            for i, (name, _) in enumerate(TOKEN_PATTERNS):
                if m.group(i + 1) is not None:
                    runs.append((m.group(i + 1), TOKEN_COLORS[name]))
                    break
            last = m.end()
        if last < len(text):
            runs.append((text[last:], None))
        return runs

    def draw(self, surface, rect):
        self.rect = rect
        # toolbar
        tb = self._toolbar_rect()
        rounded_rect(surface, tb, 0, self.theme.surface_alt)
        font = cached_font(self.os.config.font_size)
        if self.path:
            label = f"● {self.status}" if self.dirty else self.status
        else:
            label = self.status
        img = font.render(label, True, self.theme.text_dim)
        surface.blit(img, (tb.x + 12, tb.centery - img.get_height() // 2))
        save_b = pygame.Rect(tb.right - 110, tb.y + 5, 100, 30)
        hover = save_b.collidepoint(pygame.mouse.get_pos())
        rounded_rect(surface, save_b, 8, self.theme.accent if hover else self.theme.surface)
        s_img = font.render("Save (Ctrl+S)", True, self.theme.text)
        surface.blit(s_img, s_img.get_rect(center=save_b.center))

        # text area
        tr = self._text_rect()
        line_h = self._line_h()
        text_x = self._text_x()
        clip = pygame.Rect(tr)
        old = surface.get_clip()
        surface.set_clip(clip)
        # gutter: subtle column behind the fixed-width line numbers
        self._fill_rgba(surface, pygame.Rect(tr.x, tr.y, self.GUTTER_W, tr.height),
                        self.theme.active)
        self._fill_rgba(surface, pygame.Rect(tr.x + self.GUTTER_W, tr.y, 1, tr.height),
                        self.theme.glass_border)
        # line numbers
        font = self._font()
        visible = tr.height // line_h + 1
        start = self.scroll // line_h
        for i in range(start, min(start + visible + 2, len(self.lines))):
            y = tr.y - (self.scroll % line_h) + i * line_h
            if y < tr.y - line_h:
                continue
            line = self.lines[i]
            # line number (right-aligned inside the fixed gutter)
            nimg = font.render(str(i + 1), True, self.theme.text_dim)
            surface.blit(nimg, (text_x - 8 - nimg.get_width(), y + 2))
            # highlight background for cursor line (text area only, fixed gutter)
            if i == self.cursor_line:
                hl = pygame.Rect(text_x, y, tr.width - self.GUTTER_W, line_h)
                pygame.draw.rect(surface, self.theme.active, hl)
            # find-in-text highlights behind the matching substrings
            for mcs, mce in self._find_by_line.get(i, ()):
                sw = font.size(line[:mcs])[0]
                ew = font.size(line[:mce])[0]
                rgba = self.theme.selection
                if self.find_matches and self.find_matches[self.find_current][:2] == (i, mcs):
                    rgba = (*self.theme.accent, 120)
                self._fill_rgba(surface,
                                pygame.Rect(text_x + sw - self.scroll_x, y,
                                            ew - sw, line_h),
                                rgba)
            # highlighted code (shifted left by the horizontal scroll offset)
            x = text_x - self.scroll_x
            for tok, color in self._highlight(line):
                col = color if color else self.theme.text
                timg = font.render(tok, True, col)
                surface.blit(timg, (x, y + 2))
                x += timg.get_width()
            # cursor
            if i == self.cursor_line and int(self._blink * 2) % 2 == 0:
                cw = font.size(line[:self.cursor_col])[0]
                cx = text_x + cw - self.scroll_x
                cy = y + 2
                pygame.draw.line(surface, self.theme.accent, (cx, cy), (cx, cy + font.get_height()), 2)
        surface.set_clip(old)
        if self._read_only_warning:
            wimg = font.render(self._read_only_warning, True, self.theme.warn)
            surface.blit(wimg, (text_x, tr.bottom - 24))
        if self.find_active:
            self._draw_find_box(surface)
        # scrollbar
        max_s = self._max_scroll()
        if max_s > 0:
            sh = max(30, int(tr.height * tr.height / max(1, len(self.lines) * line_h)))
            ratio = self.scroll / max_s
            sy = tr.y + ratio * (tr.height - sh)
            pygame.draw.rect(surface, self.theme.scrollbar, pygame.Rect(tr.right - 8, sy, 6, sh), border_radius=3)
