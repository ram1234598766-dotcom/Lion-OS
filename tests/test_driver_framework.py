# tests/test_driver_framework.py
from lionos.drivers.framework import Driver, DriverStatus


class ProbeDriver(Driver):
    name = "probe"
    category = "test"
    simulated = True
    config_defaults = {"rate": 100}

    def probe(self):
        return True


def test_driver_status_defaults():
    s = DriverStatus()
    assert s.available is True and s.enabled is True and s.running is False
    assert 0 <= s.health <= 100


def test_driver_config_merges_defaults():
    d = ProbeDriver(config={"rate": 200})
    assert d.config["rate"] == 200
    assert ProbeDriver().config["rate"] == 100


def test_driver_lifecycle_returns():
    d = ProbeDriver()
    assert d.probe() is True
    d.init(); d.start(); d.stop(); d.update(0.016)
    assert d.diagnose() == ""


def test_simulated_defaults_disabled():
    d = ProbeDriver()
    assert d.status.enabled is False   # simulated → off by default


def test_configure_merges_and_applies():
    d = ProbeDriver()
    d.configure({"rate": 500})
    assert d.config["rate"] == 500
