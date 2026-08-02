# Lion-OS 2.0 "Majestic" — Phase 2 (Driver framework + auto-config + driver library) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pluggable driver framework with a bus that auto-probes, auto-tunes, and self-heals every driver at boot; 5 real core drivers (display/audio/input/media/network); a ~100-driver simulated library; and a Devices & Drivers app + kernel boot integration that make the OS "configure everything automatically."

**Architecture:** New `lionos/drivers/` package: `framework.py` (Driver base + DriverStatus + lifecycle), `bus.py` (DriverBus: dependency-ordered probe→auto_tune→init→start, device tree, enable/disable, re-probe, auto-config snapshot), `core/` (display, audio, input, media, network), `library/` (simulated drivers grouped by subsystem). The kernel probes the bus at boot (logging `[ok]`/`[warn]`/`[offline]`/`[sim]` lines) and exposes `os.drivers`. A new **Devices** app renders the device tree.

**Tech Stack:** Python 3.9+, pygame-ce, stdlib (`os`, `io`, `hashlib`, `json`, `threading`, `subprocess`, `multiprocessing.shared_memory`), psutil/requests (already deps).

## Global Constraints

- Python `>=3.9`; **no new runtime dependencies**. Optional backends (numpy, pyttsx3, opencv, camera) activate only if importable — never required.
- Keep all 56 existing tests + `python -m lionos --headless` green after every task.
- Every driver degrades gracefully: absent hardware/backend ⇒ `available=False`, all ops no-op, never raises.
- Simulated drivers ship **off by default** (`simulated=True` → `enabled=False` unless user enables) and are gated by `show_simulated` in the Devices app.
- Test on Windows via `py -3 -m pytest tests/ -q` (never `python3`).
- Use the `Driver`/`DriverStatus`/`DriverBus` APIs defined in Task 1 exactly — later tasks rely on them.

---

### Task 1: Driver framework (`framework.py`)

**Files:**
- Create: `lionos/drivers/__init__.py` (empty package init re-exporting framework/bus)
- Create: `lionos/drivers/framework.py`
- Test: `tests/test_driver_framework.py` (new)

**Interfaces:**
- Produces:
  - `class DriverStatus` (dataclass): `available: bool`, `enabled: bool`, `running: bool`, `health: int` (0-100), `detail: str`, `last_error: str = ""`.
  - `class Driver` (base):
    - class attrs: `name: str`, `category: str`, `simulated: bool = False`, `depends: list[str] = []`, `description: str = ""`, `config_defaults: dict = {}`.
    - `__init__(self, config: dict | None = None)` → sets `self.config = {**config_defaults, **(config or {})}`, `self.status = DriverStatus(enabled=not self.simulated, ...)`.
    - lifecycle: `probe(self) -> bool`, `init(self) -> None`, `start(self) -> None`, `stop(self) -> None`, `update(self, dt: float) -> None`, `auto_tune(self) -> dict` (returns recommended config), `configure(self, cfg: dict) -> None` (merges + applies), `diagnose(self) -> str`.
    - `_mark(status, **kw)` helper.
    - every method default no-op/`True` except where overridden.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_driver_framework.py -v` → ImportError.

- [ ] **Step 3: Implement `framework.py`**

```python
"""Driver framework for Lion-OS.

A ``Driver`` declares a name/category/dependencies and a lifecycle:
``probe -> init -> start -> update -> stop``. Drivers auto-tune their own
config from ``probe()`` results, degrade gracefully when hardware/backends are
absent, and report ``DriverStatus`` for the Devices app and System Health.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class DriverStatus:
    available: bool = True
    enabled: bool = True
    running: bool = False
    health: int = 100
    detail: str = ""
    last_error: str = ""

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ("available", "enabled", "running", "health", "detail", "last_error")}


class Driver:
    name: str = "driver"
    category: str = "generic"
    simulated: bool = False
    depends: List[str] = []
    description: str = ""
    config_defaults: Dict = {}

    def __init__(self, config: Optional[dict] = None):
        self.config: Dict = {**self.config_defaults, **(config or {})}
        self.status = DriverStatus(enabled=not self.simulated)

    # -- lifecycle (override in subclasses) ----------------------------------
    def probe(self) -> bool:
        """Detect whether the underlying hardware/backend exists. Return True
        if available (or for simulations). Auto-configures from the result."""
        return True

    def init(self) -> None:
        """Initialize resources. Raise on hard failure (bus catches + heals)."""

    def start(self) -> None:
        self.status.running = True

    def stop(self) -> None:
        self.status.running = False

    def update(self, dt: float) -> None:
        """Per-frame tick, called by the kernel loop for running drivers."""

    def auto_tune(self) -> dict:
        """Return recommended config derived from probe() (called by the bus)."""
        return {}

    def configure(self, cfg: dict) -> None:
        """Merge + apply manual configuration (wins over auto-tuned values)."""
        self.config.update(cfg)

    def diagnose(self) -> str:
        """One-line human-readable status detail (used by the Devices app)."""
        return self.status.detail

    # -- helpers --------------------------------------------------------------
    def _set(self, **kw) -> None:
        for k, v in kw.items():
            setattr(self.status, k, v)

    def _error(self, msg: str) -> None:
        self.status.available = False
        self.status.running = False
        self.status.health = 0
        self.status.last_error = msg
```

- [ ] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_driver_framework.py -v` → 5 passed.

- [ ] **Step 5: Create `lionos/drivers/__init__.py`**

```python
"""Driver framework + driver library for Lion-OS.

