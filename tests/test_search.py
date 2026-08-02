# tests/test_search.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
from lionos.kernel import LionOS
from lionos.search import global_search


def test_search_finds_apps():
    os_ = LionOS()
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    results = global_search("terminal", os_)
    assert any(r["kind"] == "app" and "Terminal" in r["title"] for r in results)


def test_search_finds_settings():
    os_ = LionOS()
    results = global_search("wallpaper", os_)
    assert any(r["kind"] == "setting" for r in results)
