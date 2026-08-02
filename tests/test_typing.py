# tests/test_typing.py
# Regression: keyboard events (KEYDOWN/TEXTINPUT) must reach the focused app.
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
from lionos.kernel import LionOS


def _boot():
    os_ = LionOS()
    os_._no_draw = False
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    return os_


def test_keyboard_reaches_inbox():
    os_ = _boot()
    inst = os_.launch("Inbox")
    os_.wm.focus(inst.window)
    os_._handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h, unicode="h", mod=0))
    os_._handle_event(pygame.event.Event(pygame.TEXTINPUT, text="i"))
    assert inst._entry == "hi"


def test_keyboard_reaches_text_editor():
    os_ = _boot()
    te = os_.launch("Text Editor")
    os_.wm.focus(te.window)
    os_._handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x, unicode="x", mod=0))
    assert te.lines[0] == "x"


def test_wizard_name_typing():
    os_ = LionOS()
    os_.wizard_active = True
    os_._wizard_input = ""
    os_._handle_login_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a, unicode="a", mod=0))
    assert os_._wizard_input == "a"
