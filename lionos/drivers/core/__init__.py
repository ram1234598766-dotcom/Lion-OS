"""Core (real) drivers."""
from .display import DisplayDriver
from .audio import AudioDriver
from .input import InputDriver
from .media import MediaDriver
from .network import NetworkDriver

CORE_DRIVERS = [DisplayDriver, AudioDriver, InputDriver, MediaDriver, NetworkDriver]

__all__ = ["DisplayDriver", "AudioDriver", "InputDriver", "MediaDriver",
           "NetworkDriver", "CORE_DRIVERS"]
