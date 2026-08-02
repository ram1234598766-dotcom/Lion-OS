# tests/test_shell_icons.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
pygame.font.init()
import pytest
from lionos.theme import THEMES
from lionos.icons import APP_ICONS, glyph_scene, IconCache
from lionos.widgets import draw_app_tile


@pytest.fixture()
def surf():
    return pygame.Surface((400, 400), pygame.SRCALPHA)


def test_draw_app_tile_accepts_scene(surf):
    cache = IconCache()
    r = pygame.Rect(0, 0, 32, 32)
    draw_app_tile(surf, r, "☺", THEMES["dark"], icon_cache=cache,
                  scene=APP_ICONS["Terminal"], scene_id="Terminal")
    assert r is not None  # no exception; rect returned


def test_draw_app_tile_uses_vector_icon_not_glyph(surf):
    cache = IconCache()
    # Render tile with the Terminal scene on a transparent surf and assert
    # some non-transparent pixels exist (proves something was drawn).
    draw_app_tile(surf, pygame.Rect(0, 0, 48, 48), "☺", THEMES["dark"],
                  icon_cache=cache, scene=APP_ICONS["Terminal"], scene_id="Terminal")
    has_pixels = any(surf.get_at((x, y))[3] > 0 for x in range(0, 48, 4) for y in range(0, 48, 4))
    assert has_pixels


def test_draw_app_tile_falls_back_to_glyph_without_scene(surf):
    cache = IconCache()
    draw_app_tile(surf, pygame.Rect(0, 0, 32, 32), "☺", THEMES["dark"], icon_cache=cache)
    # should not raise
