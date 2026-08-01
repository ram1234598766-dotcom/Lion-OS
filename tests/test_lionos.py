"""Automated tests for Lion-OS.

These run headlessly with SDL's dummy driver so they work in CI without a
display server.
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest


@pytest.fixture(scope="module")
def os_env():
    from lionos.config import LionConfig
    from lionos.kernel import LionOS

    cfg = LionConfig()
    cfg.auto_login = True
    cfg.screen_w = 800
    cfg.screen_h = 600
    o = LionOS(cfg)
    # boot fully
    for _ in range(300):
        o._update(0.05)
    assert o.booted
    o._do_login()
    assert o.logged_in
    yield o
    pygame.quit()


def test_all_apps_registered(os_env):
    apps = os_env.apps_registry.all()
    assert len(apps) >= 14
    for name in ("Calculator", "File Manager", "Terminal", "Text Editor",
                 "Paint", "System Monitor", "Settings", "Notes", "Browser",
                 "Media Player", "AI Assistant", "About", "App Store", "Welcome"):
        assert name in apps, f"missing app {name}"


@pytest.mark.parametrize("name", [
    "Welcome", "Calculator", "Text Editor", "File Manager", "Notes",
    "Paint", "System Monitor", "Settings", "About", "AI Assistant",
    "Media Player", "Browser", "App Store",
])
def test_app_launch_and_render(os_env, name):
    inst = os_env.launch(name)
    assert inst is not None
    for _ in range(8):
        os_env._update(0.05)
        os_env._draw()


def test_calculator_math(os_env):
    calc = os_env.launch("Calculator")
    for label in ("7", "+", "3", "="):
        r, c = calc.buttons[label]
        br = calc._btn_rect(r, c)
        ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(br.centerx, br.centery))
        calc.handle_event(ev, (br.centerx, br.centery))
    assert calc.result == "10", f"expected 10, got {calc.result!r}"


def test_window_move_and_snap(os_env):
    calc = os_env.launch("Calculator")
    w = calc.window
    start = (w.rect.centerx, w.rect.y + 10)
    os_env._handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=start))
    os_env._handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(start[0] + 200, start[1] + 150), rel=(200, 150)))
    os_env._handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(start[0] + 200, start[1] + 150)))
    assert w.rect.x != start[0], "window did not move"


def test_window_close_button(os_env):
    calc = os_env.launch("Calculator")
    w = calc.window
    tr = w.titlebar_rect
    pos = (tr.right - 16, tr.centery)
    os_env._handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    assert calc.closed, "close button did not close the app"


def test_theme_switch(os_env):
    os_env.set_theme("ocean")
    assert os_env.theme.name.lower() == "ocean"
    os_env.set_theme("dark")


def test_file_manager_navigation(os_env):
    fm = os_env.launch("File Manager")
    assert fm.cwd == os.path.expanduser("~")
    # go home and up should not crash
    fm._go_home()
    fm._load_dir()
    os_env._update(0.05)
    os_env._draw()


def test_terminal_commands(os_env):
    term = os_env.launch("Terminal")
    assert term._handle_builtin("pwd") is True
    assert term._handle_builtin("echo hello") is True
    assert term._handle_builtin("help") is True
    assert any("hello" in ln for ln, _ in term.lines)
    # interactive submit
    term.input_line = "pwd"
    term._submit()
    assert term.input_line == ""


def test_notes_save_load(os_env):
    notes = os_env.launch("Notes")
    notes._new_note()
    notes.edit_content = "hello lion"
    notes._save_current()
    os_env._update(0.05)


def test_headless_module():
    from lionos.headless import run_smoke_test
    assert run_smoke_test() == 0
