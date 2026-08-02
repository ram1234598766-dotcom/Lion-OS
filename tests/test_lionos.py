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


# ---------------------------------------------------------------------------
# Refinement pass tests
# ---------------------------------------------------------------------------
def test_all_themes_registered(os_env):
    from lionos.theme import THEMES
    assert len(THEMES) >= 8
    for name in ("dark", "light", "ocean", "forest", "violet", "rose",
                 "sunset", "midnight"):
        assert name in THEMES


def test_theme_interpolate(os_env):
    from lionos.theme import THEMES
    mid = THEMES["dark"].interpolate(THEMES["ocean"], 0.5)
    assert mid.name.lower() in ("dark", "ocean")
    assert mid.bg is not None and mid.accent is not None
    # t=0 stays dark, t=1 becomes ocean
    assert THEMES["dark"].interpolate(THEMES["ocean"], 0).bg == THEMES["dark"].bg
    assert THEMES["dark"].interpolate(THEMES["ocean"], 1).accent == THEMES["ocean"].accent


def test_theme_transition_reaches_target(os_env):
    os_env.set_theme("violet")
    assert os_env.theme.name.lower() == "violet"
    os_env.set_theme("sunset")
    assert os_env.theme.name.lower() == "sunset"
    # run the transition animation to completion
    for _ in range(60):
        os_env._update(0.05)
    assert os_env.theme.name.lower() == "sunset"
    os_env.set_theme("dark")
    for _ in range(60):
        os_env._update(0.05)


def test_window_chrome_cache_invalidation(os_env):
    calc = os_env.launch("Calculator")
    win = calc.window
    font = os_env.get_font(os_env.config.font_size)
    # build cache
    win.ensure_chrome(os_env.theme, True, font, os_env.config.font_size)
    assert win._chrome, "chrome cache should be populated"
    key_before = win._chrome_key
    # resize invalidates
    win.rect.width += 50
    win.invalidate_chrome()
    assert win._chrome_key is None or win._chrome_key != key_before
    win.ensure_chrome(os_env.theme, True, font, os_env.config.font_size)
    assert win._chrome, "cache rebuilt after invalidation"


def test_snap_corners(os_env):
    calc = os_env.launch("Calculator")
    w = calc.window
    sr = os_env.screen_rect
    for side in ("tl", "tr", "bl", "br"):
        w.snap(side, sr)
        for _ in range(30):
            w.step_anim(0.016)   # complete the morph glide
        assert w.snapped == side
        if side == "tl":
            assert (w.rect.x, w.rect.y) == (sr.x, sr.y)
        elif side == "tr":
            assert w.rect.x == sr.x + sr.width // 2
        elif side == "bl":
            assert w.rect.y == sr.y + sr.height // 2
        elif side == "br":
            assert w.rect.x == sr.x + sr.width // 2
            assert w.rect.y == sr.y + sr.height // 2


def test_snap_preview_corners(os_env):
    calc = os_env.launch("Calculator")
    w = calc.window
    sr = os_env.screen_rect
    os_env.wm._update_snap_preview(w, (sr.x + 2, sr.y + 2))
    assert os_env.wm._snap_preview["side"] == "tl"
    os_env.wm._update_snap_preview(w, (sr.right - 2, sr.y + 2))
    assert os_env.wm._snap_preview["side"] == "tr"
    os_env.wm._update_snap_preview(w, (sr.x + 2, sr.bottom - 2))
    assert os_env.wm._snap_preview["side"] == "bl"
    os_env.wm._update_snap_preview(w, (sr.right - 2, sr.bottom - 2))
    assert os_env.wm._snap_preview["side"] == "br"
    os_env.wm._snap_preview = None


def test_alt_tab_cycles_windows(os_env):
    # close any windows left over from earlier tests so the order is deterministic
    for inst in list(os_env.instances):
        inst.window.visible = False
        inst.closed = True
    os_env.instances = []
    os_env.wm.windows = []
    os_env.wm.focused = None
    calc = os_env.launch("Calculator")
    term = os_env.launch("Terminal")
    order = os_env.wm.visible_windows()
    assert len(order) == 2
    os_env.wm.start_alt_tab()
    assert os_env.wm.alt_tab_active
    os_env.wm.alt_tab_cycle()          # idx 1
    os_env.wm.alt_tab_activate()
    assert not os_env.wm.alt_tab_active
    assert os_env.wm.focused is order[1]


def test_launcher_keyboard_nav(os_env):
    os_env.launcher_open = True
    os_env.launcher_search = "cal"
    os_env._launcher_idx = 0
    # Enter launches the highlighted app
    os_env._handle_launcher_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, unicode="\r"))
    assert not os_env.launcher_open
    assert any(i.window.app.name == "Calculator" for i in os_env.instances)
    # arrow keys navigate without crashing
    os_env.launcher_open = True
    os_env.launcher_search = ""
    os_env._launcher_idx = 0
    os_env._handle_launcher_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN, unicode=""))
    os_env._handle_launcher_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP, unicode=""))
    os_env.launcher_open = False


def test_desktop_icons_launch(os_env):
    from lionos.kernel import DESKTOP_START, DESKTOP_TILE
    icon = (DESKTOP_START + DESKTOP_TILE // 2, DESKTOP_START + DESKTOP_TILE // 2)
    os_env._handle_desktop_click(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=icon))
    os_env._handle_desktop_click(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=icon))
    assert any(i.window.app.name == "Calculator" for i in os_env.instances)


def test_calculator_keyboard(os_env):
    calc = os_env.launch("Calculator")
    for key, unicode_ in [(pygame.K_7, "7"), (pygame.K_PLUS, "+"),
                          (pygame.K_3, "3"), (pygame.K_EQUALS, "=")]:
        calc.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, unicode=unicode_), (0, 0))
    assert calc.result == "10", f"expected 10, got {calc.result!r}"
    # history recorded
    assert len(calc.history) >= 1


def test_calculator_percent(os_env):
    calc = os_env.launch("Calculator")
    for key, unicode_ in [(pygame.K_5, "5"), (pygame.K_0, "0")]:
        calc.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, unicode=unicode_), (0, 0))
    calc._percent()
    assert calc.expression == "0.5", f"expected 0.5, got {calc.expression!r}"


def test_terminal_history(os_env):
    term = os_env.launch("Terminal")
    term.input_line = "echo first"
    term._submit()
    term.input_line = "echo second"
    term._submit()
    assert term.history[-1] == "echo second"
    assert term.history[-2] == "echo first"
    # UP recalls previous
    term.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP), (0, 0))
    assert term.input_line == "echo second"


def test_notes_autosave(os_env):
    import shutil
    notes = os_env.launch("Notes")
    d = notes._notes_dir()
    shutil.rmtree(d, ignore_errors=True)
    notes._new_note()
    notes.edit_content = "autosave content"
    notes._mark_dirty()
    for _ in range(30):
        os_env._update(0.05)
    files = os.listdir(d) if os.path.isdir(d) else []
    assert any("autosave" in f for f in files), f"expected autosave file, got {files}"
    shutil.rmtree(d, ignore_errors=True)
