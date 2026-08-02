"""Media driver — audio file backend, image loading, codec table."""
from __future__ import annotations

import os

import pygame

from ..framework import Driver

AUDIO_EXTS = {".wav", ".ogg", ".mp3"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}


class MediaDriver(Driver):
    name = "media"
    category = "core"
    description = "Audio/image playback + codec detection"

    def __init__(self, config=None):
        super().__init__(config)
        self._video = False

    def probe(self) -> bool:
        self._video = False
        try:
            import importlib.util
            self._video = any(importlib.util.find_spec(m)
                              for m in ("av", "imageio_ffmpeg", "cv2"))
        except Exception:
            pass
        return True

    def auto_tune(self) -> dict:
        return {"video": self._video}

    def supports(self, path: str) -> bool:
        return os.path.splitext(path)[1].lower() in AUDIO_EXTS | IMAGE_EXTS

    def codecs(self) -> list:
        exts = sorted(AUDIO_EXTS | IMAGE_EXTS)
        return exts + (["video (optional backend)"] if self._video else [])

    def open_audio(self, path: str) -> None:
        pygame.mixer.music.load(path)

    def diagnose(self) -> str:
        return f"{len(self.codecs())} codecs" + (" +video" if self._video else "")
