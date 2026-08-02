"""Display driver — video-driver selection, mode, vsync info."""
from __future__ import annotations

import pygame

from ..framework import Driver


class DisplayDriver(Driver):
    name = "display"
    category = "core"
    description = "Video output (windowed/fullscreen, vsync)"

    def probe(self) -> bool:
        try:
            if not pygame.display.get_init():
                pygame.display.init()
            self._driver = pygame.display.get_driver()
            info = pygame.display.Info()
            self._res = (info.current_w, info.current_h)
        except pygame.error:
            self._set(available=False, detail="no display")
            return False
        return True

    def auto_tune(self) -> dict:
        return {"vsync": False, "fullscreen": False}

    def diagnose(self) -> str:
        return f"{self._driver} @ {self._res}"
