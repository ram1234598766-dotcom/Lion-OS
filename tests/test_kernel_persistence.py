# tests/test_kernel_persistence.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
from lionos.kernel import LionOS


def test_kernel_has_clipboard():
    os_ = LionOS()
    assert os_.clipboard is not None
    os_.clipboard_copy("hello")
    assert os_.clipboard_paste() == "hello"


def test_session_save_restore_roundtrip():
    os_ = LionOS()
    os_._no_draw = False
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    os_.launch("Terminal")
    snapshot = os_._collect_session()
    assert any(w["app"] == "Terminal" for w in snapshot["windows"])
    os_._restore_session(snapshot)
    assert any(w.app.name == "Terminal" for w in os_.wm.windows)
