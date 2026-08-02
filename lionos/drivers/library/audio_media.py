"""Audio/media library drivers."""
from ..framework import Driver


class SoundBlasterMidi(Driver):
    name = "sound_blaster"
    category = "audio"
    description = "Notes to synthesized tones"
    config_defaults = {"instrument": "square"}
    def probe(self):
        return True
    def play_note(self, freq):
        return freq


class PcmDecoder(Driver):
    name = "pcm"
    category = "audio"
    description = "Parses WAV headers + streams bits"
    def probe(self):
        return True
    def parse_header(self, data):
        if data[:4] != b"RIFF":
            raise ValueError("not a WAV")
        return {"fmt": data[8:12].decode("latin1"), "size": len(data)}


class VideoFrameDecoder(Driver):
    name = "video_frames"
    category = "audio"
    simulated = True
    description = "Image arrays to flipbook animation"
    def probe(self):
        return True


class CameraCapture(Driver):
    name = "camera"
    category = "audio"
    simulated = True
    description = "Webcam frames if present, else synthetic"
    def probe(self):
        try:
            import cv2  # noqa: F401
            self._has = True
        except Exception:
            self._has = False
        return True
    def frame(self):
        return "camera frame" if self._has else "synthetic frame"


class TtsSpeech(Driver):
    name = "tts"
    category = "audio"
    simulated = True
    description = "Text to speech (pyttsx3 if present)"
    def probe(self):
        try:
            import pyttsx3  # noqa: F401
            self._has = True
        except Exception:
            self._has = False
        return True
    def speak(self, text):
        return text if self._has else None


class RomLoader(Driver):
    name = "rom_loader"
    category = "audio"
    simulated = True
    description = "Raw byte arrays to executable logic"
    def probe(self):
        return True
