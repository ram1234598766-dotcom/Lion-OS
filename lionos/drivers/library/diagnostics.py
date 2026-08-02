"""Diagnostics/power/environment library drivers."""
import json
import time

from ..framework import Driver


class LoopbackTest(Driver):
    name = "loopback"
    category = "diagnostics"
    description = "Route output back to input"
    def probe(self):
        return True
    def echo(self, data):
        return data


class ThermalSensor(Driver):
    name = "thermal"
    category = "diagnostics"
    description = "Heat from real CPU load"
    config_defaults = {"base": 40.0}
    def probe(self):
        return True
    def temp(self, load_pct=0.0):
        return round(self.config["base"] + load_pct * 0.6, 1)


class UpsDriver(Driver):
    name = "ups"
    category = "diagnostics"
    description = "Real battery via psutil"
    def probe(self):
        return True
    def battery_pct(self):
        try:
            import psutil
            b = psutil.sensors_battery()
            return b.percent if b else 100
        except Exception:
            return 100


class LedBar(Driver):
    name = "led_bar"
    category = "diagnostics"
    description = "Taskbar/title alert flash"
    config_defaults = {"flash": False}
    def probe(self):
        return True
    def flash(self, on):
        self.config["flash"] = on


class BarcodeScanner(Driver):
    name = "barcode"
    category = "diagnostics"
    simulated = True
    description = "Decode image files (pyzbar if present)"
    def probe(self):
        return True


class CrashDump(Driver):
    name = "crash_dump"
    category = "diagnostics"
    description = "Write a text dump on fatal error"
    def probe(self):
        return True
    def dump(self, path, text):
        with open(path, "w") as f:
            f.write(text)
        return path


class CoreDumpEvent(Driver):
    name = "core_dump"
    category = "diagnostics"
    description = "Snapshot variables at crash instant"
    def probe(self):
        return True
    def snapshot(self, **vars_):
        return dict(vars_)


class Watchdog(Driver):
    name = "watchdog"
    category = "diagnostics"
    description = "Reboot OS if no feed for N sec"
    config_defaults = {"timeout": 10.0}
    def __init__(self, config=None):
        super().__init__(config)
        self._last = time.time()
    def probe(self):
        return True
    def feed(self):
        self._last = time.time()
    def tripped(self):
        return time.time() - self._last > self.config["timeout"]


class PowerMeter(Driver):
    name = "power_meter"
    category = "diagnostics"
    description = "Track virtual power consumption"
    def __init__(self, config=None):
        super().__init__(config)
        self._wh = 0.0
    def probe(self):
        return True
    def consume(self, watts, dt):
        self._wh += watts * dt


class SatelliteLink(Driver):
    name = "satellite"
    category = "diagnostics"
    simulated = True
    description = "Latency/dropout/Doppler sim"
    config_defaults = {"latency_ms": 400}
    def probe(self):
        return True


class GpsProvider(Driver):
    name = "gps"
    category = "environment"
    simulated = True
    description = "Mock coordinates / IP lookup"
    config_defaults = {"lat": 12.97, "lon": 77.59}
    def probe(self):
        return True
    def location(self):
        return (self.config["lat"], self.config["lon"])


class GyroAccel(Driver):
    name = "gyro"
    category = "environment"
    simulated = True
    description = "Gestures to motion/tilt"
    def probe(self):
        return True


class AmbientLight(Driver):
    name = "ambient_light"
    category = "environment"
    description = "Hour to brightness/theme hint"
    def probe(self):
        return True
    def brightness(self, hour):
        return 0.2 if 0 <= hour < 6 else 1.0


class ServoActuator(Driver):
    name = "servo"
    category = "environment"
    simulated = True
    description = "Commands to mock mechanical steps"
    def probe(self):
        return True


class TelemetryAggregator(Driver):
    name = "telemetry"
    category = "environment"
    description = "Package readings to JSON"
    def probe(self):
        return True
    def dump(self, **readings):
        return json.dumps(readings)


class SmartLamp(Driver):
    name = "smart_lamp"
    category = "environment"
    description = "RGB/brightness to mock output"
    def probe(self):
        return True
    def set_rgb(self, rgb):
        return tuple(rgb)


class CashDrawer(Driver):
    name = "cash_drawer"
    category = "environment"
    description = "POS open/close + transaction log"
    def probe(self):
        return True
    def open(self):
        return True


class MagStripeReader(Driver):
    name = "mag_stripe"
    category = "environment"
    description = "Numeric card to credential form"
    def probe(self):
        return True
    def parse(self, num):
        return {"pan": num[:16], "exp": num[16:20]}


class Plotter(Driver):
    name = "plotter"
    category = "environment"
    description = "Coordinates to SVG draw-paths"
    def probe(self):
        return True
    def svg(self, points):
        path = "M" + " L".join(f"{x},{y}" for x, y in points)
        return f"<path d='{path}'/>"


class BiosLayer(Driver):
    name = "bios"
    category = "environment"
    simulated = True
    description = "Legacy boot/config interpretation"
    def probe(self):
        return True
