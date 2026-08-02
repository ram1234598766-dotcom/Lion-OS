"""Inbox — quick-capture with To Do / Someday / Ideas triage."""
from __future__ import annotations

import json
import os

import pygame

from .base import App
from ..widgets import draw_glass_panel, cached_font


class InboxApp(App):
    name = "Inbox"
    icon = "Inbox"
    category = "Utilities"
    description = "Quick-capture: To Do / Someday / Ideas, promote to task"
    default_w = 640
    default_h = 480
    resizable = True
    min_w = 400
    min_h = 300

    def on_open(self):
        self._items = self._load()
        self._entry = ""

    def _path(self):
        from ..config import config_dir
        return os.path.join(config_dir(), "inbox.json")

    def _load(self):
        try:
            with open(self._path(), "r", encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, list) else []
        except Exception:
            return []

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._path()), exist_ok=True)
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump(self._items, f, indent=2)
        except Exception:
            pass

    def handle_event(self, event, local_pos):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self._entry:
                self._items.insert(0, {"text": self._entry, "section": "To Do"})
                self._entry = ""
                self._save()
                return True
            if event.key == pygame.K_BACKSPACE:
                self._entry = self._entry[:-1]
                return True
        if event.type == pygame.TEXTINPUT:
            self._entry += event.text
            return True
        if event.type == pygame.KEYDOWN and getattr(event, "unicode", "") and event.unicode.isprintable():
            self._entry += event.unicode
            return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            y = 90
            for item in self._items:
                r = pygame.Rect(12, y, self.rect.width - 24, 34)
                if r.collidepoint(local_pos) and item["section"] != "To Do":
                    item["section"] = "To Do"
                    self._save()
                    return True
                y += 38
        return False

    def draw(self, surface, rect):
        theme = self.theme
        draw_glass_panel(surface, rect, theme, radius=theme.radius)
        title = cached_font(18).render("Inbox", True, theme.text)
        surface.blit(title, (16, 12))
        box = pygame.Rect(12, 46, rect.width - 24, 34)
        pygame.draw.rect(surface, theme.surface, box, border_radius=8)
        pygame.draw.rect(surface, theme.accent, box, 1, border_radius=8)
        t = cached_font(16).render(self._entry or "Quick capture — Enter to add…",
                                   True, theme.text if self._entry else theme.text_dim)
        surface.blit(t, (box.x + 10, box.centery - t.get_height() // 2))
        y = 90
        for item in self._items:
            col = theme.accent if item["section"] == "To Do" else theme.text_dim
            r = pygame.Rect(12, y, rect.width - 24, 34)
            pygame.draw.rect(surface, theme.surface_alt, r, border_radius=8)
            sec = cached_font(13).render(item["section"], True, col)
            surface.blit(sec, (r.x + 8, r.y + 8))
            txt = cached_font(15).render(item["text"], True, theme.text)
            surface.blit(txt, (r.x + 110, r.y + 8))
            y += 38
