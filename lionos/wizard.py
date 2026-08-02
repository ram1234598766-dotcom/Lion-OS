"""First-boot wizard — scaffolds ~/.lionos/profile.json."""
from __future__ import annotations

import json
import os
import shutil
import time

from .config import config_dir

_state_dir = config_dir()
WIZARD_STEPS = ["name", "theme", "pin", "matters"]


def profile_path() -> str:
    return os.path.join(_state_dir, "profile.json")


def load_profile() -> dict:
    try:
        with open(profile_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_profile(data: dict) -> None:
    os.makedirs(_state_dir, exist_ok=True)
    if os.path.exists(profile_path()):
        arch = os.path.join(_state_dir, "archives")
        os.makedirs(arch, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        shutil.copyfile(profile_path(), os.path.join(arch, f"profile-{stamp}.json"))
    data["saved_at"] = time.time()
    tmp = profile_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, profile_path())
