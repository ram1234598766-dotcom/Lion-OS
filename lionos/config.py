"""Persistent user configuration for Lion-OS.

Stored as JSON in ``~/.lionos/config.json``.
"""

import json
import os
import platform
import sys
import threading
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional

APP_DIR_NAME = ".lionos"


def config_dir() -> str:
    return os.path.join(os.path.expanduser("~"), APP_DIR_NAME)


def ensure_config_dir() -> str:
    d = config_dir()
    os.makedirs(d, exist_ok=True)
    return d


def _default_theme() -> str:
    return "dark"


@dataclass
class LionConfig:
    theme: str = "dark"
    wallpaper: str = "gradient"          # gradient | solid
    wallpaper_color: str = "#1a1040"
    accent: str = "#f79400"
    username: str = "Lion"
    password: str = ""                   # empty = auto-login
    resolution: str = "windowed"         # windowed | fullscreen
    screen_w: int = 1280
    screen_h: int = 720
    volume: float = 0.8
    clock_24h: bool = False
    font_size: int = 16
    ai_provider: str = "ollama"          # ollama | openai | deepseek | local
    ai_model: str = ""
    ai_endpoint: str = ""
    ai_api_key: str = ""
    ai_enabled: bool = True
    anim_enabled: bool = True
    auto_login: bool = False
    lock_on_wake: bool = False
    mru_apps: list = field(default_factory=list)
    bookmarks: list = field(default_factory=list)

    def save(self) -> None:
        ensure_config_dir()
        path = os.path.join(config_dir(), "config.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
        os.replace(tmp, path)

    @classmethod
    def load(cls) -> "LionConfig":
        cfg = cls()
        path = os.path.join(config_dir(), "config.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
            except (json.JSONDecodeError, OSError):
                pass
        return cfg

    @property
    def system_info(self) -> Dict[str, Any]:
        import platform as p
        return {
            "hostname": p.node(),
            "os": p.system(),
            "release": p.release(),
            "machine": p.machine(),
            "processor": p.processor() or p.machine(),
            "python": sys.version.split()[0],
            "arch": p.machine(),
        }


class ConfigStore:
    """Thread-safe access to the shared config."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.cfg: LionConfig = LionConfig.load()

    def get(self) -> LionConfig:
        with self._lock:
            return self.cfg

    def set(self, **kwargs) -> None:
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self.cfg, k):
                    setattr(self.cfg, k, v)
            self.cfg.save()

    def save(self) -> None:
        with self._lock:
            self.cfg.save()
