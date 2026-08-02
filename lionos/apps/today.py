"""Today — the activity log as a timeline view."""
from __future__ import annotations

import pygame

from .base import App
from ..widgets import draw_glass_panel, cached_font


class TodayApp(App):
    name = "Today"
    icon = "Today"
    category = "Utilities"
    description = "Your activity timeline"
    default_w = 640
    default_h = 480
    resizable = True
    min_w = 400
    min_h = 300

    def draw(self, surface, rect):
        from .. import activity
        theme = self.theme
        draw_glass_panel(surface, rect, theme, radius=theme.radius)
        title = cached_font(20).render("Today / Timeline", True, theme.text)
        surface.blit(title, (16, 12))
        y = 50
        for ev in activity.read_events(limit=40):
            t = cached_font(15).render(f"{ev.get('type', '?')}: {ev.get('detail', '')}",
                                       True, theme.text)
            surface.blit(t, (20, y))
            y += 22
            if y > rect.bottom - 10:
                break
