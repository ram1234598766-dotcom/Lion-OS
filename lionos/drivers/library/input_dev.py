"""Input/accessibility library drivers."""
from ..framework import Driver


class BrailleProxy(Driver):
    name = "braille"
    category = "input"
    description = "Translates screen text into accessible blocks"
    def probe(self):
        return True
    def convert(self, text):
        return f"[braille] {text}"


class Touchscreen(Driver):
    name = "touchscreen"
    category = "input"
    description = "Maps clicks to touch events"
    def probe(self):
        return True
    def to_touch(self, pos):
        return ("touch", pos)


class StylusTablet(Driver):
    name = "stylus"
    category = "input"
    description = "Captures pen pressure/tilt"
    config_defaults = {"pressure": 1.0}
    def probe(self):
        return True


class SpeechToText(Driver):
    name = "speech_to_text"
    category = "input"
    simulated = True
    description = "Mic audio to text (guarded)"
    def probe(self):
        return True


class HotasJoystick(Driver):
    name = "hotas"
    category = "input"
    description = "Multi-axis throttle decoding"
    config_defaults = {"axes": 4}
    def probe(self):
        return True


class MidiKeyboard(Driver):
    name = "midi_keyboard"
    category = "input"
    simulated = True
    description = "A/S/D/F rows to musical notes"
    MAP = {"a": "C", "s": "D", "d": "E", "f": "F"}
    def probe(self):
        return True
    def note(self, key):
        return self.MAP.get(key.lower())