The kernel probes a DriverBus at boot; drivers auto-configure themselves and
degrade gracefully. See ``bus.py`` and ``framework.py``.
"""
from .framework import Driver, DriverStatus

__all__ = ["Driver", "DriverStatus"]
```

- [ ] **Step 6: Commit**

```bash
git add lionos/drivers/framework.py lionos/drivers/__init__.py tests/test_driver_framework.py
git commit -m "feat(drivers): Driver framework + DriverStatus lifecycle"
```

---

### Task 2: Driver bus (`bus.py`)

**Files:**
- Create: `lionos/drivers/bus.py`
- Test: `tests/test_driver_bus.py` (new)

**Interfaces:**
- Consumes: `Driver`, `DriverStatus` (Task 1).
- Produces:
  - `BootProbeLine` (dataclass): `name, state, detail`; `state ∈ {"ok","warn","offline","sim"}`.
  - `class DriverBus`:
    - `__init__(self, drivers: list[Driver])`
    - `register(driver)` / `all() -> list[Driver]` (dependency-ordered)
    - `probe_all() -> list[BootProbeLine]` (probe → auto_tune → apply → init → start; logs each)
    - `get(name) -> Driver | None`, `by_category() -> dict[str, list[Driver]]`
    - `enable(name) / disable(name)`, `re_probe(name)`
    - `update(dt)` (tick all running)
    - `device_tree() -> list[dict]` (for the Devices app)
    - `auto_config_snapshot() -> dict` (written to `drivers.auto.json`)
    - `stop_all()`

- [ ] **Step 1: Write the failing test**

```python
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
    assert "base" in snap and snap["base"]["name"] == "base"
```

- [ ] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_driver_bus.py -v` → ImportError.

- [ ] **Step 3: Implement `bus.py`**

```python
"""Driver bus: registers drivers, orders by dependency, probes/auto-tunes/init/
starts them at boot, and exposes a device tree + auto-config snapshot."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .framework import Driver, DriverStatus


@dataclass
class BootProbeLine:
    name: str
    state: str      # ok | warn | offline | sim
    detail: str = ""


class DriverBus:
    def __init__(self, drivers: Optional[List[Driver]] = None):
        self._drivers: Dict[str, Driver] = {}
        for d in drivers or []:
            self.register(d)
        self._boot_time = time.time()

    # -- registration --------------------------------------------------------
    def register(self, driver: Driver) -> None:
        self._drivers[driver.name] = driver

    def get(self, name: str) -> Optional[Driver]:
        return self._drivers.get(name)

    def all(self) -> List[Driver]:
        names = self._topo()
        return [self._drivers[n] for n in names]

    def by_category(self) -> Dict[str, List[Driver]]:
        out: Dict[str, List[Driver]] = {}
        for d in self.all():
            out.setdefault(d.category, []).append(d)
        return out

    def _topo(self) -> List[str]:
        """Dependency-ordered names (parents before children)."""
        visited, order = set(), []

        def visit(name):
            if name in visited:
                return
            visited.add(name)
            d = self._drivers.get(name)
            if d:
                for dep in d.depends:
                    visit(dep)
                order.append(name)

        for n in self._drivers:
            visit(n)
        return order

    # -- lifecycle ------------------------------------------------------------
    def probe_all(self) -> List[BootProbeLine]:
        lines = []
        for d in self.all():
            if not d.status.enabled:
                lines.append(BootProbeLine(d.name, "offline", "disabled"))
                continue
            try:
                ok = d.probe()
            except Exception as e:                      # pragma: no cover
                d._error(f"probe failed: {e}")
                ok = False
            if not ok:
                d.status.available = False
                lines.append(BootProbeLine(d.name, "offline", "not detected"))
                continue
            # auto-tune: manual overrides win over auto values
            tuned = d.auto_tune() or {}
            d.configure(tuned)
            try:
                d.init()
                d.start()
                d._set(available=True, running=True, health=100,
                       detail=d.diagnose() or "ok", last_error="")
            except Exception as e:
                d._error(str(e))
                lines.append(BootProbeLine(d.name, "warn", f"init failed: {e}"))
                continue
            state = "sim" if d.simulated else "ok"
            lines.append(BootProbeLine(d.name, state, d.diagnose() or "ok"))
        return lines

    def re_probe(self, name: str) -> BootProbeLine:
        d = self.get(name)
        if d is None:
            return BootProbeLine(name, "warn", "unknown driver")
        d.stop()
        d.status = DriverStatus(enabled=not d.simulated)
        lines = self.probe_all()
        return next((l for l in lines if l.name == name),
                    BootProbeLine(name, "warn", "no line"))

    def enable(self, name: str) -> None:
        d = self.get(name)
        if d:
            d.status.enabled = True

    def disable(self, name: str) -> None:
        d = self.get(name)
        if d:
            d.stop()
            d.status.enabled = False
            d.status.running = False

    def update(self, dt: float) -> None:
        for d in self.all():
            if d.status.running:
                try:
                    d.update(dt)
                except Exception:
                    pass

    def stop_all(self) -> None:
        for d in self.all():
            try:
                d.stop()
            except Exception:
                pass

    # -- reporting ------------------------------------------------------------
    def device_tree(self) -> List[dict]:
        out = []
        for cat, drivers in self.by_category().items():
            out.append({
                "category": cat,
                "drivers": [{
                    "name": d.name,
                    "status": d.status.to_dict(),
                    "simulated": d.simulated,
                    "description": d.description,
                    "config": dict(d.config),
                } for d in drivers],
            })
        return out

    def auto_config_snapshot(self) -> dict:
        return {
            "written_at": time.time(),
            "drivers": {d.name: {"name": d.name, "config": dict(d.config)}
                        for d in self.all()},
        }
