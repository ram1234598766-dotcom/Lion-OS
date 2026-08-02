# tests/test_core_drivers.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
from lionos.drivers.core.audio import AudioDriver
from lionos.drivers.core.display import DisplayDriver
from lionos.drivers.core.input import InputDriver
from lionos.drivers.core.media import MediaDriver
from lionos.drivers.core.network import NetworkDriver


def test_display_driver_probes():
    d = DisplayDriver()
    assert d.probe() is True
    assert d.diagnose()  # non-empty detail


def test_audio_driver_guarded():
    d = AudioDriver()
    d.probe()   # must not raise, with or without a device
    d.play_sfx("boot")   # no-op when unavailable
    d.set_volume(0.5)
    assert 0.0 <= d.config.get("volume", 0.5) <= 1.0


def test_input_driver_reports_devices():
    d = InputDriver()
    d.probe()
    assert d.diagnose()


def test_media_driver_supports_wav():
    d = MediaDriver()
    assert d.supports("song.wav") is True
    assert d.supports("song.mp3") is True
    assert d.supports("song.xyz") is False
    assert ".wav" in d.codecs()


def test_network_driver_online_is_bool():
    d = NetworkDriver()
    d.probe()
    assert isinstance(d.online(), bool)
