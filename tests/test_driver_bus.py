# tests/test_driver_bus.py
from lionos.drivers.bus import DriverBus, BootProbeLine
from lionos.drivers.framework import Driver


class Base(Driver):
    name = "base"
    category = "a"


class Child(Driver):
    name = "child"
    category = "b"
    depends = ["base"]


def test_probe_all_orders_by_dependency():
    bus = DriverBus([Child(), Base()])
    names = [d.name for d in bus.all()]
    assert names.index("base") < names.index("child")


def test_probe_all_returns_probe_lines():
    bus = DriverBus([Base(), Child()])
    lines = bus.probe_all()
    assert all(isinstance(l, BootProbeLine) for l in lines)
    assert len(lines) == 2


def test_enable_disable_and_get():
    bus = DriverBus([Base()])
    bus.probe_all()
    bus.disable("base")
    assert bus.get("base").status.enabled is False
    bus.enable("base")
    assert bus.get("base").status.enabled is True


def test_device_tree_grouped():
    bus = DriverBus([Base(), Child()])
    tree = bus.device_tree()
    assert {t["category"] for t in tree} == {"a", "b"}
    assert sum(len(t["drivers"]) for t in tree) == 2


def test_auto_config_snapshot():
    bus = DriverBus([Base()])
    bus.probe_all()
    snap = bus.auto_config_snapshot()
    assert "base" in snap["drivers"] and snap["drivers"]["base"]["name"] == "base"
