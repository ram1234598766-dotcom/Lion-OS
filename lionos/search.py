"""Global search across apps, settings, notes, and activity."""
from __future__ import annotations

SETTINGS_FIELDS = ("theme", "wallpaper", "accent_override", "motion",
                   "sound_enabled", "statusline", "session_resume",
                   "clipboard_enabled", "show_fps", "focus_off")


def global_search(query: str, os_) -> list:
    q = query.lower()
    results = []
    if not q:
        return results
    # apps
    for name, cls in os_.apps_registry.all().items():
        if q in name.lower() or q in (getattr(cls, "description", "") or "").lower():
            results.append({"title": name, "source": "Apps", "kind": "app",
                            "target": name})
    # settings
    for field in SETTINGS_FIELDS:
        if q in field.replace("_", " ").lower():
            results.append({"title": field.replace("_", " ").title(),
                            "source": "Settings", "kind": "setting",
                            "target": field})
    # notes filenames
    try:
        import os as _os
        from .config import config_dir
        notes_dir = _os.path.join(config_dir(), "notes")
        if _os.path.isdir(notes_dir):
            for fn in _os.listdir(notes_dir):
                if q in fn.lower():
                    results.append({"title": fn, "source": "Notes", "kind": "note",
                                    "target": fn})
    except Exception:
        pass
    # activity log apps
    from . import activity
    for name in activity.app_counts():
        if q in name.lower():
            results.append({"title": name, "source": "Activity", "kind": "app",
                            "target": name})
    return results
