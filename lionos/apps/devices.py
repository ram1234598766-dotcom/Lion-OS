"""Devices & Drivers app — renders the driver device tree with controls."""
from __future__ import annotations

import pygame

from .base import App
from ..widgets import draw_glass_panel, cached_font


class DevicesApp(App):
    name = "Devices"
    icon = "Devices"
    category = "System"
    description = "Driver bus device tree, status, enable/disable, re-probe"
    default_w = 860
    default_h = 560
    resizable = True
    min_w = 560
    min_h = 360

    def on_open(self):
        self._search = ""
        self._msg = ""

    def _rows(self):
        tree = self.os.drivers.device_tree()
        rows = []
        for group in tree:
            for drv in group["drivers"]:
                name = drv["name"].lower()
                if self._search and self._search.lower() not in name:
                    continue
                rows.append((group["category"], drv))
        return rows

    def handle_event(self, event, local_pos):
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_BACKSPACE, pygame.K_RETURN):
            if event.key == pygame.K_BACKSPACE:
                self._search = self._search[:-1]
            return True
        if event.type == pygame.TEXTINPUT:
            self._search += event.text
            return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            self._click(local_pos)
            return True
        return False

    def _click(self, pos):
        y = 64
        row_h = 34
        for _cat, drv in self._rows():
            r = pygame.Rect(12, y, self.rect.width - 24, row_h)
            if r.collidepoint(pos):
                name = drv["name"]
                if pos[0] > r.right - 130:
                    if drv["status"]["enabled"]:
                        self.os.drivers.disable(name)
                        self._msg = f"{name}: disabled"
                    else:
                        self.os.drivers.enable(name)
                        self._msg = f"{name}: enabled"
                    self.redraw()
                elif pos[0] > r.right - 230:
                    line = self.os.drivers.re_probe(name)
                    self._msg = f"{name}: {line.state} ({line.detail})"
                    self.redraw()
            y += row_h

    def draw(self, surface, rect):
        self.rect = rect
        theme = self.theme
        draw_glass_panel(surface, rect, theme, radius=theme.radius)
        font = cached_font(16)
        title = font.render("Devices & Drivers", True, theme.text)
        surface.blit(title, (18, 16))
        search = font.render(f"Search: {self._search or '…'}", True, theme.text_dim)
        surface.blit(search, (18, 44))
        y = 64
        row_h = 34
        for _cat, drv in self._rows():
            st = drv["status"]
            color = theme.success if st["running"] else (
                theme.warn if not st["enabled"] else theme.danger)
            row = pygame.Rect(12, y, rect.width - 24, row_h)
            pygame.draw.rect(surface, theme.surface_alt, row, border_radius=6)
            badge = pygame.Rect(row.x + 8, row.y + 8, 14, 14)
            pygame.draw.circle(surface, color, badge.center, 6)
            nm = font.render(drv["name"], True, theme.text)
            surface.blit(nm, (row.x + 30, row.y + 8))
            det = cached_font(13).render(st["detail"] or "", True, theme.text_dim)
            surface.blit(det, (row.x + 30 + nm.get_width() + 12, row.y + 10))
            sim = cached_font(12).render("[sim]" if drv["simulated"] else "", True, theme.text_dim)
            surface.blit(sim, (row.x + 30 + nm.get_width() + 12 + det.get_width() + 8, row.y + 10))
            rp = cached_font(13).render("Re-probe", True, theme.accent)
            surface.blit(rp, (row.right - 210, row.y + 9))
            togg = cached_font(13).render(
                "Enable" if not st["enabled"] else "Disable", True, theme.accent)
            surface.blit(togg, (row.right - 120, row.y + 9))
            y += row_h
        if self._msg:
            m = cached_font(13).render(self._msg, True, theme.info)
            surface.blit(m, (18, rect.bottom - 24))
