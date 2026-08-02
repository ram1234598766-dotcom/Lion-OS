"""Sound theme — plays guarded UI sounds through the audio driver."""
from __future__ import annotations


class SoundTheme:
    def __init__(self, audio=None):
        self._audio = audio
        self.enabled = True
        self.volume = 0.8

    def set_volume(self, v: float) -> None:
        self.volume = max(0.0, min(1.0, v))
        if self._audio is not None:
            self._audio.set_volume(self.volume)

    def play(self, sound_id: str) -> None:
        if not self.enabled or self._audio is None:
            return
        try:
            self._audio.play_sfx(sound_id)
        except Exception:
            pass
