"""Audio driver — guarded mixer init, volume, SFX, music."""
from __future__ import annotations

import array
import math

import pygame

from ..framework import Driver

_SFX_FREQ = {
    "boot": 440, "open": 660, "close": 330, "toast": 520,
    "screenshot": 780, "error": 180,
}


class AudioDriver(Driver):
    name = "audio"
    category = "core"
    description = "Audio output (mixer, volume, music)"
    config_defaults = {"volume": 0.8, "muted": False}

    def probe(self) -> bool:
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.pre_init(44100, -16, 2, 512)
                pygame.mixer.init()
        except pygame.error:
            self._set(available=False, detail="no audio device")
            return False
        self._set(available=True, detail="ok")
        return True

    def auto_tune(self) -> dict:
        return {"volume": 0.8, "muted": False}

    def _mixer(self):
        return self.status.available and pygame.mixer.get_init() is not None

    def set_volume(self, v: float) -> None:
        self.config["volume"] = max(0.0, min(1.0, v))
        if self._mixer():
            mul = 0.0 if self.config.get("muted") else 1.0
            pygame.mixer.music.set_volume(self.config["volume"] * mul)

    def mute(self):
        self.config["muted"] = True
        self.set_volume(self.config["volume"])

    def unmute(self):
        self.config["muted"] = False
        self.set_volume(self.config["volume"])

    def play_sfx(self, sound_id: str) -> None:
        if not self._mixer():
            return
        sr = 44100
        dur = 0.08
        freq = _SFX_FREQ.get(sound_id, 440)
        n = int(sr * dur)
        buf = array.array("h", (int(12000 * math.sin(2 * math.pi * freq * i / sr))
                                for i in range(n)))
        snd = pygame.mixer.Sound(buffer=buf)
        snd.set_volume(self.config["volume"])
        snd.play()

    def play_music(self, path: str) -> None:
        if self._mixer():
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()

    def stop_music(self) -> None:
        if self._mixer():
            pygame.mixer.music.stop()

    def diagnose(self) -> str:
        return "no device" if not self.status.available else "ok"
