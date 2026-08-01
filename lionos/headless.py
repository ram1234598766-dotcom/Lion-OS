"""Headless smoke-test runner for Lion-OS.

Drives the kernel loop without a display (SDL dummy video driver) and verifies
that boot, login and a sample of apps run without crashing. Used by CI and the
``--headless`` flag.
"""

from __future__ import annotations

import os
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["LION_OS_HEADLESS"] = "1"


def run_smoke_test(steps: int = 400, tick_dt: float = 0.05) -> int:
    from lionos.config import LionConfig
    from lionos.kernel import LionOS

    cfg = LionConfig()
    cfg.theme = "dark"
    cfg.auto_login = True
    cfg.screen_w = 800
    cfg.screen_h = 600

    os_ = LionOS(cfg)

    # 1) boot to completion
    guard = 0
    while not os_.booted and guard < steps:
        os_._update(tick_dt)
        guard += 1
    assert os_.booted, "OS never finished booting"

    # 2) login
    os_._do_login()
    assert os_.logged_in, "OS never logged in"

    # 3) launch a battery of apps and run a few frames
    apps = ["Welcome", "Calculator", "Text Editor", "File Manager", "Notes",
            "Paint", "System Monitor", "Settings", "About", "AI Assistant"]
    ok = 0
    for name in apps:
        try:
            inst = os_.launch(name)
            assert inst is not None
            for _ in range(8):
                os_._update(tick_dt)
                os_._draw()
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"[FAIL] {name}: {type(e).__name__}: {e}", file=sys.stderr)

    # 4) simulate a keypress
    import pygame
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    for _ in range(5):
        os_._update(tick_dt)

    print(f"[ok] booted + logged in; apps launched: {ok}/{len(apps)}")
    assert ok >= 8, f"Too many app launch failures: {ok}/{len(apps)}"
    return 0


if __name__ == "__main__":
    sys.exit(run_smoke_test())
