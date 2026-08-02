# tests/test_icons.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
pygame.font.init()
from lionos.icons import (s_rect, s_circle, s_line, s_glyph, glyph_scene,
                          IconCache, palette_for)
from lionos.theme import THEMES


def _term_scene():
    return [
        s_rect(10, 18, 44, 34, "panel", radius=6),
        s_glyph(">", 16, "accent", cx=20, cy=32),
        s_line(30, 32, 50, 32, "muted", 3),
    ]


def test_palette_has_tokens():
    p = palette_for(THEMES["dark"])
    for k in ("accent", "accent2", "panel", "text", "muted", "highlight", "success", "warn", "danger"):
        assert k in p and len(p[k]) in (3, 4)


def test_render_returns_correct_size():
    cache = IconCache()
    surf = cache.render(_term_scene(), "terminal", 32, THEMES["dark"])
    assert surf.get_size() == (32, 32)


def test_cache_hits_are_identical_surface():
    cache = IconCache()
    a = cache.render(_term_scene(), "terminal", 32, THEMES["dark"])
    b = cache.render(_term_scene(), "terminal", 32, THEMES["dark"])
    assert a is b  # cached object identity


def test_theme_change_invalidates():
    cache = IconCache()
    a = cache.render(_term_scene(), "terminal", 32, THEMES["dark"])
    b = cache.render(_term_scene(), "terminal", 32, THEMES["ocean"])
    assert a is not b


def test_glyph_fallback_renders():
    cache = IconCache()
    surf = cache.render(glyph_scene("☺"), "fallback", 24, THEMES["dark"])
    assert surf.get_size() == (24, 24)
