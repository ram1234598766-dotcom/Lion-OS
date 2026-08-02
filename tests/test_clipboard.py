# tests/test_clipboard.py
import lionos.clipboard as C


def test_copy_paste(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "_state_dir", str(tmp_path))
    cb = C.Clipboard()
    cb.copy("text", "hello")
    assert cb.paste() == "hello"


def test_history_ring(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "_state_dir", str(tmp_path))
    cb = C.Clipboard(max_history=3)
    for i in range(5):
        cb.copy("text", f"item{i}")
    h = cb.history()
    assert [e["value"] for e in h] == ["item4", "item3", "item2"]


def test_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "_state_dir", str(tmp_path))
    cb = C.Clipboard()
    cb.copy("text", "x")
    cb.clear()
    assert cb.paste() == ""
