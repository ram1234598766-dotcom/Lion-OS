"""Theme system for Lion-OS — dark/light glassmorphism palettes."""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Theme:
    name: str
    is_dark: bool
    bg: tuple
    bg_alt: tuple
    surface: tuple
    surface_alt: tuple
    glass: tuple            # translucent surface color
    glass_border: tuple
    text: tuple
    text_dim: tuple
    accent: tuple
    accent_alt: tuple
    danger: tuple
    success: tuple
    warn: tuple
    info: tuple
    taskbar: tuple
    taskbar_active: tuple
    hover: tuple
    active: tuple
    scrollbar: tuple
    shadow: tuple
    selection: tuple
    wallpaper_top: tuple
    wallpaper_bottom: tuple
    icon_bg: tuple

    @property
    def wallpaper(self) -> "List[tuple]":
        return [self.wallpaper_top, self.wallpaper_bottom]


DARK = Theme(
    name="Dark",
    is_dark=True,
    bg=(18, 18, 24),
    bg_alt=(24, 24, 32),
    surface=(30, 30, 40),
    surface_alt=(40, 40, 52),
    glass=(28, 28, 38, 210),
    glass_border=(255, 255, 255, 30),
    text=(232, 232, 240),
    text_dim=(150, 150, 165),
    accent=(247, 148, 0),           # lion gold
    accent_alt=(255, 183, 77),
    danger=(231, 76, 60),
    success=(46, 204, 113),
    warn=(241, 196, 15),
    info=(52, 152, 219),
    taskbar=(20, 20, 28, 235),
    taskbar_active=(247, 148, 0),
    hover=(255, 255, 255, 18),
    active=(255, 255, 255, 30),
    scrollbar=(90, 90, 105),
    shadow=(0, 0, 0, 140),
    selection=(247, 148, 0, 90),
    wallpaper_top=(24, 16, 48),
    wallpaper_bottom=(10, 10, 20),
    icon_bg=(247, 148, 0),
)

LIGHT = Theme(
    name="Light",
    is_dark=False,
    bg=(236, 238, 245),
    bg_alt=(226, 228, 238),
    surface=(255, 255, 255),
    surface_alt=(240, 241, 247),
    glass=(245, 246, 252, 225),
    glass_border=(255, 255, 255, 120),
    text=(28, 30, 42),
    text_dim=(110, 115, 132),
    accent=(224, 122, 0),
    accent_alt=(247, 148, 0),
    danger=(198, 40, 40),
    success=(39, 174, 96),
    warn=(212, 172, 13),
    info=(41, 128, 185),
    taskbar=(250, 250, 252, 240),
    taskbar_active=(224, 122, 0),
    hover=(20, 20, 30, 14),
    active=(20, 20, 30, 24),
    scrollbar=(180, 182, 195),
    shadow=(20, 20, 30, 60),
    selection=(247, 148, 0, 70),
    wallpaper_top=(226, 214, 235),
    wallpaper_bottom=(190, 198, 220),
    icon_bg=(224, 122, 0),
)

OCEAN = Theme(
    name="Ocean",
    is_dark=True,
    bg=(10, 22, 34),
    bg_alt=(16, 30, 44),
    surface=(22, 40, 58),
    surface_alt=(30, 52, 74),
    glass=(20, 38, 56, 215),
    glass_border=(120, 200, 255, 40),
    text=(225, 238, 248),
    text_dim=(140, 160, 178),
    accent=(0, 190, 255),
    accent_alt=(90, 214, 255),
    danger=(255, 92, 92),
    success=(64, 222, 156),
    warn=(255, 200, 87),
    info=(64, 156, 255),
    taskbar=(12, 26, 40, 235),
    taskbar_active=(0, 190, 255),
    hover=(255, 255, 255, 18),
    active=(255, 255, 255, 30),
    scrollbar=(50, 80, 105),
    shadow=(0, 0, 0, 140),
    selection=(0, 190, 255, 70),
    wallpaper_top=(8, 44, 70),
    wallpaper_bottom=(6, 14, 26),
    icon_bg=(0, 190, 255),
)

