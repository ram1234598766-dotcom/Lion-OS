# tests/test_workspaces.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
from lionos.kernel import LionOS


def test_workspace_switch():
    os_ = LionOS()
    os_._no_draw = False
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    inst = os_.launch("Terminal")
    inst.window.workspace = 1
    os_.set_workspace(0)
    assert os_.workspace == 0
    os_.set_workspace(1)
    assert os_.workspace == 1
    os_.wm.focus(inst.window)
    assert os_.wm.focused is inst.window


def test_tile_window_half():
    os_ = LionOS()
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    inst = os_.launch("Terminal")
    os_.tile_window("left")
    assert inst.window.rect.width == os_.screen_w // 2
