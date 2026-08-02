"""Procedural vector icon system for Lion-OS.

Apps declare a small scene of shape primitives in a normalized 0..64 box.
``IconCache.render`` draws the scene at 2x and smoothscales it down, giving
crisp antialiased icons at any size. Colors are semantic token names resolved
through the active theme, so every icon re-themes automatically.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import pygame

from .theme import Theme

Color = Tuple[int, int, int]
RGBA = Tuple[int, int, int, int]
Scene = List[Tuple[str, dict]]


# --- scene builders (normalized 0..64 box) --------------------------------
def s_rect(x=0, y=0, w=16, h=16, color="accent", radius=3):
    return ("rect", dict(x=x, y=y, w=w, h=h, color=color, radius=radius))


def s_circle(cx=32, cy=32, r=8, color="accent", width=0):
    return ("circle", dict(cx=cx, cy=cy, r=r, color=color, width=width))


def s_line(x1=0, y1=0, x2=64, y2=64, color="text", width=2):
    return ("line", dict(x1=x1, y1=y1, x2=x2, y2=y2, color=color, width=width))


def s_arc(x=0, y=0, w=16, h=16, a1=0.0, a2=6.28, color="accent", width=2):
    return ("arc", dict(x=x, y=y, w=w, h=h, a1=a1, a2=a2, color=color, width=width))


def s_poly(points, color="accent"):
    return ("poly", dict(points=list(points), color=color))


def s_ellipse(x=0, y=0, w=16, h=16, color="accent", width=0):
    return ("ellipse", dict(x=x, y=y, w=w, h=h, color=color, width=width))


def s_glyph(char, size=10, color="text", cx=32, cy=32):
    return ("glyph", dict(char=char, size=size, color=color, cx=cx, cy=cy))


def glyph_scene(char):
    return [s_glyph(char, 40, "text", cx=32, cy=32)]


# --- app icon scenes (normalized 0..64) ------------------------------------
APP_ICONS: Dict[str, Scene] = {
    # Terminal: prompt + underscore line on a dark panel
    "Terminal": [
        s_rect(10, 18, 44, 34, "grad", radius=6),
        s_glyph(">", 16, "accent", cx=22, cy=32),
        s_line(32, 32, 52, 32, "muted", 3),
    ],
    # Calculator: rounded body + key grid
    "Calculator": [
        s_rect(14, 10, 36, 46, "grad", radius=6),
        s_rect(20, 16, 24, 6, "muted", radius=2),
        *[s_circle(cx=22 + (i % 3) * 10, cy=30 + (i // 3) * 10, r=3,
                   color=("accent" if i < 4 else "muted"))
          for i in range(9)],
    ],
    # File Manager: folder with tab
    "File Manager": [
        s_rect(12, 20, 16, 8, "accent2", radius=3),
        s_rect(10, 24, 44, 28, "accent", radius=4),
        s_line(18, 34, 46, 34, "white", 2),
        s_line(18, 40, 40, 40, "white", 2),
    ],
    # Notes: page with lines + folded corner
    "Notes": [
        s_rect(18, 12, 30, 42, "panel", radius=4),
        s_line(24, 24, 42, 24, "muted", 2),
        s_line(24, 32, 42, 32, "muted", 2),
        s_line(24, 40, 36, 40, "muted", 2),
        s_poly([(44, 40), (48, 40), (48, 36), (44, 40)], "accent"),
    ],
    # Settings: gear (circle + spokes)
    "Settings": [
        s_circle(cx=32, cy=32, r=9, color="accent", width=3),
        s_circle(cx=32, cy=32, r=4, color="accent"),
        *[s_line(cx0, cy0, cx1, cy1, "accent", 3)
          for (cx0, cy0, cx1, cy1) in [
              (32, 10, 32, 17), (32, 47, 32, 54), (10, 32, 17, 32),
              (47, 32, 54, 32), (16, 16, 21, 21), (43, 43, 48, 48),
              (43, 21, 48, 16), (16, 43, 21, 48)]],
    ],
    # Browser: globe
    "Browser": [
        s_circle(cx=32, cy=32, r=18, color="accent", width=3),
        s_ellipse(14, 18, 36, 28, "accent", width=2),
        s_line(14, 32, 50, 32, "accent", 2),
        s_line(32, 14, 32, 50, "accent", 2),
    ],
    # Media Player: two music notes
    "Media Player": [
        s_circle(cx=20, cy=46, r=6, color="accent"),
        s_line(24, 46, 24, 18, "accent", 3),
        s_line(24, 18, 44, 12, "accent", 3),
        s_line(44, 12, 44, 32, "accent", 3),
        s_circle(cx=44, cy=32, r=6, color="accent"),
    ],
    # Paint: palette with dots
    "Paint": [
        s_circle(cx=32, cy=32, r=20, color="accent", width=3),
        s_circle(cx=32, cy=32, r=13, color="accent"),
        s_circle(cx=24, cy=38, r=4, color="success"),
        s_circle(cx=34, cy=42, r=4, color="warn"),
        s_circle(cx=42, cy=34, r=4, color="danger"),
    ],
    # AI Assistant: chat bubble with dots
    "AI Assistant": [
        s_rect(12, 14, 40, 28, "accent", radius=8),
        s_poly([(16, 40), (16, 50), (26, 40)], "accent"),
        s_circle(cx=24, cy=28, r=3, color="white"),
        s_circle(cx=32, cy=28, r=3, color="white"),
        s_circle(cx=40, cy=28, r=3, color="white"),
    ],
    # System Monitor: bar chart
    "System Monitor": [
        s_line(12, 52, 52, 52, "muted", 3),
        s_rect(16, 34, 8, 18, "accent", radius=2),
        s_rect(28, 22, 8, 30, "success", radius=2),
        s_rect(40, 12, 8, 40, "warn", radius=2),
    ],
    # Text Editor: page with pencil
    "Text Editor": [
        s_rect(18, 10, 30, 44, "panel", radius=4),
        s_line(24, 22, 42, 22, "muted", 2),
        s_line(24, 30, 42, 30, "muted", 2),
        s_line(24, 38, 36, 38, "muted", 2),
        s_line(40, 40, 50, 30, "accent", 3),
        s_line(50, 30, 54, 34, "accent", 3),
    ],
    # About: info ring
    "About": [
        s_circle(cx=32, cy=32, r=20, color="accent", width=3),
        s_circle(cx=32, cy=24, r=3, color="accent"),
        s_line(32, 30, 32, 44, "accent", 3),
    ],
    # App Store: shopping bag
    "App Store": [
        s_arc(26, 12, 12, 10, 3.14, 6.28, "accent", 3),
        s_rect(18, 22, 28, 30, "accent", radius=4),
        s_line(26, 22, 26, 30, "white", 2),
        s_line(38, 22, 38, 30, "white", 2),
    ],
    # Welcome: sparkle star
    "Welcome": [
        s_poly([(32, 10), (37, 27), (54, 32), (37, 37), (32, 54),
                (27, 37), (10, 32), (27, 27)], "accent"),
    ],
    # UI Toolkit: 2x2 grid of rounded squares
    "UI Toolkit": [
        s_rect(12, 12, 16, 16, "accent", radius=4),
        s_rect(36, 12, 16, 16, "success", radius=4),
        s_rect(12, 36, 16, 16, "warn", radius=4),
        s_rect(36, 36, 16, 16, "muted", radius=4),
    ],
    # --- planned Phase-5 apps (scenes defined now so Phase 1 tests cover them)
    "Help": [
        s_circle(cx=32, cy=32, r=20, color="accent", width=3),
        s_glyph("?", 24, "accent", cx=32, cy=34),
    ],
    "System Health": [
        s_circle(cx=18, cy=32, r=9, color="danger", width=3),
        s_poly([(32, 32), (38, 26), (44, 30), (54, 22), (52, 34),
                (44, 36), (36, 40)], "success"),
        s_line(52, 34, 56, 38, "warn", 3),
    ],
    "Inbox": [
        s_rect(10, 18, 44, 30, "accent", radius=6),
        s_line(14, 24, 32, 36, "white", 3),
        s_line(50, 24, 32, 36, "white", 3),
    ],
    "Today": [
        s_circle(cx=32, cy=32, r=20, color="accent", width=3),
        s_line(32, 14, 32, 32, "accent", 3),
        s_line(32, 32, 44, 40, "accent", 3),
    ],
    "Devices": [
        s_rect(10, 24, 30, 18, "panel", radius=4),
        s_circle(cx=30, cy=33, r=5, color="accent", width=3),
        s_line(46, 22, 52, 22, "accent", 3),
        s_line(46, 34, 52, 34, "accent", 3),
        s_line(52, 22, 52, 34, "accent", 3),
        s_rect(36, 26, 8, 14, "accent", radius=2),
    ],
}


# --- palette --------------------------------------------------------------
def palette_for(theme: Theme) -> Dict[str, Color]:
    return {
        "accent": theme.accent,
        "accent2": theme.accent2,
        "panel": theme.surface_alt,
        "text": theme.text,
        "muted": theme.text_dim,
        "highlight": theme.glow,
        "success": theme.success,
        "warn": theme.warn,
        "danger": theme.danger,
        "white": (255, 255, 255),
        "black": (0, 0, 0),
        "grad1": theme.icon_grad1,
        "grad2": theme.icon_grad2,
    }


def _fingerprint(theme: Theme) -> tuple:
    return tuple(getattr(theme, f)
                 for f in ("accent", "accent2", "surface_alt", "text",
                           "text_dim", "glow", "success", "warn", "danger"))


# --- renderer -------------------------------------------------------------
def _fill_gradient(surf, rect, c1, c2, radius):
    """Vertical linear gradient fill clipped to a rounded rect."""
    clip = surf.get_clip()
    surf.set_clip(rect)
    h = max(1, rect.height)
    for yy in range(h):
        t = yy / h
        col = (int(c1[0] + (c2[0] - c1[0]) * t),
               int(c1[1] + (c2[1] - c1[1]) * t),
               int(c1[2] + (c2[2] - c1[2]) * t))
        pygame.draw.line(surf, col, (rect.x, rect.y + yy), (rect.right - 1, rect.y + yy))
    if radius > 0:
        mask = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
        surf.blit(mask, rect.topleft, special_flags=pygame.BLEND_RGBA_MIN)
    surf.set_clip(clip)


def _draw_primitive(surf, kind, p, pal, s):
    scale = lambda v: int(v * s)
    px = lambda k: pal.get(p.get(k), (255, 255, 255))
    if kind == "rect":
        if p.get("color") == "grad":
            rr = pygame.Rect(scale(p["x"]), scale(p["y"]),
                             scale(p["w"]), scale(p["h"]))
            _fill_gradient(surf, rr, pal["grad1"], pal["grad2"],
                           scale(p.get("radius", 3)))
        else:
            pygame.draw.rect(surf, px("color"),
                             pygame.Rect(scale(p["x"]), scale(p["y"]),
                                         scale(p["w"]), scale(p["h"])),
                             border_radius=scale(p.get("radius", 3)))
    elif kind == "circle":
        pygame.draw.circle(surf, px("color"),
                           (scale(p["cx"]), scale(p["cy"])),
                           scale(p["r"]), scale(p.get("width", 0)))
    elif kind == "line":
        pygame.draw.line(surf, px("color"),
                         (scale(p["x1"]), scale(p["y1"])),
                         (scale(p["x2"]), scale(p["y2"])),
                         max(1, scale(p.get("width", 2))))
    elif kind == "arc":
        pygame.draw.arc(surf, px("color"),
                        pygame.Rect(scale(p["x"]), scale(p["y"]),
                                    scale(p["w"]), scale(p["h"])),
                        p["a1"], p["a2"], max(1, scale(p.get("width", 2))))
    elif kind == "poly":
        pts = [(scale(x), scale(y)) for x, y in p["points"]]
        pygame.draw.polygon(surf, px("color"), pts)
    elif kind == "ellipse":
        pygame.draw.ellipse(surf, px("color"),
                            pygame.Rect(scale(p["x"]), scale(p["y"]),
                                        scale(p["w"]), scale(p["h"])),
                            scale(p.get("width", 0)))
    elif kind == "glyph":
        from .widgets import cached_font
        f = cached_font(scale(p.get("size", 16)))
        img = f.render(p["char"], True, px("color"))
        surf.blit(img, img.get_rect(center=(scale(p["cx"]), scale(p["cy"]))))


def _render_scene(scene, size, pal):
    ss = 2  # supersample factor
    base = 64
    big = pygame.Surface((base * ss, base * ss), pygame.SRCALPHA)
    for kind, p in scene:
        _draw_primitive(big, kind, p, pal, ss)
    return pygame.transform.smoothscale(big, (size, size))


class IconCache:
    def __init__(self):
        self._cache: Dict[tuple, pygame.Surface] = {}

    def render(self, scene, scene_id, size, theme):
        key = (scene_id, size, _fingerprint(theme))
        surf = self._cache.get(key)
        if surf is None:
            surf = _render_scene(scene, size, palette_for(theme))
            self._cache[key] = surf
        return surf
