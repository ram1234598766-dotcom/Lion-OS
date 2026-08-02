# tests/test_activity.py
import lionos.activity as A


def test_log_and_read(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "_state_dir", str(tmp_path))
    A.log_event("app_launch", "Terminal")
    A.log_event("app_launch", "Notes")
    A.log_event("theme_change", "ocean")
    evs = A.read_events()
    assert evs[0]["type"] == "theme_change"
    assert len(evs) == 3


def test_app_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "_state_dir", str(tmp_path))
    A.log_event("app_launch", "Terminal")
    A.log_event("app_launch", "Terminal")
    A.log_event("app_launch", "Notes")
    assert A.app_counts() == {"Terminal": 2, "Notes": 1}


def test_session_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "_state_dir", str(tmp_path))
    A.log_event("app_launch", "Terminal")
    A.log_event("app_launch", "Terminal")
    A.log_event("app_launch", "Notes")
    s = A.session_summary()
    assert "Terminal" in s and "Notes" in s
