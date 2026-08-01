"""About app for Lion-OS."""

from __future__ import annotations

import platform

import pygame

from .base import App
from .. import APP_NAME, VERSION, __codename__, __build__
from ..widgets import rounded_rect


class AboutApp(App):
    name = "About"
    icon = "ℹ"
    description = "About Lion-OS"
    category = "System"
    default_w = 480
    default_h = 380
    resizable = False

    def __init__(self, os, window=None):
        super().__init__(os, window)

    def handle_event(self, event, local_pos):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # check buttons
            close = pygame.Rect(self.rect.x + self.rect.width - 150, self.rect.y + self.rect.height - 52, 130, 36)
            if close.collidepoint(local_pos):
                self.close()
                return True
        return False

    def draw(self, surface, rect):
        self.rect = rect
        font = pygame.font.Font(None, 26)
        small = pygame.font.Font(None, 16)
        mid = font = pygame.font.Font(None, 34)

        cx = rect.centerx
        y = rect.y + 40
        # lion logo
        pygame.draw.circle(surface, self.theme.accent, (cx, y + 20), 38)
        lg = mid.render("🦁", True, (255, 255, 255))
        surface.blit(lg, lg.get_rect(center=(cx, y + 20)))
        t = mid.render(f"{APP_NAME} {VERSION}", True, self.theme.accent)
        surface.blit(t, t.get_rect(midtop=(cx, y + 66)))
        c = small.render(f"Codename \"{__codename__}\" · Build {__build__}", True, self.theme.text_dim)
        surface.blit(c, c.get_rect(midtop=(cx, y + 100)))

        info = [
            "A graphical desktop operating system that runs",
            "entirely inside Python. Built on Pygame and psutil.",
            "",
            f"Python {platform.python_version()}",
            f"Platform {platform.system()} {platform.release()}",
            f"Machine {platform.machine()}",
        ]
        for i, ln in enumerate(info):
            img = small.render(ln, True, self.theme.text)
            surface.blit(img, img.get_rect(midtop=(cx, y + 130 + i * 20)))

        close = pygame.Rect(rect.x + rect.width - 150, rect.y + rect.height - 52, 130, 36)
        hover = close.collidepoint(pygame.mouse.get_pos())
        rounded_rect(surface, close, 8, self.theme.accent if hover else self.theme.surface_alt)
        cimg = font.render("Close", True, self.theme.text)
        surface.blit(cimg, cimg.get_rect(center=close.center))
