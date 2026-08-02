# tests/conftest.py
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest


@pytest.fixture(autouse=True)
def _ensure_pygame_font():
    """Some tests call pygame.quit() in teardown, which invalidates every
    cached Font object (a font created before the quit errors with
    'Invalid font (font module quit since font created)' even after
    re-init). Drop the widget font cache and re-init the module before
    every test so font rendering always works."""
    from lionos.widgets import clear_font_cache
    clear_font_cache()
    pygame.font.init()
    yield