```

- [ ] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_driver_bus.py -v` → 5 passed.

- [ ] **Step 5: Commit**

```bash
git add lionos/drivers/bus.py tests/test_driver_bus.py
git commit -m "feat(drivers): DriverBus with dependency order + auto-config + device tree"
```

---

### Task 3: Core drivers (display, audio, input, media, network)

**Files:**
- Create: `lionos/drivers/core/__init__.py` (empty), `lionos/drivers/core/display.py`,
  `audio.py`, `input.py`, `media.py`, `network.py`
- Test: `tests/test_core_drivers.py` (new)

**Interfaces:**
- Consumes: `Driver`, `DriverBus` (Tasks 1-2).
- Produces the 5 core driver classes (registered by the bus; wired to the kernel in Task 5):
  - `DisplayDriver` (`name="display"`, category="core") — `probe()` returns True; `auto_tune()` suggests `{"vsync": config.vsync, "resolution": ...}`; `diagnose()` reports the SDL driver name + resolution.
  - `AudioDriver` (`name="audio"`) — `probe()` tries `pygame.mixer.get_init()` after a guarded `pygame.mixer.init()`; returns False on no device. Methods: `play_sfx(id)`, `play_music(path)`, `stop_music()`, `set_volume(v)`, `mute()/unmute()`. `auto_tune()` returns `{"volume": config.volume}`. All methods no-op when unavailable.
  - `InputDriver` (`name="input"`) — reports keyboard/mouse present; optional `gamepad` support (probes `pygame.joystick.get_count()`).
  - `MediaDriver` (`name="media"`) — `supports(path)` by extension; `open_audio(path)` uses `pygame.mixer.music.load`; `codecs()` returns supported list.
  - `NetworkDriver` (`name="network"`) — `probe()` returns True (even offline); `online()` does a cached connectivity check; `auto_tune()` returns `{"offline_ok": True}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_core_drivers.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pytest
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
    assert "wav" in d.codecs()


def test_network_driver_online_is_bool():
    d = NetworkDriver()
    d.probe()
    assert isinstance(d.online(), bool)
```

- [ ] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_core_drivers.py -v` → ImportError.

- [ ] **Step 3: Implement the 5 core drivers**

`lionos/drivers/core/display.py`:

```python
"""Display driver — video-driver selection, mode, vsync info."""
from __future__ import annotations
import os
import pygame
from ..framework import Driver


class DisplayDriver(Driver):
    name = "display"
    category = "core"
    description = "Video output (windowed/fullscreen, vsync)"

    def probe(self) -> bool:
        self._driver = pygame.display.get_driver()
        info = pygame.display.Info()
        self._res = (info.current_w, info.current_h)
        return True

    def auto_tune(self) -> dict:
        return {"vsync": False, "fullscreen": False}

    def diagnose(self) -> str:
        return f"{self._driver} @ {self._res}"
```

`lionos/drivers/core/audio.py`:

```python
"""Audio driver — guarded mixer init, volume, SFX, music."""
from __future__ import annotations
import pygame
from ..framework import Driver


class AudioDriver(Driver):
    name = "audio"
    category = "core"
    description = "Audio output (mixer, volume, music)"

    def probe(self) -> bool:
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.pre_init(44100, -16, 2, 512)
                pygame.mixer.init()
        except pygame.error:
            self._set(available=False, detail="no audio device")
            return False
        self._set(available=True, detail="ok")
        return True

    def auto_tune(self) -> dict:
        return {"volume": 0.8, "muted": False}

    def _mixer(self):
        return self.status.available and pygame.mixer.get_init() is not None

    def set_volume(self, v: float) -> None:
        self.config["volume"] = max(0.0, min(1.0, v))
        if self._mixer():
            pygame.mixer.music.set_volume(self.config["volume"] * (0.0 if self.config.get("muted") else 1.0))

    def mute(self): self.config["muted"] = True; self.set_volume(self.config["volume"])
    def unmute(self): self.config["muted"] = False; self.set_volume(self.config["volume"])

    def play_sfx(self, sound_id: str) -> None:
        if not self._mixer():
            return
        # minimal generated blip so SFX need no asset files
        import array, math
        sr = 44100
        dur = 0.08
        freq = {"boot": 440, "open": 660, "close": 330, "toast": 520,
                "screenshot": 780, "error": 180}.get(sound_id, 440)
        n = int(sr * dur)
        buf = array.array("h", (int(12000 * math.sin(2 * math.pi * freq * i / sr))
                                for i in range(n)))
        snd = pygame.mixer.Sound(buffer=buf)
        snd.set_volume(self.config["volume"])
        snd.play()

    def play_music(self, path: str) -> None:
        if self._mixer():
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()

    def stop_music(self) -> None:
        if self._mixer():
            pygame.mixer.music.stop()

    def diagnose(self) -> str:
        return "no device" if not self.status.available else "ok"
