"""System Monitor app for Lion-OS — live CPU/RAM/disk graphs."""

from __future__ import annotations

import os
from collections import deque

import pygame

from .base import App
from ..widgets import cached_font, rounded_rect

try:
    import psutil
    HAVE_PSUTIL = True
except Exception:
    HAVE_PSUTIL = False


class SystemMonitorApp(App):
    name = "System Monitor"
    icon = "📊"
    description = "Live system performance"
    category = "System"
    default_w = 700
    default_h = 520
    resizable = True

    def __init__(self, os, window=None):
        super().__init__(os, window)
        self.history_cpu = deque(maxlen=120)
        self.history_ram = deque(maxlen=120)
        self.timer = 0.0
        self.cpu = 0.0
        self.ram = 0.0
        self.disk = 0.0
        self.net = (0.0, 0.0)
        self._last_net = None
        self.scroll = 0
        self._fill_cache = {}

    def on_resize(self, rect):
        self.rect = rect

    def update(self, dt):
        self.timer += dt
        if self.timer < 0.5:
            return
        self.timer = 0.0
        if HAVE_PSUTIL:
            try:
                self.cpu = psutil.cpu_percent(interval=None)
                self.ram = psutil.virtual_memory().percent
                self.disk = psutil.disk_usage(os.path.abspath(os.sep)).percent
                nio = psutil.net_io_counters()
                if self._last_net:
                    d = (nio.bytes_sent - self._last_net[0],
                         nio.bytes_recv - self._last_net[1])
                    self.net = (d[0] / 0.5, d[1] / 0.5)
                self._last_net = (nio.bytes_sent, nio.bytes_recv)
            except Exception:
                pass
        else:
            self.cpu = (self.cpu * 7 + 12) / 8
            self.ram = 40
            self.disk = 55
        self.history_cpu.append(self.cpu)
        self.history_ram.append(self.ram)

    def handle_event(self, event, local_pos):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            self.scroll = max(0, min(100, self.scroll + (-20 if event.button == 4 else 20)))
            return True
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(100, self.scroll - event.y * 20))
            return True
        return False

    def _graph(self, rect, history, color, label, value):
        rounded_rect(self.surface, rect, 10, self.theme.surface_alt)
        font = cached_font(self.os.config.font_size)
        small = cached_font(14)
        l = font.render(label, True, self.theme.text)
        self.surface.blit(l, (rect.x + 14, rect.y + 10))
        v = font.render(f"{value:.0f}%", True, color)
        self.surface.blit(v, (rect.right - v.get_width() - 14, rect.y + 10))
        # sparkline
        if len(history) > 1:
            gx = rect.x + 14
            gy = rect.y + 44
            gw = rect.width - 28
            gh = rect.height - 60
            pts = []
            n = len(history)
            for i, val in enumerate(history):
                x = gx + i * gw / max(1, n - 1)
                y = gy + gh - val / 100 * gh
                pts.append((x, y))
            if len(pts) > 1:
                pygame.draw.lines(self.surface, color, False, pts, 2)
                # area fill (reuse a size-keyed surface, not a fresh one)
                fill = self._fill_cache.get((gw, gh))
                if fill is None:
                    fill = pygame.Surface((int(gw), int(gh)), pygame.SRCALPHA)
                    self._fill_cache[(gw, gh)] = fill
                fill.fill((0, 0, 0, 0))
                for i in range(1, len(pts)):
                    pygame.draw.line(fill, color + (60,), (pts[i - 1][0] - gx, pts[i - 1][1] - gy),
                                     (pts[i][0] - gx, pts[i][1] - gy), 2)
                self.surface.blit(fill, (gx, gy))

    def _fmt_net(self, bps):
        if bps >= 1024 ** 3:
            return f"{bps / 1024 ** 3:.1f} GB/s"
        if bps >= 1024 ** 2:
            return f"{bps / 1024 ** 2:.1f} MB/s"
        return f"{bps / 1024:.0f} KB/s"

    def draw(self, surface, rect):
        self.rect = rect
        self.surface = surface
        font = cached_font(self.os.config.font_size)
        small = cached_font(14)

        info = []
        if HAVE_PSUTIL:
            try:
                vm = psutil.virtual_memory()
                du = psutil.disk_usage(os.path.abspath(os.sep))
                info = [
                    (f"CPU cores: {psutil.cpu_count(logical=True)}",
                     f"RAM: {vm.used / 1024 ** 3:.1f} / {vm.total / 1024 ** 3:.1f} GB"),
                    (f"Disk: {du.free / 1024 ** 3:.1f} GB free",
                     f"Load: {os.getloadavg() if hasattr(os, 'getloadavg') else 'n/a'}"),
                ]
            except Exception:
                pass
        y = rect.y + 12 + self.scroll
        for label, val in info:
            limg = small.render(label, True, self.theme.text_dim)
            surface.blit(limg, (rect.x + 14, y))
            vimg = small.render(val, True, self.theme.text_dim)
            surface.blit(vimg, (rect.right - vimg.get_width() - 14, y))
            y += 22

        g1 = pygame.Rect(rect.x + 12, rect.y + 12 + 50 + self.scroll, rect.width - 24, 130)
        g2 = pygame.Rect(rect.x + 12, rect.y + 12 + 190 + self.scroll, rect.width - 24, 130)
        self._graph(g1, self.history_cpu, self.theme.accent, "CPU Usage", self.cpu)
        self._graph(g2, self.history_ram, self.theme.info, "Memory Usage", self.ram)

        # disk + net row
        d3 = pygame.Rect(rect.x + 12, rect.y + 12 + 330 + self.scroll, (rect.width - 36) // 2, 90)
        d4 = pygame.Rect(rect.x + 12 + (rect.width - 24) // 2 + 12, rect.y + 12 + 330 + self.scroll,
                         (rect.width - 36) // 2, 90)
        rounded_rect(surface, d3, 10, self.theme.surface_alt)
        rounded_rect(surface, d4, 10, self.theme.surface_alt)
        dl = font.render(f"Disk {self.disk:.0f}%", True, self.theme.text)
        surface.blit(dl, (d3.x + 14, d3.y + 12))
        pygame.draw.rect(surface, self.theme.surface, (d3.x + 14, d3.y + 44, d3.width - 28, 10), border_radius=5)
        pygame.draw.rect(surface, self.theme.success, (d3.x + 14, d3.y + 44, int((d3.width - 28) * self.disk / 100), 10), border_radius=5)
        nl = font.render("Network", True, self.theme.text)
        surface.blit(nl, (d4.x + 14, d4.y + 12))
        down = small.render(f"↓ {self._fmt_net(self.net[1])}", True, self.theme.success)
        up = small.render(f"↑ {self._fmt_net(self.net[0])}", True, self.theme.info)
        surface.blit(down, (d4.x + 14, d4.y + 42))
        surface.blit(up, (d4.x + 14, d4.y + 62))
