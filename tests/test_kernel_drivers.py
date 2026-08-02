# tests/test_kernel_drivers.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pytest
from lionos.kernel import LionOS
from lionos.drivers import build_driver_bus


def test_kernel_has_driver_bus():
    os_ = LionOS()
    assert os_.drivers is not None
    assert os_.driver_probe_lines, "no probe lines produced"


def test_probe_lines_have_expected_states():
    os_ = LionOS()
    states = {l.state for l in os_.driver_probe_lines}
    assert states.issubset({"ok", "warn", "offline", "sim"})


def test_build_driver_bus_respects_config():
    class Fake:
        show_simulated = True
    bus = build_driver_bus(Fake())
    assert len(bus.all()) > 0
    sims = [d for d in bus.all() if d.simulated]
    assert all(d.status.enabled for d in sims)  # show_simulated → enabled


def test_kernel_update_ticks_drivers():
    os_ = LionOS()
    os_._dt = 0.016
    os_._update(os_._dt)   # must not raise with drivers running