```

`lionos/drivers/core/input.py`:

```python
"""Input driver — keyboard/mouse + optional gamepad."""
from __future__ import annotations
import pygame
from ..framework import Driver


class InputDriver(Driver):
    name = "input"
    category = "core"
    description = "Keyboard / mouse / gamepad"

    def probe(self) -> bool:
        self._gamepads = pygame.joystick.get_count() if hasattr(pygame, "joystick") else 0
        return True

    def auto_tune(self) -> dict:
        return {"gamepad": self._gamepads > 0}

    def diagnose(self) -> str:
        pads = f", {self._gamepads} gamepad(s)" if self._gamepads else ""
        return f"keyboard+mouse{pads}"
```

`lionos/drivers/core/media.py`:

```python
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

    def probe(self) -> bool:
        self._video = False
        try:
            import importlib.util
            self._video = any(importlib.util.find_spec(m) for m in ("av", "imageio_ffmpeg", "cv2"))
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
```

`lionos/drivers/core/network.py`:

```python
"""Network driver — cached connectivity probe."""
from __future__ import annotations
import time
from ..framework import Driver


class NetworkDriver(Driver):
    name = "network"
    category = "core"
    description = "Network connectivity"

    def __init__(self, config=None):
        super().__init__(config)
        self._last = 0.0
        self._cached = False

    def probe(self) -> bool:
        self._set(available=True, detail="unknown")
        return True

    def online(self) -> bool:
        now = time.time()
        if now - self._last < 2.0:
            return self._cached
        self._last = now
        self._cached = self._check()
        return self._cached

    def _check(self) -> bool:
        try:
            import urllib.request
            urllib.request.urlopen("https://pypi.org", timeout=2)
            return True
        except Exception:
            return False

    def diagnose(self) -> str:
        return "online" if self.online() else "offline"
```

`lionos/drivers/core/__init__.py`:

```python
"""Core (real) drivers."""
from .display import DisplayDriver
from .audio import AudioDriver
from .input import InputDriver
from .media import MediaDriver
from .network import NetworkDriver

CORE_DRIVERS = [DisplayDriver, AudioDriver, InputDriver, MediaDriver, NetworkDriver]
```

- [ ] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_core_drivers.py -v` → 5 passed.

- [ ] **Step 5: Commit**

```bash
git add lionos/drivers/core/ tests/test_core_drivers.py
git commit -m "feat(drivers): 5 real core drivers (display/audio/input/media/network)"
```

---

### Task 4: Driver library part 1 — storage & compute

**Files:**
- Create: `lionos/drivers/library/__init__.py`, `lionos/drivers/library/storage.py`, `lionos/drivers/library/compute.py`
- Test: `tests/test_library_storage_compute.py` (new)

**Interfaces:**
- Consumes: `Driver`.
- Produces the first two library modules. Each driver is a small `Driver` subclass; `simulated=False` where genuinely functional, `True` otherwise. All `probe()` return True (they "work" without hardware), unless the backend (e.g. numpy) is missing.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_library_storage_compute.py
from lionos.drivers.library.storage import NVMeDriver, RamDiskDriver, RaidDriver, FloppyDriver
from lionos.drivers.library.compute import FPUDriver, RNGDriver


def test_nvme_read_write():
    d = NVMeDriver()
    d.probe()
    d.write(b"hello")
    assert d.read() == b"hello"


def test_ramdisk_wiped_on_reinit():
    d = RamDiskDriver()
    d.probe()
    d.write(b"x")
    d2 = RamDiskDriver()
    assert d2.read() == b""


def test_floppy_size_cap():
    d = FloppyDriver()
    assert d.max_size == 1_474_560


def test_fpu_accel():
    d = FPUDriver()
    assert d.sqrt(9) == 3.0


def test_rng_entropy():
    d = RNGDriver()
    d.probe()
    assert len(d.random_bytes(16)) == 16
```

- [ ] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_library_storage_compute.py -v` → ImportError.

- [ ] **Step 3: Implement the two modules**

`lionos/drivers/library/storage.py`:

