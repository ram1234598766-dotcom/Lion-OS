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
    }


def _fingerprint(theme: Theme) -> tuple:
    return tuple(getattr(theme, f)
                 for f in ("accent", "accent2", "surface_alt", "text",
                           "text_dim", "glow", "success", "warn", "danger"))


# --- renderer -------------------------------------------------------------
def _draw_primitive(surf, kind, p, pal, s):
    scale = lambda v: int(v * s)
    px = lambda k: pal.get(p.get(k), (255, 255, 255))
    if kind == "rect":
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
