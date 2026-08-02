"""Graphics/display library drivers."""
from ..framework import Driver


class DisplaySwitcher(Driver):
    name = "display_switch"
    category = "graphics"
    simulated = True
    description = "Multi-monitor / split-screen management"
    config_defaults = {"screens": 1}
    def probe(self):
        return True


class RefreshController(Driver):
    name = "refresh"
    category = "graphics"
    description = "FPS governor to prevent flicker"
    config_defaults = {"fps": 60}
    def probe(self):
        return True
    def clamp(self, fps):
        return max(1, min(144, int(fps)))


class AsciiRasterizer(Driver):
    name = "ascii"
    category = "graphics"
    description = "Fonts to ASCII-art"
    def probe(self):
        return True
    def render(self, text):
        return text


class UiScaling(Driver):
    name = "ui_scaling"
    category = "graphics"
    simulated = True
    description = "Auto reflow on resize"
    def probe(self):
        return True


class EinkDisplay(Driver):
    name = "eink"
    category = "graphics"
    simulated = True
    description = "Slow/partial redraw emulation"
    def probe(self):
        return True


class Haptics(Driver):
    name = "haptics"
    category = "graphics"
    simulated = True
    description = "Notifications to rumble commands"
    def probe(self):
        return True


class Oscilloscope(Driver):
    name = "oscilloscope"
    category = "graphics"
    simulated = True
    description = "Driver signals to wave graphs"
    def probe(self):
        return True
