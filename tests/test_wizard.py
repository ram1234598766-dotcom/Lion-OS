# tests/test_wizard.py
import lionos.wizard as W


def test_profile_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "_state_dir", str(tmp_path))
    W.save_profile({"name": "Lion", "theme": "ocean", "pinned": ["Terminal"]})
    assert W.load_profile()["name"] == "Lion"


def test_load_missing_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "_state_dir", str(tmp_path))
    assert W.load_profile() == {}


def test_profile_step_constants():
    assert W.WIZARD_STEPS == ["name", "theme", "pin", "matters"]
