"""Text editor app for Lion-OS with syntax highlighting."""

from __future__ import annotations

import os
import re

import pygame

from .base import App
from ..widgets import Button, rounded_rect

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

    def __init__(self, os, window=None, path=None):
        super().__init__(os, window)
        self.path = path
        self.lines = [""]
        self.cursor_line = 0
        self.cursor_col = 0
        self.scroll = 0
        self.font_size = self.os.config.font_size
        self._blink = 0.0
        self.dirty = False
        self.status = "Untitled"
        self._read_only_warning = ""
        if path:
            self._load(path)

    def _load(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            self.lines = content.split("\n")
            self.path = path
            self.set_title(os.path.basename(path))
            self.status = os.path.basename(path)
        except OSError as e:
            self._read_only_warning = f"Cannot open: {e}"

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
        # find nearest col
        font = pygame.font.Font(None, self.font_size)
        best_col = 0
        best_dist = 99999
        for c in range(len(line) + 1):
            w = font.size(line[:c])[0]
            d = abs(pos[0] - tr.x - w)
            if d < best_dist:
                best_dist = d
                best_col = c
        self.cursor_col = best_col

    def _handle_key(self, event):
        k = event.key
        mod = event.mod
        line = self.lines[self.cursor_line]
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
            return True
        if k == pygame.K_DELETE:
            if self.cursor_col < len(line):
                self.lines[self.cursor_line] = line[:self.cursor_col] + line[self.cursor_col + 1:]
            elif self.cursor_line < len(self.lines) - 1:
                self.lines[self.cursor_line] += self.lines.pop(self.cursor_line + 1)
            self.dirty = True
            return True
        if k == pygame.K_RETURN:
            self.lines.insert(self.cursor_line + 1, line[self.cursor_col:])
            self.lines[self.cursor_line] = line[:self.cursor_col]
            self.cursor_line += 1
            self.cursor_col = 0
            self.dirty = True
            return True
        if k == pygame.K_TAB:
            self.lines[self.cursor_line] = line[:self.cursor_col] + "    " + line[self.cursor_col:]
            self.cursor_col += 4
            self.dirty = True
            return True
        if k == pygame.K_UP:
            if self.cursor_line > 0:
                self.cursor_line -= 1
                self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))
            return True
        if k == pygame.K_DOWN:
            if self.cursor_line < len(self.lines) - 1:
                self.cursor_line += 1
                self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))
            return True
        if k == pygame.K_LEFT:
            self.cursor_col = max(0, self.cursor_col - 1)
            return True
        if k == pygame.K_RIGHT:
            self.cursor_col = min(len(line), self.cursor_col + 1)
            return True
        if k == pygame.K_HOME:
            self.cursor_col = 0
            return True
        if k == pygame.K_END:
            self.cursor_col = len(line)
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
        font = pygame.font.Font(None, self.os.config.font_size)
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
        clip = pygame.Rect(tr)
        old = surface.get_clip()
        surface.set_clip(clip)
        # line numbers
        font = pygame.font.Font(None, self.font_size)
        visible = tr.height // line_h + 1
        start = self.scroll // line_h
        for i in range(start, min(start + visible + 2, len(self.lines))):
            y = tr.y - (self.scroll % line_h) + i * line_h
            if y < tr.y - line_h:
                continue
            line = self.lines[i]
            # line number
            nimg = font.render(str(i + 1), True, self.theme.text_dim)
            surface.blit(nimg, (tr.x + 6, y + 2))
            # highlight background for cursor line
            if i == self.cursor_line:
                hl = pygame.Rect(tr.x + 34, y, tr.width - 34, line_h)
                pygame.draw.rect(surface, self.theme.active, hl)
            # highlighted code
            x = tr.x + 40
            for tok, color in self._highlight(line):
                col = color if color else self.theme.text
                timg = font.render(tok, True, col)
                surface.blit(timg, (x, y + 2))
                x += timg.get_width()
            # cursor
            if i == self.cursor_line and int(self._blink * 2) % 2 == 0:
                cw = font.size(line[:self.cursor_col])[0]
                cx = tr.x + 40 + cw
                cy = y + 2
                pygame.draw.line(surface, self.theme.accent, (cx, cy), (cx, cy + font.get_height()), 2)
        surface.set_clip(old)
        if self._read_only_warning:
            wimg = font.render(self._read_only_warning, True, self.theme.warn)
            surface.blit(wimg, (tr.x + 40, tr.bottom - 24))
        # scrollbar
        max_s = self._max_scroll()
        if max_s > 0:
            sh = max(30, int(tr.height * tr.height / max(1, len(self.lines) * line_h)))
            ratio = self.scroll / max_s
            sy = tr.y + ratio * (tr.height - sh)
            pygame.draw.rect(surface, self.theme.scrollbar, pygame.Rect(tr.right - 8, sy, 6, sh), border_radius=3)
