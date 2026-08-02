# tests/test_new_apps.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
from lionos.kernel import LionOS
from lionos.apps import get_apps


def test_new_apps_registered():
    names = {c.name for c in get_apps()}
    for want in ("Inbox", "System Health", "Today"):
        assert want in names, want


def test_new_apps_launch_and_draw():
    os_ = LionOS()
    os_._no_draw = False
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    for name in ("Inbox", "System Health", "Today", "Media Player"):
        inst = os_.launch(name)
        for _ in range(4):
            os_._dt = 0.016
            os_._update(os_._dt)
        assert inst.hydrated, name
    os_._needs_redraw = True
    os_._draw()
    pygame.display.flip()
