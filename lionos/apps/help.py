"""Help app — a searchable catalog of every built-in app."""
from __future__ import annotations

import pygame

from .base import App
from ..widgets import draw_glass_panel, cached_font


class HelpApp(App):
    name = "Help"
    icon = "Help"
    category = "System"
    description = "Self-documenting catalog of every app"
    default_w = 780
    default_h = 520
    resizable = True
    min_w = 480
    min_h = 320

    def on_open(self):
        self._search = ""

    def _rows(self):
        from ..apps import get_apps
        rows = []
        for cls in get_apps():
            if self._search and self._search.lower() not in cls.name.lower():
                continue
            rows.append((cls.name, cls.description or "", cls.category))
        return rows

    def handle_event(self, event, local_pos):
        if event.type == pygame.TEXTINPUT:
            self._search += event.text
            return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_BACKSPACE:
            self._search = self._search[:-1]
            return True
        return False

    def draw(self, surface, rect):
        theme = self.theme
        draw_glass_panel(surface, rect, theme, radius=theme.radius)
        font = cached_font(18)
        title = font.render("Help & App Catalog", True, theme.text)
        surface.blit(title, (18, 14))
        search = cached_font(15).render(f"Search: {self._search or '…'}", True, theme.text_dim)
        surface.blit(search, (18, 46))
        y = 78
        for name, desc, cat in self._rows():
            r = pygame.Rect(14, y, rect.width - 28, 40)
            pygame.draw.rect(surface, theme.surface_alt, r, border_radius=6)
            n = cached_font(16).render(name, True, theme.text)
            surface.blit(n, (r.x + 12, r.y + 6))
            c = cached_font(13).render(cat, True, theme.text_dim)
            surface.blit(c, (r.x + 12 + n.get_width() + 10, r.y + 8))
            d = cached_font(13).render(desc or "…", True, theme.text_dim)
            surface.blit(d, (r.x + 12, r.y + 24))
            y += 46
