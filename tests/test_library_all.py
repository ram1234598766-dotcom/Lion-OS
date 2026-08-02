# tests/test_library_all.py
from lionos.drivers.library import LIBRARY_DRIVERS


def test_all_library_drivers_probe():
    for cls in LIBRARY_DRIVERS:
        d = cls()
        assert d.probe() is True, cls.__name__
        d.init(); d.start()
        assert d.status.running is True, cls.__name__
        d.stop()


def test_library_driver_names_unique():
    names = [c.name for c in LIBRARY_DRIVERS]
    assert len(names) == len(set(names))


def test_library_driver_registry_count():
    # Appendix A defines ~100 library drivers; require a healthy fraction.
    assert len(LIBRARY_DRIVERS) >= 60
