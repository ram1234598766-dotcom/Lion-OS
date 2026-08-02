# tests/test_catalog_tray.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
from lionos.kernel import LionOS


def test_catalog_has_all_apps():
    os_ = LionOS()
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    rows = os_.launcher_catalog()
    assert len(rows) >= 15
    assert all("name" in r and "desc" in r for r in rows)


def test_statusline_config():
    os_ = LionOS()
    os_.config.statusline = ["clock", "date", "theme"]
    assert os_.statusline_widgets() == ["clock", "date", "theme"]