FOREST = Theme(
    name="Forest",
    is_dark=True,
    bg=(16, 26, 18),
    bg_alt=(22, 34, 24),
    surface=(28, 42, 30),
    surface_alt=(38, 56, 40),
    glass=(26, 40, 28, 215),
    glass_border=(140, 220, 150, 36),
    text=(230, 240, 230),
    text_dim=(145, 165, 148),
    accent=(64, 200, 96),
    accent_alt=(120, 230, 140),
    danger=(255, 100, 100),
    success=(64, 222, 120),
    warn=(240, 210, 90),
    info=(90, 170, 230),
    taskbar=(16, 28, 20, 235),
    taskbar_active=(64, 200, 96),
    hover=(255, 255, 255, 18),
    active=(255, 255, 255, 30),
    scrollbar=(70, 100, 78),
    shadow=(0, 0, 0, 140),
    selection=(64, 200, 96, 70),
    wallpaper_top=(26, 56, 34),
    wallpaper_bottom=(10, 18, 12),
    icon_bg=(64, 200, 96),
)

VIOLET = Theme(
    name="Violet",
    is_dark=True,
    bg=(24, 18, 40),
    bg_alt=(32, 24, 52),
    surface=(40, 32, 64),
    surface_alt=(52, 42, 80),
    glass=(38, 30, 62, 218),
    glass_border=(200, 170, 255, 40),
    text=(238, 232, 252),
    text_dim=(160, 150, 188),
    accent=(167, 94, 255),
    accent_alt=(200, 150, 255),
    danger=(255, 100, 130),
    success=(90, 222, 150),
    warn=(250, 210, 100),
    info=(110, 160, 255),
    taskbar=(26, 20, 44, 235),
    taskbar_active=(167, 94, 255),
    hover=(255, 255, 255, 18),
    active=(255, 255, 255, 30),
    scrollbar=(90, 80, 120),
    shadow=(0, 0, 0, 150),
    selection=(167, 94, 255, 70),
    wallpaper_top=(50, 24, 88),
    wallpaper_bottom=(18, 12, 32),
    icon_bg=(167, 94, 255),
)

ROSE = Theme(
    name="Rose",
    is_dark=False,
    bg=(250, 240, 244),
    bg_alt=(244, 232, 238),
    surface=(255, 250, 252),
    surface_alt=(248, 238, 243),
    glass=(252, 246, 250, 230),
    glass_border=(255, 255, 255, 140),
    text=(58, 40, 50),
    text_dim=(150, 120, 135),
    accent=(236, 72, 138),
    accent_alt=(244, 114, 182),
    danger=(220, 60, 80),
    success=(40, 190, 120),
    warn=(216, 170, 40),
    info=(70, 140, 220),
    taskbar=(252, 248, 250, 242),
    taskbar_active=(236, 72, 138),
    hover=(20, 10, 16, 12),
    active=(20, 10, 16, 22),
    scrollbar=(214, 190, 200),
    shadow=(60, 20, 40, 60),
    selection=(236, 72, 138, 60),
    wallpaper_top=(255, 226, 240),
    wallpaper_bottom=(238, 214, 228),
    icon_bg=(236, 72, 138),
)

THEMES: Dict[str, Theme] = {
    "dark": DARK,
    "light": LIGHT,
    "ocean": OCEAN,
    "forest": FOREST,
    "violet": VIOLET,
    "rose": ROSE,
}

THEME_NAMES = list(THEMES.keys())


def blend(c1: tuple, c2: tuple, t: float) -> tuple:
    """Linearly interpolate two RGBA/RGB colors."""
    t = max(0.0, min(1.0, t))
    return tuple(int(a + (b - a) * t) for a, b in zip(c1[:3], c2[:3])) + (c1[3:] and c1[3] or c2[3:])
