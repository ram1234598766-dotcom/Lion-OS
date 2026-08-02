# tests/test_sound.py
from lionos.sound import SoundTheme


class FakeAudio:
    def __init__(self):
        self.calls = []
    def play_sfx(self, sid):
        self.calls.append(sid)
    def set_volume(self, v):
        pass


def test_sound_theme_plays():
    a = FakeAudio()
    s = SoundTheme(a)
    s.enabled = True
    s.play("open")
    assert a.calls == ["open"]


def test_sound_disabled_noop():
    a = FakeAudio()
    s = SoundTheme(a)
    s.enabled = False
    s.play("open")
    assert a.calls == []
