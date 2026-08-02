"""Theme system for Lion-OS — dark/light glassmorphism palettes.

Themes carry the full palette used across the desktop. An extra set of
``titlebar_*`` / ``icon_grad*`` / ``glow`` fields drives the richer chrome
introduced in the identity pass. ``Theme.interpolate`` blends two themes
live so the kernel can animate a theme switch.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Dict, List, Tuple

Color = Tuple[int, int, int]
RGBA = Tuple[int, int, int, int]


@dataclass
class Theme:
    name: str
    is_dark: bool
    bg: Color
    bg_alt: Color
    surface: Color
    surface_alt: Color
    glass: RGBA
    glass_border: RGBA
    text: Color
    text_dim: Color
    accent: Color
    accent_alt: Color
    danger: Color
    success: Color
    warn: Color
    info: Color
    taskbar: RGBA
    taskbar_active: Color
    hover: RGBA
    active: RGBA
    scrollbar: Color
    shadow: RGBA
    selection: RGBA
    wallpaper_top: Color
    wallpaper_bottom: Color
    icon_bg: Color
    # --- identity-pass extras (default to derived values in __post_init__) ---
    titlebar_top: Color = None
    titlebar_bottom: Color = None
    glow: Color = None
    accent2: Color = None
    icon_grad1: Color = None
    icon_grad2: Color = None
    # --- semantic tokens (non-color, skipped by as_dict) ---
    radius: int = 12
    spacing: int = 8
    text_disabled: Color = None

    def __post_init__(self):
        if self.titlebar_top is None:
            self.titlebar_top = self.surface_alt
        if self.titlebar_bottom is None:
            self.titlebar_bottom = self.surface
        if self.glow is None:
            self.glow = self.accent
        if self.accent2 is None:
            self.accent2 = self.accent_alt
        if self.icon_grad1 is None:
            self.icon_grad1 = self.accent
        if self.icon_grad2 is None:
            self.icon_grad2 = self.accent2
        if self.text_disabled is None:
            self.text_disabled = ensure_contrast(self.text_dim, self.surface, 3.0)

    @property
    def wallpaper(self) -> List[Color]:
        return [self.wallpaper_top, self.wallpaper_bottom]

    # -- helpers --------------------------------------------------------------
    def as_dict(self) -> dict:
        """All fields that are plain colors (used for interpolation)."""
        skip = {"name", "is_dark", "radius", "spacing", "text_disabled"}
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name not in skip}

    def interpolate(self, other: "Theme", t: float) -> "Theme":
        """Return a theme blended between self (t=0) and other (t=1)."""
        t = max(0.0, min(1.0, t))
        data = self.as_dict()
        data["is_dark"] = other.is_dark if t >= 0.5 else self.is_dark
        for k, a in data.items():
            if k == "is_dark":
                continue
            b = getattr(other, k)
            if isinstance(a, tuple) and isinstance(b, tuple) and len(a) == len(b):
                data[k] = blend(a, b, t)
        data["name"] = other.name if t >= 0.5 else self.name
        return Theme(**data)


# -- WCAG-AA contrast helpers ---------------------------------------------
def _srgb_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(c):
    """WCAG relative luminance of an RGB color (0.0-1.0)."""
    r, g, b = (_srgb_linear(ch) for ch in c[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(c1, c2):
    """WCAG contrast ratio between two RGB colors (>=1.0)."""
    l1, l2 = relative_luminance(c1), relative_luminance(c2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def ensure_contrast(text, bg, min_ratio=4.5):
    """Lighten (dark themes) or darken (light themes) ``text`` until it reaches
    ``min_ratio`` against ``bg``. Returns the adjusted color."""
    text, bg = tuple(text[:3]), tuple(bg[:3])
    out = list(text)
    lum_bg = relative_luminance(bg)
    for _ in range(30):
        if contrast_ratio(out, bg) >= min_ratio:
            break
        if lum_bg > 0.5:
            out = [max(0, int(v * 0.86)) for v in out]       # light bg -> darken
        else:
            out = [min(255, int(v + (255 - v) * 0.5)) for v in out]  # dark bg -> lighten
    return tuple(out)


def theme_contrast_report(t):
    """Body text contrast vs the main surfaces of a theme."""
    text = tuple(t.text[:3])
    return {
        "surface": contrast_ratio(text, tuple(t.surface[:3])),
        "wallpaper": contrast_ratio(text, tuple(t.wallpaper_top[:3])),
    }


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
    titlebar_top=(44, 40, 58),
    titlebar_bottom=(28, 28, 38),
    glow=(247, 148, 0),
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
    titlebar_top=(250, 250, 253),
    titlebar_bottom=(240, 241, 247),
    glow=(224, 122, 0),
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
    titlebar_top=(26, 70, 100),
    titlebar_bottom=(18, 36, 54),
    glow=(0, 190, 255),
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
    titlebar_top=(46, 84, 52),
    titlebar_bottom=(26, 40, 28),
    glow=(64, 200, 96),
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
    titlebar_top=(72, 48, 116),
    titlebar_bottom=(38, 30, 60),
    glow=(167, 94, 255),
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
    titlebar_top=(255, 240, 246),
    titlebar_bottom=(248, 236, 242),
    glow=(236, 72, 138),
)

SUNSET = Theme(
    name="Sunset",
    is_dark=True,
    bg=(30, 14, 24),
    bg_alt=(40, 20, 32),
    surface=(52, 26, 40),
    surface_alt=(70, 36, 54),
    glass=(56, 28, 44, 220),
    glass_border=(255, 180, 150, 40),
    text=(248, 236, 236),
    text_dim=(180, 150, 158),
    accent=(255, 120, 60),
    accent_alt=(255, 170, 90),
    danger=(255, 80, 80),
    success=(80, 220, 140),
    warn=(255, 205, 80),
    info=(120, 160, 255),
    taskbar=(40, 18, 30, 235),
    taskbar_active=(255, 120, 60),
    hover=(255, 255, 255, 20),
    active=(255, 255, 255, 32),
    scrollbar=(110, 70, 90),
    shadow=(20, 0, 10, 150),
    selection=(255, 120, 60, 70),
    wallpaper_top=(80, 20, 50),
    wallpaper_bottom=(26, 10, 24),
    icon_bg=(255, 120, 60),
    titlebar_top=(96, 40, 62),
    titlebar_bottom=(50, 24, 38),
    glow=(255, 120, 60),
)

MIDNIGHT = Theme(
    name="Midnight",
    is_dark=True,
    bg=(6, 10, 20),
    bg_alt=(12, 18, 32),
    surface=(16, 24, 42),
    surface_alt=(26, 38, 62),
    glass=(14, 22, 40, 220),
    glass_border=(140, 170, 255, 40),
    text=(224, 232, 248),
    text_dim=(140, 152, 178),
    accent=(96, 130, 255),
    accent_alt=(150, 175, 255),
    danger=(255, 90, 100),
    success=(70, 215, 150),
    warn=(250, 210, 90),
    info=(90, 160, 255),
    taskbar=(10, 16, 30, 240),
    taskbar_active=(96, 130, 255),
    hover=(255, 255, 255, 18),
    active=(255, 255, 255, 30),
    scrollbar=(60, 80, 120),
    shadow=(0, 0, 10, 160),
    selection=(96, 130, 255, 70),
    wallpaper_top=(12, 24, 56),
    wallpaper_bottom=(4, 6, 16),
    icon_bg=(96, 130, 255),
    titlebar_top=(24, 40, 72),
    titlebar_bottom=(14, 22, 40),
    glow=(96, 130, 255),
)

THEMES: Dict[str, Theme] = {
    "dark": DARK,
    "light": LIGHT,
    "ocean": OCEAN,
    "forest": FOREST,
    "violet": VIOLET,
    "rose": ROSE,
    "sunset": SUNSET,
    "midnight": MIDNIGHT,
}

THEME_NAMES = list(THEMES.keys())


def blend(c1: tuple, c2: tuple, t: float) -> tuple:
    """Linearly interpolate two RGBA/RGB colors of the same length."""
    t = max(0.0, min(1.0, t))
    n = min(len(c1), len(c2))
    if n == 0:
        return c1 or c2
    out = tuple(int(a + (b - a) * t) for a, b in zip(c1[:n], c2[:n]))
    return out + c1[n:] if len(c1) > n else out
