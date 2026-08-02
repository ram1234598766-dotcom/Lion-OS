# tests/test_devices_app.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
from lionos.kernel import LionOS
from lionos.apps import get_apps


def test_devices_app_registered():
    assert any(c.name == "Devices" for c in get_apps())


def test_devices_app_launches_and_draws():
    os_ = LionOS()
    os_._no_draw = False
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    inst = os_.launch("Devices")
    for _ in range(4):
        os_._dt = 0.016
        os_._update(os_._dt)
    assert inst.hydrated
    os_._needs_redraw = True
    os_._draw()
    pygame.display.flip()
