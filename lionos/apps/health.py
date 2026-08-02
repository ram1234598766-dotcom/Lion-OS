"""System Health — scored audit of the install."""
from __future__ import annotations

import pygame

from .base import App
from ..widgets import draw_glass_panel, cached_font


class SystemHealthApp(App):
    name = "System Health"
    icon = "System Health"
    category = "System"
    description = "Scored audit: apps, themes, drivers, profile"
    default_w = 640
    default_h = 480
    resizable = True
    min_w = 400
    min_h = 300

    def _score(self):
        from ..apps import get_apps
        from ..theme import THEMES
        apps = len(get_apps())
        themes = len(THEMES)
        drivers = sum(1 for d in self.os.drivers.all() if d.status.running)
        profile_done = self.os.config.wizard_done
        s = min(40, apps * 2) + min(20, themes * 2) + min(30, drivers)
        s += 10 if profile_done else 0
        return min(100, s)

    def draw(self, surface, rect):
        theme = self.theme
        draw_glass_panel(surface, rect, theme, radius=theme.radius)
        score = self._score()
        title = cached_font(20).render("System Health", True, theme.text)
        surface.blit(title, (16, 12))
        color = theme.success if score >= 70 else (theme.warn if score >= 40 else theme.danger)
        n = cached_font(64).render(f"{score}", True, color)
        surface.blit(n, n.get_rect(center=(rect.centerx - 30, rect.y + 90)))
        pct = cached_font(18).render("/ 100", True, theme.text_dim)
        surface.blit(pct, pct.get_rect(midleft=(rect.centerx + 40, rect.y + 90)))
        tips = ["Open more apps", "Switch themes", "Enable drivers", "Complete setup"]
        y = rect.y + 150
        for tip in tips:
            t = cached_font(16).render("• " + tip, True, theme.text_dim)
            surface.blit(t, (24, y))
            y += 28
