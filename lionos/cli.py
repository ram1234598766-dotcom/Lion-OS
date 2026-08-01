"""Command-line interface for Lion-OS.

Run the OS::

    lionos
    python -m lionos

Flags:
    --reset        reset saved configuration
    --theme NAME   boot with a specific theme (dark, light, ocean, forest, violet, rose)
    --fullscreen   boot fullscreen
    --windowed     boot in a window
    --headless     run without rendering (smoke test mode)
    --version      print version
"""

from __future__ import annotations

import argparse
import os
import sys


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lionos",
        description="Lion-OS — a graphical desktop OS that runs inside Python.",
    )
    p.add_argument("--reset", action="store_true", help="Reset saved configuration")
    p.add_argument("--theme", choices=["dark", "light", "ocean", "forest", "violet", "rose"],
                   help="Boot with a specific theme")
    p.add_argument("--fullscreen", action="store_true", help="Boot fullscreen")
    p.add_argument("--windowed", action="store_true", help="Boot in a window")
    p.add_argument("--headless", action="store_true", help="Run without rendering (test mode)")
    p.add_argument("--screen", type=str, default=None, help="Screen size WxH, e.g. 1600x900")
    p.add_argument("--version", action="version", version=f"Lion-OS {__import__('lionos').__version__}")
    return p


def main(argv=None) -> int:
    from lionos import __version__, APP_NAME
    from lionos.config import LionConfig

    args = build_parser().parse_args(argv)

    if args.reset:
        from lionos.config import config_dir
        cfg_path = os.path.join(config_dir(), "config.json")
        if os.path.exists(cfg_path):
            os.remove(cfg_path)
            print("Configuration reset.")

    cfg = LionConfig.load()
    if args.theme:
        cfg.theme = args.theme
    if args.fullscreen:
        cfg.resolution = "fullscreen"
    if args.windowed:
        cfg.resolution = "windowed"
    if args.screen and "x" in args.screen:
        try:
            w, h = args.screen.lower().split("x")
            cfg.screen_w = int(w)
            cfg.screen_h = int(h)
        except ValueError:
            pass

    if args.headless:
        os.environ["LION_OS_HEADLESS"] = "1"
        from lionos.headless import run_smoke_test
        return run_smoke_test()

    print(f"  {APP_NAME} v{__version__}")
    print("  Booting desktop environment...")

    from lionos.kernel import boot
    return boot(cfg)


if __name__ == "__main__":
    sys.exit(main())
