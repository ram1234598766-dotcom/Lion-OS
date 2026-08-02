"""Input driver — keyboard/mouse + optional gamepad."""
from __future__ import annotations

import pygame

from ..framework import Driver


class InputDriver(Driver):
    name = "input"
    category = "core"
    description = "Keyboard / mouse / gamepad"

    def probe(self) -> bool:
        try:
            self._gamepads = pygame.joystick.get_count()
        except pygame.error:
            self._gamepads = 0
        return True

    def auto_tune(self) -> dict:
        return {"gamepad": self._gamepads > 0}

    def diagnose(self) -> str:
        pads = f", {self._gamepads} gamepad(s)" if self._gamepads else ""
        return f"keyboard+mouse{pads}"
