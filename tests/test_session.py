# tests/test_session.py
import os

import lionos.session as S


def _cfg(tmp):
    S._state_dir = str(tmp)
    return tmp


def test_save_load_roundtrip(tmp_path):
    _cfg(tmp_path)
    data = {"windows": [{"app": "Terminal", "rect": [0, 0, 800, 600]}],
            "theme": "ocean", "workspace": 2}
    S.save_session(data)
    assert S.load_session()["windows"] == data["windows"]
    assert S.load_session()["theme"] == "ocean"


def test_load_missing_returns_none(tmp_path):
    _cfg(tmp_path)
    assert S.load_session() is None


def test_load_corrupt_returns_none(tmp_path):
    _cfg(tmp_path)
    with open(S.session_path(), "w") as f:
        f.write("{not json")
    assert S.load_session() is None


def test_checkpoint_rotation(tmp_path):
    _cfg(tmp_path)
    for i in range(5):
        S.checkpoint_session({"n": i}, keep=3)
    files = sorted(n for n in os.listdir(str(tmp_path)) if n.startswith("session-"))
    assert len(files) == 3


def test_recover_falls_back_to_checkpoint(tmp_path):
    _cfg(tmp_path)
    S.checkpoint_session({"n": 1})
    data = S.recover_session()
    assert data is not None and data["n"] == 1
