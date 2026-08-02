# tests/test_screenshot_focus.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
from lionos.kernel import LionOS


def test_screenshot_writes_file():
    os_ = LionOS()
    os_._no_draw = False
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    os_._needs_redraw = True
    os_._draw()
    import pygame
    pygame.display.flip()
    path = os_.take_screenshot()
    assert path and os.path.exists(path)


def test_focus_mode_dim():
    os_ = LionOS()
    os_.config.focus_off = ["Terminal"]
    assert os_.focus_dimmed("Terminal") is True
    assert os_.focus_dimmed("Notes") is False
