"""Paint app for Lion-OS — drawing canvas."""

from __future__ import annotations

import os

import pygame

from .base import App
from ..widgets import Button, cached_font, rounded_rect

COLOR_PALETTE = [
    (0, 0, 0), (90, 90, 100), (150, 150, 160), (240, 240, 245),
    (220, 60, 60), (240, 150, 40), (250, 210, 60), (80, 200, 90),
    (60, 180, 220), (80, 110, 240), (150, 70, 220), (240, 110, 190),
    (255, 255, 255), (180, 130, 80),
]

TOOLS = ["✏", "▦", "○", "━", "◻", "🎨"]


class PaintApp(App):
    name = "Paint"
    icon = "🎨"
    description = "Draw and paint"
    category = "Utilities"
    default_w = 760
    default_h = 540
    resizable = True

    def __init__(self, os, window=None):
        super().__init__(os, window)
        self.color = (220, 60, 60)
        self.tool = "✏"         # pencil | brush | eraser | line | rect | fill
        self.size = 4
        self.drawing = False
        self._last_pos = None
        self._start_pos = None
        self.canvas = None
        self.canvas_size = (1000, 700)
        self.canvas_offset = (0, 0)
        self._history = []
        self._history_idx = -1
        self._push_history()
        self.path = None
        self._init_canvas()

    def _init_canvas(self):
        if self.canvas is None:
            self.canvas = pygame.Surface(self.canvas_size, pygame.SRCALPHA)
            self.canvas.fill((255, 255, 255))

    def _push_history(self):
        if self.canvas is None:
            return
        snap = self.canvas.copy()
        self._history = self._history[:self._history_idx + 1]
        self._history.append(snap)
        self._history_idx += 1
        if len(self._history) > 30:
            self._history.pop(0)
            self._history_idx -= 1

    def _canvas_rect(self):
        return pygame.Rect(self.rect.x + 12, self.rect.y + 50,
                           self.rect.width - 24, self.rect.height - 66)

    def _tool_rect(self):
        return pygame.Rect(self.rect.x + 12, self.rect.y + 10, self.rect.width - 24, 32)

    def _to_canvas(self, pos):
        cr = self._canvas_rect()
        return (pos[0] - cr.x, pos[1] - cr.y)

    def handle_event(self, event, local_pos):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_z and event.mod & pygame.KMOD_CTRL:
                self._undo()
                return True
            if event.key == pygame.K_y and event.mod & pygame.KMOD_CTRL:
                self._redo()
                return True
            if event.key == pygame.K_s and event.mod & pygame.KMOD_CTRL:
                self._save()
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            tr = self._tool_rect()
            if tr.collidepoint(local_pos):
                # tool select
                for i, t in enumerate(TOOLS):
                    r = pygame.Rect(tr.x + i * 46, tr.y, 44, tr.height)
                    if r.collidepoint(local_pos):
                        self.tool = t
                        return True
                # color select row 1
                for i, c in enumerate(COLOR_PALETTE[:7]):
                    r = pygame.Rect(tr.x + 6 * 46 + i * 26, tr.y + 2, 22, 13)
                    if r.collidepoint(local_pos):
                        self.color = c
                        return True
                # color select row 2
                for i, c in enumerate(COLOR_PALETTE[7:]):
                    r = pygame.Rect(tr.x + 6 * 46 + i * 26, tr.y + 17, 22, 13)
                    if r.collidepoint(local_pos):
                        self.color = c
                        return True
                return True
            cr = self._canvas_rect()
            if cr.collidepoint(local_pos):
                self.drawing = True
                self._last_pos = self._to_canvas(local_pos)
                self._start_pos = self._to_canvas(local_pos)
                if self.tool == "🎨":
                    self._fill(self._last_pos)
                    self._push_history()
                    self.drawing = False
                return True
        if event.type == pygame.MOUSEMOTION and self.drawing:
            pos = self._to_canvas(local_pos)
            cr = self._canvas_rect()
            if self._canvas_rect().collidepoint(local_pos):
                self._stroke(self._last_pos, pos)
                self._last_pos = pos
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.drawing:
                if self.tool in ("▦", "○", "━", "◻") and self._start_pos:
                    self._stroke_shape(self._start_pos, self._last_pos)
                self.drawing = False
                self._last_pos = None
                self._start_pos = None
                self._push_history()
            return True
        return False

    def _stroke(self, a, b):
        if self.tool == "✏":
            if a and b:
                pygame.draw.line(self.canvas, self.color, a, b, self.size)
                pygame.draw.circle(self.canvas, self.color, b, self.size // 2)
        elif self.tool == "▦":
            if a and b:
                pygame.draw.line(self.canvas, self.color, a, b, self.size * 2)
        elif self.tool == "○":
            if a and b:
                pygame.draw.line(self.canvas, self.color, a, b, self.size)
        elif self.tool == "━":
            if a and b:
                pygame.draw.line(self.canvas, self.color, a, b, self.size)
        elif self.tool == "◻":
            if a and b:
                pygame.draw.line(self.canvas, self.color, a, b, self.size)
        elif self.tool == "🎨":
            pass

    def _stroke_shape(self, a, b):
        if self.tool == "▦":
            w = max(2, b[0] - a[0])
            h = max(2, b[1] - a[1])
            pygame.draw.rect(self.canvas, self.color, (a[0], a[1], w, h), self.size)
        elif self.tool == "○":
            r = int(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5)
            pygame.draw.circle(self.canvas, self.color, a, max(2, r), self.size)
        elif self.tool == "━":
            pygame.draw.line(self.canvas, self.color, a, b, self.size)
        elif self.tool == "◻":
            pygame.draw.rect(self.canvas, self.color, pygame.Rect(a, (b[0] - a[0], b[1] - a[1])).normalize(), self.size)

    def _fill(self, pos):
        w, h = self.canvas.get_size()
        x, y = int(pos[0]), int(pos[1])
        if not (0 <= x < w and 0 <= y < h):
            return
        target = self.canvas.get_at((x, y))[:3]
        if target == self.color:
            return
        visited = set()
        stack = [(x, y)]
        while stack and len(visited) < 200000:
            cx, cy = stack.pop()
            if (cx, cy) in visited or not (0 <= cx < w and 0 <= cy < h):
                continue
            if self.canvas.get_at((cx, cy))[:3] != target:
                continue
            visited.add((cx, cy))
            self.canvas.set_at((cx, cy), self.color)
            stack.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])

    def _undo(self):
        if self._history_idx > 0:
            self._history_idx -= 1
            self.canvas = self._history[self._history_idx].copy()

    def _redo(self):
        if self._history_idx < len(self._history) - 1:
            self._history_idx += 1
            self.canvas = self._history[self._history_idx].copy()

    def _save(self):
        try:
            path = os.path.join(os.path.expanduser("~"), "lion-art.png")
            pygame.image.save(self.canvas, path)
            self.show_toast("Paint", f"Saved to {path}", "success")
        except Exception as e:
            self.show_toast("Paint", f"Save failed: {e}", "error")

    def draw(self, surface, rect):
        self.rect = rect
        font = cached_font(self.os.config.font_size)
        small = cached_font(14)
        # toolbar
        tr = self._tool_rect()
        rounded_rect(surface, tr, 8, self.theme.surface_alt)
        for i, t in enumerate(TOOLS):
            r = pygame.Rect(tr.x + i * 46, tr.y, 44, tr.height)
            if t == self.tool:
                rounded_rect(surface, r, 6, self.theme.selection[:3] if len(self.theme.selection) == 3 else self.theme.selection)
            elif r.collidepoint(pygame.mouse.get_pos()):
                rounded_rect(surface, r, 6, self.theme.hover[:3] if len(self.theme.hover) == 3 else self.theme.hover)
            img = font.render(t, True, self.theme.text)
            surface.blit(img, img.get_rect(center=r.center))
        # color swatches
        for i, c in enumerate(COLOR_PALETTE[:7]):
            r = pygame.Rect(tr.x + 6 * 46 + i * 26, tr.y + 2, 22, 13)
            pygame.draw.rect(surface, c, r, border_radius=3)
            if c == self.color:
                pygame.draw.rect(surface, self.theme.accent, r, 2, border_radius=3)
        for i, c in enumerate(COLOR_PALETTE[7:]):
            r = pygame.Rect(tr.x + 6 * 46 + i * 26, tr.y + 17, 22, 13)
            pygame.draw.rect(surface, c, r, border_radius=3)
            if c == self.color:
                pygame.draw.rect(surface, self.theme.accent, r, 2, border_radius=3)
        # brush size hint
        s_img = small.render(f"Size {self.size}", True, self.theme.text_dim)
        surface.blit(s_img, (tr.right - s_img.get_width() - 8, tr.y + 4))

        # canvas
        cr = self._canvas_rect()
        rounded_rect(surface, cr, 4, self.theme.surface)
        if self.canvas:
            scaled = pygame.transform.scale(self.canvas, (cr.width, cr.height))
            surface.blit(scaled, cr.topleft)
            # checkerboard for transparency is hidden under white canvas
        pygame.draw.rect(surface, self.theme.glass_border[:3] if len(self.theme.glass_border) == 4 else self.theme.glass_border, cr, 1, border_radius=4)
