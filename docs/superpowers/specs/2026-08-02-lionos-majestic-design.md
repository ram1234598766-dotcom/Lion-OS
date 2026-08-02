# Lion-OS 2.0 "Majestic" — Design

**Date:** 2026-08-02
**Status:** Approved (design), pending implementation plan
**Project:** Lion-OS (`C:\Users\Mrityunjay\Lion-OS`)
**Version target:** 2.0.0 (major — massive feature + polish update)

## 1. Goals

Take Lion-OS from "impressive demo" to "genuine desktop OS" that feels smooth,
personal, and powerful:

1. **Replace emoji-glyph icons with procedural vector icons** — crisp at every
   size, theme-aware, consistent across the whole shell (the headline "less
   crude" fix).
2. **Buttery 60 fps** — deterministic main loop, dirty-rect rendering, vsync,
   fixed timestep, perf counters, two-phase startup, correct cache
   invalidation.
3. **A powerful driver architecture** — a pluggable **driver bus** with a
   device tree, lifecycle (probe/init/start/stop), dependency ordering, per-driver
   config, and boot probing. 5 real core drivers (display/audio/input/media/
   network) plus a ~100-driver **simulated driver library** spanning hardware,
   network, security, diagnostics, virtualization, and esoteric interfaces —
   each graceful (never crashes when hardware/backend is absent).
4. **Real-OS persistence** — session resume (no cold blank desktop), first-boot
   wizard, activity log + recents + session summary, clipboard with history.
5. **A proper app catalog** — data-driven manifest, categorized scrollable
   launcher with descriptions + version badges, curated-first tab.
6. **Polished chrome** — notification center, sound design, wallpaper gallery +
   accent picker, workspaces, window tiling, global search, screenshots, system
   tray, statusline widgets, motion-level accessibility.
7. **New apps** — Help, System Health, Inbox (quick-capture), Today/Timeline,
   **Devices & Drivers**; **Media Player rebuilt on the media driver**.
8. **Configure everything to run smoothly** — one comprehensive Settings app and
   robust, correct config/cache plumbing with graceful degradation everywhere.

## 2. Non-goals

- **No required new runtime dependencies** (stays a pure-Python Pygame package).
  Optional backends (TTS, webcam, video codec) activate only if a library is
  present; the core never requires them.
- Simulated drivers are **architecture and telemetry**, not fake hardware claims.
  Drivers marked *simulated* may produce plausible data; they do not pretend to
  be physical devices.
- No network accounts, no cloud sync, no real multi-user security model.
- No Windows/Linux/macOS native integrations beyond what Pygame/SDL/stdlib offer.
- No restructuring of the existing 7,800-LOC architecture into new layers
  (evolutionary refactor only — see §4).

## 3. Version & codename

Bump to **2.0.0**, codename **"Majestic"**. Update `pyproject.toml`,
`lionos/__init__.py` (version/build/codename), README badges + notes.

## 4. Architecture approach

**Evolutionary refactor** of the existing structure:

- Keep `kernel.py`, `wm.py`, `widgets.py`, `theme.py`, `config.py`, `cli.py`,
  `ai/`, `apps/` and evolve them in place.
- Add focused new modules/subsystems:
  - `lionos/icons.py` — procedural vector icon renderer + per-app icon scenes.
  - `lionos/drivers/` — the **driver framework + driver library** (package):
    - `drivers/framework.py` — `Driver` base class, `DriverStatus`, lifecycle.
    - `drivers/bus.py` — `DriverBus`: registry, dependency order, probe/init/
      start/stop, device tree, re-probe, enable/disable.
    - `drivers/core/` — display, audio, input, media, network (real drivers).
    - `drivers/library/` — ~100 simulated driver modules, grouped:
      `storage.py`, `compute.py`, `input_dev.py`, `audio_media.py`,
      `graphics_display.py`, `network.py`, `security.py`, `diagnostics.py`,
      `power_env.py`, `ipc_host.py`, `cloud_dist.py`, `virtualization.py`,
      `enterprise.py`, `compliance.py`, `dev_tools.py`, `ai_compute.py`,
      `iot_robotics.py`, `esoteric.py`.
    - `drivers/__init__.py` — `DriverManager` façade.
  - `lionos/session.py` — session snapshot/restore + graceful shutdown.
  - `lionos/catalog.py` — app manifest + categorized catalog model.
  - `lionos/activity.py` — append-only JSONL activity log.
  - `lionos/sound.py` — sound theme built on the audio driver.
  - `lionos/workspaces.py` — virtual desktops (or folded into `wm.py` if small).
  - `lionos/search.py` — global search across apps/files/settings.
  - `lionos/clipboard.py` — cross-app clipboard + history.
- Keep per-frame code paths deterministic and cache-backed; animations strictly
  additive behind a motion flag.

## 5. Data files under `~/.lionos/`

| File | Purpose |
|---|---|
| `config.json` | user preferences (existing — extended with `drivers.*`) |
| `profile.json` | first-boot wizard output (name, pinned apps, what-matters) |
| `session.json` | desktop state snapshot (windows, positions, z-order, focus, theme, workspace) |
| `session-<n>.json` | last-3 crash-recovery checkpoints |
| `activity.jsonl` | append-only event stream |
| `clipboard.jsonl` | clipboard history |
| `screenshots/` | screenshot output |
| `media/` | Media Player playlists / library metadata |
| `drivers.log` | driver probe/status log |
| `drivers/<name>.json` | per-driver persistent state (EEPROM, watchdog, backups, journal) |
| `notes/`, `config.json` (existing) | unchanged |
| `logs/` | OS logs |

## 6. Workstreams (6 phases, dependency-ordered)

### Phase 1 — Foundation: icons + smoothness + tokens

#### 6.1 Icon system (`icons.py`)

- **Icon DSL:** each app declares an `IconScene` = list of shape primitives
  drawn with pygame primitives, colored from **semantic theme tokens**:
  primitives `round_rect`, `circle`, `line`, `arc`, `polygon`, `text`; colors
  from a token map (`accent`, `accent2`, `panel`, `text`, `highlight`, `muted`).
- **Renderer:** renders to a cached `pygame.Surface` at a requested size via
  **2× supersampling + downscale** for clean AA. Cache keyed by
  `(scene_id, size, theme_fingerprint)`.
- **Sizes:** 16 (titlebar/tray), 24 (taskbar), 32 (launcher), 64 (desktop/about).
- **Flagship art:** hand-drawn scenes for all existing + new apps (~19 total);
  glyph-tile fallback for any app without a scene.
- **Interactions:** hover glow, pressed inset, launch-bounce (motion-flagged);
  launcher icons render notification badge dots from the notification service.
- **Integration points:** desktop icons, launcher, taskbar, window titlebar,
  Alt-Tab, About.

#### 6.2 Smoothness engine

- **Dirty-rect rendering:** `pygame.display.update(rects)` instead of `flip()`
  when only regions changed; full redraw on large changes only.
- **VSync + fixed timestep:** vsync in `set_mode` where available; `clock.tick(60)`;
  `dt` clamped; animate against fixed-step eased values.
- **Perf counters + telemetry HUD:** frame ms, FPS, redraw count, per-stage ms;
  toggleable translucent HUD (focused title, window count, FPS, RAM).
- **Two-phase startup:** structural pass (boot→login→wallpaper→taskbar→icons→
  window frames) instantly; heavy app content hydrates over next frames.
- **Cache correctness:** all cached surfaces keyed by inputs; file-backed assets
  invalidated on `mtime`+`size`; `_needs_redraw` stays the redraw source of truth.
- **Background work:** watchers/health/snapshots run off the main loop with a
  ~2s debounce — never block input/rendering.

#### 6.3 Theme tokens + contrast

- Semantic token set on `Theme` (formalize `radius`, `spacing`, `text-disabled`);
  migrate every hardcoded color in `widgets.py` + apps through theme fields.
- **WCAG-AA contrast pass** across all 8 themes (body ≥ 4.5:1, large ≥ 3:1) with
  a test assertion.
- **Visible keyboard focus states** in taskbar, launcher, window chrome.

### Phase 2 — Driver architecture (framework + core + library)

#### 6.4 Driver framework (`drivers/framework.py`, `drivers/bus.py`)

- **`Driver` base class** with lifecycle:
  `probe() -> bool`, `init()`, `start()`, `stop()`, `update(dt)`,
  `status() -> DriverStatus`, `diagnose() -> str`, `configure(cfg)`.
  Class attrs: `name`, `category`, `simulated: bool`, `depends: list[str]`,
  `description`, `config_defaults: dict`.
- **`DriverStatus`**: `available`, `enabled`, `running`, `health` (0-100),
  `detail` (one-line state), `last_error`.
- **`DriverBus`**: holds all registered drivers; on boot topologically sorts by
  `depends`, probes each, init/start; produces `BootProbeLine`s
  (`[ok]`/`[warn]`/`[offline]`/`[sim]`); supports re-probe, enable/disable,
  per-driver `update(dt)`, and a **device tree** (grouped by category) for the
  Devices app.
- Per-driver config lives in `config.json` → `drivers.<name>`. Absent config =
  defaults; absent hardware/backend = `available=False`, all ops no-op.
- Framework is **headless-safe** (no display/audio → drivers degrade).

##### 6.4.1 Auto-configuration & self-healing engine

The system **configures itself** — everything is detected, tuned, and applied
automatically, with zero clicks required:

- **`Driver.auto_tune(probe) -> dict`** — every driver returns its optimal
  config from its own probe result (audio → best sample rate + device; display →
  best resolution/refresh/vsync; thermal → real CPU baseline; storage → real
  free space). The bus runs `auto_tune` automatically after `probe` and applies
  it **unless the user manually overrode** the value.
- **Auto-probe cascade:** `probe → auto_tune → init → start`, each step logged
  at boot (`[ok] Audio → 44100Hz/2ch (wasapi)`).
- **Self-healing fallback chains:** on init failure a driver retries the next
  best option automatically (audio: chosen device → default → silent no-op;
  video: accelerated → software → dummy; resolution: preferred → first
  available). A driver that cannot start records `last_error`, reports
  `available=False` with a helpful status, and never crashes the OS.
- **System auto-tuner** (runs once at boot, re-runs on wake/re-probe):
  - CPU cores/RAM → recommended motion level, fps target, cache budget.
  - Display refresh rate → vsync on/off + frame pacing.
  - Headless / no display → `--headless` path.
  - Battery present (psutil) → low-battery auto-reduce motion + power saver.
  - Offline network → network features degrade to cached/empty states.
- **First boot:** everything auto-configures to a working desktop with zero
  clicks; the wizard becomes *optional personalization*, not a requirement.
- **`drivers.auto.json`** — the OS writes a snapshot of what it auto-configured
  after boot (device → chosen settings), so users/reviewers can inspect and
  diff against manual overrides.
- **Precedence:** manual override > auto-configured > defaults.
- **Devices & Drivers UI:** every driver shows `[Auto] <value>` (detected
  config), an `[Override]` to change it, `[Re-auto]` to re-run `auto_tune`, and
  a global **Auto-tune all** button; the driver log shows what was configured.

#### 6.5 Core drivers (real, functional)

- **`drivers/core/display.py`** — SDL video-driver selection (`windows`/
  `dummy` for headless/`offscreen`), mode, vsync, `DisplayInfo`.
- **`drivers/core/audio.py`** — guarded mixer init, output-device enumeration +
  selection, master/music volume + mute, generated SFX, `play_music`.
- **`drivers/core/input.py`** — keyboard/mouse/scroll normalization + optional
  gamepad navigation (feature-flagged).
- **`drivers/core/media.py`** — wav/ogg/mp3 audio backend, image loading,
  codec table, **optional video backend** (only if a codec lib is installed).
- **`drivers/core/network.py`** — connectivity probe (cached ~2s), online/
  offline tray indicator, offline fallback for Browser/App Store/AI.

#### 6.6 Simulated driver library (`drivers/library/`)

~100 driver classes, each a `Driver` registered in the bus, grouped into
modules. Every driver: has a real `probe`/`status`/`update`, is configurable,
logs to `drivers.log`, and **degrades gracefully**. Marked **R** = genuinely
functional on host, **S** = simulation (plausible telemetry / no-op). See
**Appendix A — Driver catalog** for the full list.

**Representative behaviors:**
- *Storage*: RAM disk + NVMe (`io.BytesIO` block store, real read/write), RAID
  (striping across host folders), floppy (1.44 MB caps), tape (sequential-only),
  SAN (bind remote folders as drives).
- *Compute*: FPU (route to `math`/`numpy` if present), NPU emulator (route to
  `ollama` if present), vector accelerator (`memoryview`), quantum (Hadamard/
  CNOT matrix sim), physics proxy (gravity/collision math).
- *Input/accessibility*: touchscreen (click→touch mapping), stylus (pressure/
  tilt), braille proxy (text→formatted blocks), TTS (`pyttsx3` if present),
  speech-to-text (guard on mic libs), HOTAS/multi-axis, gamepad.
- *Audio/media*: MIDI synth (notes→tone buffers), MIDI keyboard (A/S/D/F→notes),
  PCM/WAV decoder (real header parse + streaming), video frame decoder,
  camera capture (webcam if present, else frame feeds), ROM loader.
- *Graphics/display*: display switcher (multi-monitor sim), refresh controller,
  ASCII rasterizer, UI scaling engine.
- *Network/cloud*: Wi-Fi scan, firewall (rule filter on simulated packets), DHCP
  (virtual IP lease), VPN, proxy/gateway, packet sniffer (hex dump), CDN cache
  (in-memory), P2P discovery, load balancer (thread pool), mesh router, GraphQL
  client, edge-compute router, WebRTC stream (in-process).
- *Security/crypto*: fingerprint (hash key file), smart card (key file token),
  RNG (`os.urandom`), sandbox (restricted `exec`), CA store, IDS (log scan),
  key logger (audit ledger), ACL (role permissions), vulnerability simulator
  (mock race conditions), memory scrubber, anti-tamper (hash core files), GDPR
  scrubber.
- *Diagnostics/monitoring*: loopback (route output→input), thermal (heat from
  real CPU load), UPS (real battery via psutil), LED/notification bar (taskbar
  flash/title), QR/barcode (decode image files), kernel profiler (timing real
  ops), crash dump (write state), core-dump (snapshot vars), journaling (intent
  log), watchdog (freeze→reboot), black box (last-1000 commands), power meter.
- *Power/environment/IoT*: GPS (mock coords or IP lookup), gyro/accelerometer
  (gesture→tilt), ambient light (time-of-day→theme), servo/actuator (steps),
  lamp (RGB→file), cash drawer (POS log), magnetic stripe (creds), plotter
  (SVG output), e-ink (slow/partial redraw), haptics.
- *IPC/host*: clipboard bridge (real host clipboard if `pyperclip`/tk present),
  shared-memory IPC (`multiprocessing.shared_memory`), subprocess pipe (real
  host commands), bus master (packet priority), demultiplexer, hypervisor
  (guest sub-instances), vSwitch, kubelet (manifest→desired state), container
  registry proxy.
- *Enterprise/esoteric*: BIOS compatibility, JQE batch queue, FPGA bitstream
  loader, oscilloscope/signal analyzer, SAN (above), NVMe-oF, symbolic debugger,
  SSH daemon (background socket server), time-machine backup, satellite link
  (latency/dropout sim).

#### 6.7 Devices & Drivers app

- New app rendering the **device tree**: categories → drivers, each with
  status badge (ok/warn/offline/sim), health, detail, `[configure]`, `[enable/
  disable]`, `[re-probe]`. Search/filter by name or category.
- Driver log viewer (`drivers.log`). Rooted at `os.drivers` for apps/scripts.
- Settings → **Devices & Drivers** panel reuses the same data.

### Phase 3 — Persistence & identity

#### 6.8 Session resume (`session.py`)

- Serialize minimal state (windows, rects, z-order, focus, theme, workspace).
- Save on every mutating event + on quit; keep last-3 checkpoints; SIGINT/
  SIGTERM handlers save session + flush caches.
- On boot, restore + **animate windows in**; toggleable. Power-menu
  "Log out / Shut down" runs the clean path.

#### 6.9 First-boot wizard

- 4 steps: name → live theme/accent preview → pinned apps → "what matters".
- Writes `profile.json`; idempotent; archives prior profile; animated
  transitions; boot skips straight to login once present.

#### 6.10 Activity log + Recents + Session Summary

- `activity.py`: append-only JSONL events (launch/close/theme/save/login/screenshot).
- Launcher **Recents** + frequency ordering from the log.
- Boot-time **Session Summary card** fades in/out over the wallpaper.

#### 6.11 Clipboard (`clipboard.py`)

- Single service `copy/paste` used by Text Editor, Notes, Terminal, Browser,
  File Manager; history ring in `clipboard.jsonl`; **Super+V** history palette.

### Phase 4 — Catalog & chrome

#### 6.12 App manifest + catalog launcher

- Registry exposes manifest `{id, name, icon, category, description, version,
  keywords}`. Catalog launcher: categorized scrollable list with descriptions +
  version badges, collapsible category index, curated-first tab + full list.
  Type-ahead + arrow navigation.

#### 6.13 Chrome polish

- **Statusline widgets** (clock, date, theme, CPU, network, workspace) —
  toggleable, each cached to its own surface.
- **Telemetry HUD** (see 6.2) — off by default.
- **Motion-level setting** (`Full/Reduced/None`) + **feature flags**.
- **Progressive disclosure** — advanced controls behind context menus/flyouts.

#### 6.14 Notification center

- Notification service (`os.notify(...)`) with timeouts + history; taskbar
  panel with per-app grouping, click-to-open, clear-all; icon badge dots.

#### 6.15 Wallpaper gallery + accent picker

- Procedural wallpapers (gradient, aurora, grid, dots, mountain) cached per
  theme; **accent picker** re-themes icons + chrome live.

#### 6.16 System tray

- Running-app indicators, quick toggles (sound, motion, notifications), network
  online/offline, battery (psutil), notification-center opener, show desktop.

### Phase 5 — Power-user features + new apps

#### 6.17 Workspaces / virtual desktops

- 4 workspaces; Ctrl+Alt+←/→ switch, Win+number jump; taskbar indicator;
  windows animate between; workspace in session state.

#### 6.18 Window tiling

- Win+←/→/↑/↓ tile half/quarter/center; snap preview polish; auto-arrange.

#### 6.19 Global search (`search.py`)

- Super+Space centered search across apps, Notes files/content, Settings,
  activity log; source attribution; Enter opens target.

#### 6.20 Screenshot tool

- Win+Shift+S → `~/.lionos/screenshots/YYYYmmdd-HHMMSS.png`; toast + preview;
  activity log event; reachable from Power menu.

#### 6.21 Media Player rebuild

- On the media driver: audio (wav/ogg/mp3), optional video, drag-and-drop,
  open-with; **live audio visualizer**; metadata; playlist next/prev/shuffle/loop;
  unsupported formats show clear notice.

#### 6.22 New apps

- **Help** — self-documenting catalog; searchable; "?" in window chrome.
- **System Health** — scored audit (apps, themes, widgets, animations, profile,
  **driver status**) /100 + top-3 next steps.
- **Inbox + quick-capture** — Super+N capture box, To Do/Someday/Ideas,
  promote-to-task.
- **Today / Timeline** — activity log as a view.
- **Focus mode** — dim/hide/notify-suppress "not today" apps.

### Phase 6 — Config, verification, release

#### 6.23 Settings app overhaul

- **Appearance** (theme, accent, wallpaper) · **Devices & Drivers** (device
  tree, audio device picker, codec table, re-probe) · **Motion** (Full/Reduced/
  None + flags) · **Sound** (master volume, system sounds) · **Statusline**
  (widget toggles) · **Shortcuts** · **System** (session-resume, uninstall app,
  reset, About/Health).

#### 6.24 Smoothness & config hardening

- Every subsystem reads `LionConfig` defaults+validation; no config = still boots.
- **Config precedence:** manual override > auto-configured > defaults; the auto
  engine writes `drivers.auto.json` so overrides are a visible diff, never a
  hidden fight.
- All caches keyed + invalidated correctly.
- Graceful degradation verified: no audio, no display (`--headless`), slow
  machine (motion=None), corrupt `session.json`/`profile.json`, offline network,
  absent driver backends, init failure → fallback chain → `available=False`.
- Deterministic main loop with perf counters; slow-frame invariant logs.

#### 6.25 Testing

Extend the pytest suite (headless, `SDL_VIDEODRIVER=dummy`):
- Icons: every scene renders at 16/32/64; cache hits.
- **Framework**: base lifecycle; bus order by `depends`; probe/init/start/stop;
  enable/disable; device tree; re-probe; no-backend degradation.
- **Auto-config**: `auto_tune` produces sensible values from probe; fallback
  chain on init failure (audio default→silent, video→dummy); override
  precedence (manual > auto > defaults); `drivers.auto.json` written;
  system auto-tuner picks motion/fps/vsync from detected CPU/RAM/display/
  battery.
- **Core drivers**: audio no-device no-op; display dummy; media `supports()`;
  network offline fallback.
- **Library drivers**: each driver `probe()`+`status()` without error; a sampled
  subset exercised (RAM disk read/write, RNG entropy, firewall rule filter,
  PCM header parse, ACL allow/deny, thermal monotonic under load, crash-dump
  writes file, watchdog timeout, journaling intent log, backup snapshot).
- Session, activity, catalog, wizard, workspaces, clipboard, notifications,
  sound, search, contrast, Media Player, new apps, existing 35 tests + smoke.

#### 6.26 Release (2.0.0)

- README overhaul (features, driver architecture diagram, install unchanged).
- Clean build → fresh-venv verify → publish 2.0.0 to GitHub + PyPI (as v1.1.2).

## 7. Risks & mitigations

- **Scope is large** → phased; top-impact "wow" first (icons, smoothness,
  session); later phases additive.
- **Regression risk in kernel/wm** → evolutionary refactor + existing tests +
  headless smoke after every phase.
- **Pygame performance ceiling** → cache-backed rendering, dirty-rects,
  supersampling at load only, no per-frame transforms.
- **Driver bloat / toy code** → every driver has a real probe/status/update and
  a concrete (if small) behavior; pure-simulation drivers are clearly tagged S
  in the UI and are **off by default** behind a "show simulated" toggle.
- **Audio/video/backend absence** → fully guarded; never raise.

## 8. Decisions taken

- Procedural vector icons (not PNG/emoji).
- Driver framework + 5 core real drivers + ~100-driver simulated library
  (tagged R/S), all configurable, all graceful.
- **Everything auto-configures**: probe → auto_tune → init → start with
  self-healing fallbacks and a system auto-tuner; manual overrides win.
- No required new runtime deps; optional backends opt-in.
- No new third-party skills installed (apply patterns directly).
- New apps added (Help, System Health, Inbox, Today, Devices & Drivers);
  Media Player rebuilt.
- Version 2.0.0 "Majestic".

---

## Appendix A — Driver catalog

Legend: **R** = functional on host · **S** = simulation (telemetry/no-op) · drivers
are off-by-default when marked `simulated` unless explicitly enabled.

### Bus & enumeration
1. PCI Bus Enumerator — R — walks registered drivers into a device tree on boot.
2. I2C Bus Controller — S — byte-buffer transfers between virtual chips.
3. SPI Master — S — full-duplex synchronous serial emulation.
4. CAN Bus Controller — S — automotive diagnostics message bus.
5. Bus Master Controller — R — packet/driver data priority arbitration.

### Storage & filesystem
6. NVMe Controller — R — `io.BytesIO` high-speed block store.
7. RAM Disk Controller — R — volatile in-memory drive, wiped on reboot.
8. RAID Array Controller — R — stripes data across host folders (mirror/0).
9. Floppy Disk Controller — R — 1.44 MB size caps on a virtual drive.
10. Tape Drive Controller — R — sequential-only archival access.
11. Virtual SAN — R — bind remote/host folders as drives.
12. NVMe-over-Fabrics — S — block-storage-over-socket proxy.
13. EEPROM Flasher — R — persistent config that survives corruption.
14. File System Journaling — R — intent log before writes; replay on boot.
15. Time-Machine Backup — R — zip snapshots of the virtual drive on a timer.

### Compute & AI
16. Math Co-Processor (FPU) — R — route complex math to `math`/`numpy`.
17. Neural Processing Unit (NPU) — R/S — route AI ops to `ollama` if present.
18. Quantum Qubit Simulator — S — Hadamard/CNOT register matrix ops.
19. Data Pipeline Vector Accelerator — R — `memoryview` array ops.
20. Physics Engine Proxy — R — gravity/velocity/collision math service.
21. JIT Compilation Proxy — R — tokenize + `exec` user scripts (sandboxed flag).
22. Kernel Performance Profiler — R — times real ops; efficiency graphs.
23. Symbolic Debugger Interface — R — line stepping/breakpoints/inspect.

### Input & accessibility
24. Braille Display Proxy — R — text → formatted accessibility blocks.
25. Virtual Touchscreen Controller — R — click → touch events (mock profile).
26. Drawing Tablet / Stylus Driver — R — pressure/tilt into canvas input.
27. Speech-to-Text Handler — S — mic → text (guarded on available libs).
28. HOTAS / Multi-Axis Joystick — R — multi-axis throttle decoding.
29. Virtual MIDI Keyboard — R — A/S/D/F rows → musical notes.
30. Virtual Joystick Throttle — R — axis → launcher/window navigation.

### Audio & media
31. Sound Blaster (MIDI) Driver — R — notes/numbers → synthesized tone playback.
32. PCM/WAV Audio Decoder — R — real header parse + streaming audio bits.
33. Video Frame Decoder — S — image/text arrays → flipbook animation.
34. Virtual Camera Capture — R/S — webcam if present, else synthetic frames.
35. Audio Codec (PCM/WAV) — R — same as 32 (codec layer for media driver).
36. Speech Synthesis (TTS) — R/S — `pyttsx3` if present, else text-to-log.
37. Legacy Game ROM Loader — S — raw byte arrays → executable logic.

### Graphics & display
38. Display Output Switcher — R — multi-monitor/terminal-split management.
39. Refresh Rate Controller — R — FPS governor to prevent flicker.
40. ASCII Font Rasterizer — R — fonts → ASCII-art text rendering.
41. UI Scaling & Layout Engine — R — auto reflow on resize.
42. E-Ink Display Controller — S — slow/partial redraw emulation.
43. Haptic Feedback Interface — R/S — notifications → rumble/click commands.
44. Virtual Oscilloscope — S — captures driver signals → wave graphs.

### Networking & cloud
45. Virtual Wi-Fi Card — S — scan, switch, signal-strength degradation.
46. Virtual Firewall (iptables) — R — rule-filter simulated packets.
47. Mock DHCP Client — R — virtual IP lease on connect.
48. VPN Tunneling — R — simulated encrypt/route layers.
49. Proxy / Gateway Link — R — route traffic through a middleman module.
50. Network Packet Sniffer — R — hex-dump logged packets.
51. Mock CDN / Cache Manager — R — in-memory asset cache.
52. P2P Node Discovery — S — subnet scan → peer list (no central server).
53. Virtual Load Balancer — R — distribute tasks across worker threads.
54. Mesh Network Router — S — hop-by-hop packet forwarding.
55. GraphQL Client Interface — R — map requests to cloud endpoints.
56. Edge Compute Router — R/S — shift heavy tasks to worker threads.
57. Mock WebRTC Stream Handler — S — in-process realtime message stream.
58. Remote Terminal Daemon (SSH) — S — background socket server console login.
59. Container Registry Proxy — R — pull/decompress/load script archives.

### Security & cryptography
60. Biometric Fingerprint Scanner — R — hash-key-file profile auth.
61. Smart Card Reader — R — key-file security token gate.
62. Virtual RNG — R — `os.urandom` secure random bits.
63. Sandbox Isolation Layer — R — restricted container for untrusted scripts.
64. Root Certificate Authority Store — R — manage/validate certs.
65. Intrusion Detection (IDS) — R — scan logs; block malicious patterns.
66. Hardware Key Logger — R — admin audit ledger of all inputs.
67. Virtual ACL — R — role-based read/write/execute permissions.
68. Vulnerability Simulator — S — inject mock race conditions for practice.
69. Memory Scrubber / Zeroer — R — zero freed buffers for privacy.
70. Anti-Tamper Signature Verifier — R — hash core files on startup.
71. GDPR Data Scrubber — R — wipe personal-data rows from logs.
72. Aviation Black Box — R — write-only last-1000 commands cache.

### Diagnostics, power & environment
73. Diagnostic Loopback — R — route output back to input for self-test.
74. Thermal Sensor Simulator — R — heat from real CPU load.
75. Virtual UPS — R — real battery (psutil) → safe shutdown trigger.
76. LED / Notification Bar — R — taskbar flash / title alert.
77. Barcode / QR Scanner — R — decode image files → keyboard text.
78. Crash Dump (Blue Screen) — R — stop threads, write state on fatal error.
79. Kernel Core Dump Event — R — snapshot variables at crash instant.
80. Watchdog Timer — R — background thread reboots OS on freeze (>10s).
81. Virtual Smart Grid Power Meter — R — track virtual power; power-saver mode.
82. Satellite Telemetry Link — S — latency/dropout/Doppler simulation.
83. Virtual GPS / Location — R/S — mock coords or IP-lookup geolocation.
84. Gyroscope & Accelerometer — S — mouse gestures → motion/tilt telemetry.
85. Ambient Light Sensor — R — time-of-day → light/dark theme.
86. Virtual Servo / Actuator — S — string commands → mock mechanical steps.
87. Telemetry Data Aggregator — R — package sensor readings → JSON.
88. Smart Desk Lamp Controller — R — RGB/brightness → mock output file.
89. Virtual Cash Drawer Link — R — POS open/close + transaction log.
90. Magnetic Stripe / RFID Reader — R — numeric card → credential form.
91. Virtual Plotter / Drafting Arm — R — coordinates → SVG draw-paths.
92. Virtual RAM/BIOS — R — legacy boot/config interpretation.

### IPC, virtualization & enterprise
93. Host OS Clipboard Bridge — R — sync real clipboard (pyperclip/tk).
94. Shared Memory IPC — R — `multiprocessing.shared_memory` segments.
95. Subprocess Pipe Controller — R — run host commands; capture output.
96. Signal Demultiplexer — R — split combined streams per subsystem.
97. Hypervisor Interface — R — spin up/freeze/manage guest sub-instances.
98. Virtual Network Switch (vSwitch) — S — route between virtual machines.
99. Mock Kubernetes Kubelet — R — manifest → desired background state.
100. Mainframe Job Queue Entry — R — priority batch queue execution.
101. FPGA Bitstream Loader — S — parse config → reconfigure virtual circuits.
102. Macro Automation Recorder — R — record/replay keystrokes+mouse+commands.
103. Virtual SAN (see 11) — dup guard.

> The library keeps each driver class small and framework-driven; a driver is
> code a reviewer can read and a user can toggle — not dead weight. Simulated
> drivers ship disabled by default and are gated by `show_simulated` in Devices.