```python
"""Storage drivers — in-memory block stores, RAID striping, caps."""
from __future__ import annotations
import io
from ..framework import Driver


class NVMeDriver(Driver):
    name = "nvme"
    category = "storage"
    description = "High-speed in-memory block store"
    config_defaults = {"size": 1 << 20}

    def __init__(self, config=None):
        super().__init__(config)
        self._disk = io.BytesIO()

    def probe(self): return True
    def write(self, data: bytes): self._disk.seek(0); self._disk.write(data)
    def read(self) -> bytes: self._disk.seek(0); return self._disk.read()
    def diagnose(self): return f"{self.config['size'] // 1024} KiB"


class RamDiskDriver(Driver):
    name = "ramdisk"
    category = "storage"
    description = "Volatile RAM disk, wiped on reboot"
    config_defaults = {"size": 1 << 20}

    def __init__(self, config=None):
        super().__init__(config)
        self._disk = io.BytesIO()

    def probe(self): return True
    def write(self, data: bytes): self._disk.seek(0); self._disk.write(data)
    def read(self) -> bytes: self._disk.seek(0); return self._disk.read()
    def diagnose(self): return "volatile"


class RaidDriver(Driver):
    name = "raid"
    category = "storage"
    description = "Stripes virtual data across host folders"
    config_defaults = {"mirror": True}

    def __init__(self, config=None):
        super().__init__(config)
        self._parts = []

    def probe(self): return True
    def write(self, data: bytes):
        half = len(data) // 2
        self._parts = [data[:half], data[half:]]
    def read(self) -> bytes:
        return (self._parts[0] + self._parts[1]) if len(self._parts) == 2 else b""


class FloppyDriver(Driver):
    name = "floppy"
    category = "storage"
    simulated = True
    description = "3.5\" floppy — 1.44 MB caps"
    max_size = 1_474_560

    def probe(self): return True
    def fits(self, size: int) -> bool: return size <= self.max_size
    def diagnose(self): return "1.44 MB"


class TapeDriver(Driver):
    name = "tape"
    category = "storage"
    simulated = True
    description = "Sequential-only archival tape"
    def probe(self): return True


class SanDriver(Driver):
    name = "san"
    category = "storage"
    description = "Treat host folders as drives"
    def probe(self): return True
```

`lionos/drivers/library/compute.py`:

```python
"""Compute drivers — math accel, RNG, quantum sim."""
from __future__ import annotations
import math
import os
from ..framework import Driver


class FPUDriver(Driver):
    name = "fpu"
    category = "compute"
    description = "Math co-processor (routes to math/numpy)"
    config_defaults = {"use_numpy": False}

    def probe(self):
        try:
            import numpy  # noqa
            self._numpy = True
        except Exception:
            self._numpy = False
        return True

    def sqrt(self, x): return math.sqrt(x)
    def sin(self, x): return math.sin(x)
    def diagnose(self): return "numpy" if self._numpy else "math"


class RNGDriver(Driver):
    name = "rng"
    category = "compute"
    description = "Cryptographically secure random bits"
    def probe(self): return True
    def random_bytes(self, n: int) -> bytes: return os.urandom(n)
    def int_in(self, lo, hi): return int.from_bytes(os.urandom(4), "big") % (hi - lo + 1) + lo


class QuantumDriver(Driver):
    name = "quantum"
    category = "compute"
    simulated = True
    description = "Qubit register with Hadamard/CNOT"

    def __init__(self, config=None):
        super().__init__(config)
        self.state = [1.0 + 0.0j, 0.0 + 0.0j]

    def probe(self): return True
    def hadamard(self):
        import cmath
        s = self.state
        self.state = [s[0] / math.sqrt(2) + s[1] / math.sqrt(2),
                      s[0] / math.sqrt(2) - s[1] / math.sqrt(2)]
        return self.state
    def diagnose(self): return "1-qubit"
```

`lionos/drivers/library/__init__.py`:

```python
"""Simulated driver library. Importing registers nothing; the kernel builds a
DriverBus with selected drivers (see build_driver_bus in bus.py / kernel)."""
from ..core import CORE_DRIVERS
from .storage import NVMeDriver, RamDiskDriver, RaidDriver, FloppyDriver, TapeDriver, SanDriver
from .compute import FPUDriver, RNGDriver, QuantumDriver

LIBRARY_DRIVERS = [NVMeDriver, RamDiskDriver, RaidDriver, FloppyDriver, TapeDriver,
                   SanDriver, FPUDriver, RNGDriver, QuantumDriver]
```

- [ ] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_library_storage_compute.py -v` → 5 passed.

- [ ] **Step 5: Commit**

```bash
git add lionos/drivers/library/ tests/test_library_storage_compute.py
git commit -m "feat(drivers): storage + compute library drivers"
```

---

### Task 5: Driver library part 2 — remaining modules (pattern + registry)

**Files:**
- Create: `lionos/drivers/library/input_dev.py`, `audio_media.py`, `graphics_display.py`,
  `network.py`, `security.py`, `diagnostics.py`, `power_env.py`, `ipc_host.py`,
  `cloud_dist.py`, `virtualization.py`, `enterprise.py`, `compliance.py`,
  `dev_tools.py`, `ai_compute.py`, `iot_robotics.py`, `esoteric.py`
- Modify: `lionos/drivers/library/__init__.py` (register all)
- Test: `tests/test_library_all.py` (new) — every library driver probes + reports status without error.

**Interfaces:**
- Consumes: `Driver` (Task 1), the module pattern from Task 4.
- Produces every remaining driver from the spec's **Appendix A** catalog. Each is a small `Driver` subclass with `name`, `category`, `simulated`, `description`, `probe() -> True` (or backend guard), and one representative method/behavior. Simulated drivers default disabled.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_library_all.py -v` → ImportError / count fails.

- [ ] **Step 3: Implement the modules**

Each module follows this exact pattern (drivers are compact; a few lines each).
Implement ALL of the following (they mirror Appendix A's catalog):

- `input_dev.py`: `BrailleProxy`, `Touchscreen`, `StylusTablet`, `SpeechToText` (S, guards on mic libs), `HotasJoystick`, `MidiKeyboard` (S).
- `audio_media.py`: `SoundBlasterMidi` (tone synth via math), `PcmDecoder` (parse WAV header, `io.BytesIO`), `VideoFrameDecoder` (S), `CameraCapture` (S, tries `cv2`/`opencv`), `TtsSpeech` (S, tries `pyttsx3`), `RomLoader` (S).
- `graphics_display.py`: `DisplaySwitcher` (S), `RefreshController` (uses `pygame.display.get_driver`), `AsciiRasterizer` (real: map glyphs to ascii), `UiScaling` (S), `EinkDisplay` (S), `Haptics` (S), `Oscilloscope` (S).
- `network.py`: `WifiCard` (S), `FirewallRules` (real: allow/deny list on "packets"), `DhcpClient` (assigns a virtual IP), `VpnTunnel` (S), `ProxyGateway` (S), `PacketSniffer` (real: hex dump of logged packets), `CdnCache` (real: in-memory dict cache), `P2pDiscovery` (S), `LoadBalancer` (real: round-robin worker index), `MeshRouter` (S), `GraphqlClient` (S), `EdgeCompute` (S), `WebrtcStream` (S), `SshDaemon` (S, real socket server guarded), `ContainerRegistry` (real: dict of scripts).
- `security.py`: `Fingerprint` (real: hash a key file), `SmartCard` (real: require a key file token), `SecureRNG` (real: `os.urandom` — note distinct from compute.RNG; keep both), `Sandbox` (real: restricted `exec` with empty builtins), `CaStore` (real: in-memory cert dict), `IdsScanner` (real: deny-list scan of log lines), `KeyLogger` (real: append to audit ledger), `AclManager` (real: role→permission map), `VulnSimulator` (S), `MemoryScrubber` (real: zero buffers), `AntiTamper` (real: sha256 core files on start), `GdprScrubber` (real: drop PII rows), `BlackBox` (real: ring buffer of last N commands).
- `diagnostics.py`: `LoopbackTest` (real: echo), `ThermalSensor` (real: heat from `psutil.cpu_percent`), `UpsDriver` (real: `psutil.sensors_battery`), `LedBar` (real: flash taskbar/title — stores a flag), `BarcodeScanner` (S: decode simple QR via `pyzbar` if present), `CrashDump` (real: write a text dump file), `CoreDumpEvent` (real: snapshot a dict), `Watchdog` (real: background thread reboots if no `feed()` for N sec), `PowerMeter` (real: cumulative "watt-hours" from update ticks), `SatelliteLink` (S: latency/dropout sim), `GpsProvider` (S/mock coords), `GyroAccel` (S: gesture→tilt), `AmbientLight` (real: hour→brightness), `ServoActuator` (S), `TelemetryAggregator` (real: collect→JSON), `SmartLamp` (real: RGB→file), `CashDrawer` (real: POS log), `MagStripeReader` (real: numeric string→credential dict), `Plotter` (real: coords→SVG text), `BiosLayer` (S).
- `ipc_host.py`: `HostClipboard` (real: `pyperclip` if present, else `tkinter`-guarded, else no-op), `SharedMemoryIpc` (real: `multiprocessing.shared_memory` guarded), `SubprocessPipe` (real: `subprocess.run` capture), `DemuxSignal` (real: split a combined stream), `Hypervisor` (S: spawn/freeze guest Driver instances), `Vswitch` (S), `Kubelet` (real: read a manifest dict → desired state), `BusMaster` (real: priority queue of (prio, data)).
- `enterprise.py`: `JobQueue` (real: priority batch queue), `FpgaLoader` (S: parse config text), `SymbolicDebugger` (S: store breakpoints), `SshDaemon` (see network), `TimeMachineBackup` (real: zip a folder), `NvmeOverFabrics` (S).
- `compliance.py`: (GdprScrubber lives in security) + `AuditLedger` (real: append-only log).
- `dev_tools.py`: `JitProxy` (real: tokenize + `exec` with sandbox flag), `MacroRecorder` (real: record/replay key list), `SymbolicDebugger` (see enterprise), `SshDaemon` (see network).
- `ai_compute.py`: `NpuEmulator` (S: tries `ollama`/`transformers`), `VectorAccelerator` (real: `memoryview` sum).
- `iot_robotics.py`: `GpsProvider`, `GyroAccel`, `ServoActuator`, `SmartLamp`, `CashDrawer`, `MagStripeReader`, `Plotter` (see diagnostics).
- `esoteric.py`: `EinkDisplay`, `Haptics`, `Oscilloscope`, `FpgaLoader`, `SatelliteLink`, `Quantum` (see compute).

> The plan does not enumerate every 100 lines of boilerplate here; the pattern
> is fixed by Task 4's modules. Implement all names above, each 5-15 lines,
> following that pattern exactly. Update `LIBRARY_DRIVERS` in
> `library/__init__.py` to include every class. `test_library_driver_registry_count`
> enforces ≥60 drivers.

- [ ] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_library_all.py -v` → 3 passed.

- [ ] **Step 5: Commit**

```bash
git add lionos/drivers/library/ tests/test_library_all.py
git commit -m "feat(drivers): full simulated driver library (storage→esoteric)"
```

---

### Task 6: Kernel boot integration + auto-config engine

**Files:**
- Modify: `lionos/kernel.py`, `lionos/drivers/bus.py` (add `write_auto_config`), `lionos/config.py` (add `show_simulated` default)
- Test: `tests/test_kernel_drivers.py` (new, headless)

**Interfaces:**
- Consumes: `DriverBus`, `CORE_DRIVERS`, `LIBRARY_DRIVERS`, `BootProbeLine` (Tasks 1-5).
- Produces:
  - `build_driver_bus(config) -> DriverBus` in `lionos/drivers/__init__.py` — instantiates core + library drivers, applies `config.drivers.<name>` overrides, disables simulated ones unless `config.show_simulated`.
  - `LionOS.drivers: DriverBus`; `LionOS.driver_probe_lines: list[BootProbeLine]`.
  - Kernel `_update` calls `self.drivers.update(dt)` each frame.
  - On `config.show_fps` (existing) the boot screen also prints probe lines; Devices app (Task 7) reads `os.drivers.device_tree()`.
  - `LionOS._write_driver_auto_config()` writes `~/.lionos/drivers.auto.json`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_kernel_drivers.py -v` → ImportError (`build_driver_bus`).

- [ ] **Step 3: Implement**

`lionos/drivers/__init__.py` (extend):

```python
from .framework import Driver, DriverStatus
from .bus import DriverBus, BootProbeLine
from .core import CORE_DRIVERS
from .library import LIBRARY_DRIVERS

__all__ = ["Driver", "DriverStatus", "DriverBus", "BootProbeLine",
           "CORE_DRIVERS", "LIBRARY_DRIVERS", "build_driver_bus"]


def build_driver_bus(config=None) -> DriverBus:
    """Instantiate every driver, apply config overrides, and build a bus.
    Simulated drivers are disabled unless show_simulated is set."""
    overrides = {}
    if config is not None:
        overrides = getattr(config, "drivers", {}) or {}
    show_sim = bool(getattr(config, "show_simulated", False))
    bus = DriverBus()
    for cls in CORE_DRIVERS + LIBRARY_DRIVERS:
        d = cls(config=overrides.get(cls.name))
        if d.simulated and not show_sim:
            d.status.enabled = False
        bus.register(d)
    return bus
```

`lionos/config.py` — add default: `show_simulated: bool = False`.

`lionos/kernel.py`:
- import: `from .drivers import DriverBus, build_driver_bus`
- in `__init__`, after `self.icon_cache` etc.:

```python
        self.drivers = build_driver_bus(self.config)
        self.driver_probe_lines = self.drivers.probe_all()
        self._write_driver_auto_config()
```

- add method:

```python
    def _write_driver_auto_config(self):
        try:
            from .config import ensure_config_dir
            import json, os
            snap = self.drivers.auto_config_snapshot()
            with open(os.path.join(ensure_config_dir(), "drivers.auto.json"), "w") as f:
                json.dump(snap, f, indent=2)
        except Exception:
            pass
```

- in `_update`, after stepping windows (anywhere in the logged-in path), add:

```python
        self.drivers.update(dt)
```

- [ ] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_kernel_drivers.py -v` → 4 passed. Then full suite + smoke.

- [ ] **Step 5: Commit**

```bash
git add lionos/drivers/__init__.py lionos/drivers/bus.py lionos/kernel.py lionos/config.py tests/test_kernel_drivers.py
git commit -m "feat(drivers): kernel boots driver bus + auto-config snapshot"
```

---

### Task 7: Devices & Drivers app

**Files:**
- Create: `lionos/apps/devices.py`, `lionos/apps/__init__.py` (register + `AUTO_LAUNCH` unchanged)
- Test: `tests/test_devices_app.py` (new, headless)

**Interfaces:**
- Consumes: `LionOS.drivers.device_tree()`, the `App` base.
- Produces: `DevicesApp` (`name="Devices"`, `icon="Devices"` — already in `APP_ICONS`), rendering the device tree grouped by category with status badges, `[Enable/Disable]`, `[Re-probe]`, and a search box.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_devices_app.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pytest
from lionos.kernel import LionOS
from lionos.apps import get_apps


def test_devices_app_registered():
    assert any(c.name == "Devices" for c in get_apps())


def test_devices_app_launches_and_draws():
    os_ = LionOS()
    os_._no_draw = False
    for _ in range(800):
        os_._dt = 0.016
        os_._update(os_._dt)
        if os_.booted and os_.logged_in:
            break
    os_._do_login()
    inst = os_.launch("Devices")
    for _ in range(4):
        os_._dt = 0.016
        os_._update(os_._dt)
    assert inst.hydrated
    os_._needs_redraw = True
    os_._draw()
    import pygame
    pygame.display.flip()
```

- [ ] **Step 2: Run to verify it fails** — `py -3 -m pytest tests/test_devices_app.py -v` → FAIL (not registered).

- [ ] **Step 3: Implement `lionos/apps/devices.py`**

```python
"""Devices & Drivers app — renders the driver device tree with controls."""
from __future__ import annotations

import pygame

from .base import App, registry
from ..widgets import draw_glass_panel, cached_font


class DevicesApp(App):
    name = "Devices"
    icon = "Devices"
    category = "System"
    description = "Driver bus device tree, status, enable/disable, re-probe"
    default_w = 860
    default_h = 560
    resizable = True
    min_w = 560
    min_h = 360

    def on_open(self):
        self._search = ""
        self._msg = ""

    def _rows(self):
        tree = self.os.drivers.device_tree()
        rows = []
        for group in tree:
            for drv in group["drivers"]:
                name = drv["name"].lower()
                if self._search and self._search.lower() not in name:
                    continue
                rows.append((group["category"], drv))
        return rows

    def handle_event(self, event, local_pos):
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_BACKSPACE, pygame.K_RETURN):
            if event.key == pygame.K_BACKSPACE:
                self._search = self._search[:-1]
            return True
        if event.type == pygame.TEXTINPUT:
            self._search += event.text
            return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            self._click(local_pos)
            return True
        return False

    def _click(self, pos):
        y = 64
        row_h = 34
        for cat, drv in self._rows():
            r = pygame.Rect(12, y, self.rect.width - 24, row_h)
            if r.collidepoint(pos):
                name = drv["name"]
                action = "enable" if not drv["status"]["enabled"] else "disable"
                if pos[0] > r.right - 130:
                    self.os.drivers.enable(name) if action == "enable" else self.os.drivers.disable(name)
                    self._msg = f"{name}: {action}d"
                    self.redraw()
                elif pos[0] > r.right - 230:
                    line = self.os.drivers.re_probe(name)
                    self._msg = f"{name}: {line.state} ({line.detail})"
                    self.redraw()
            y += row_h

    def draw(self, surface, rect):
        self.rect = rect
        theme = self.theme
        draw_glass_panel(surface, rect, theme, radius=theme.radius)
        font = cached_font(16)
        title = font.render("Devices & Drivers", True, theme.text)
        surface.blit(title, (18, 16))
        search = font.render(f"Search: {self._search or '…'}", True, theme.text_dim)
        surface.blit(search, (18, 44))
        y = 64
        row_h = 34
        for cat, drv in self._rows():
            st = drv["status"]
            color = theme.success if st["running"] else (
                theme.warn if not st["enabled"] else theme.danger)
            row = pygame.Rect(12, y, rect.width - 24, row_h)
            pygame.draw.rect(surface, theme.surface_alt, row, border_radius=6)
            badge = pygame.Rect(row.x + 8, row.y + 8, 14, 14)
            pygame.draw.circle(surface, color, badge.center, 6)
            nm = font.render(drv["name"], True, theme.text)
            surface.blit(nm, (row.x + 30, row.y + 8))
            det = cached_font(13).render(st["detail"] or "", True, theme.text_dim)
            surface.blit(det, (row.x + 30 + nm.get_width() + 12, row.y + 10))
            sim = cached_font(12).render("[sim]" if drv["simulated"] else "", True, theme.text_dim)
            surface.blit(sim, (row.x + 30 + nm.get_width() + 12 + det.get_width() + 8, row.y + 10))
            rp = cached_font(13).render("Re-probe", True, theme.accent)
            surface.blit(rp, (row.right - 210, row.y + 9))
            togg = cached_font(13).render(
                "Enable" if not st["enabled"] else "Disable", True, theme.accent)
            surface.blit(togg, (row.right - 120, row.y + 9))
            y += row_h
        if self._msg:
            m = cached_font(13).render(self._msg, True, theme.info)
            surface.blit(m, (18, rect.bottom - 24))
```

Register in `lionos/apps/__init__.py` (add `devices` import + `DevicesApp` to `register_all`).

- [ ] **Step 4: Run to verify it passes** — `py -3 -m pytest tests/test_devices_app.py -v` → 2 passed. Then full suite + smoke.

- [ ] **Step 5: Commit**

```bash
git add lionos/apps/devices.py lionos/apps/__init__.py tests/test_devices_app.py
git commit -m "feat(apps): Devices & Drivers app over the driver bus"
```

---

## Self-Review notes

- **Spec coverage:** Phase 2 covers spec §6.4 (framework), §6.4.1 (auto-config engine), §6.5 (core drivers), §6.6 (simulated library), §6.7 (Devices app), and the kernel boot-probe/`drivers.auto.json` integration. Focus states (§6.3) remain Phase 4; session/persistence (§6.8+) is Phase 3.
- **No placeholders:** every Task 1-4, 6-7 step has concrete code; Task 5 lists every driver name to implement and gives the exact pattern + registry constraint (the ≥60-driver test enforces breadth). This is the one place a pattern is applied across ~100 near-identical classes rather than pasting all 100 bodies into the plan.
- **Type consistency:** `Driver`, `DriverStatus`, `BootProbeLine`, `DriverBus` (`probe_all`, `enable`, `disable`, `re_probe`, `device_tree`, `auto_config_snapshot`, `update`) are defined once (Tasks 1-2) and consumed identically in Tasks 3-7; `build_driver_bus(config)` is the single kernel entry point.
