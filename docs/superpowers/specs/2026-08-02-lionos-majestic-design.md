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
3. **A hardware abstraction layer ("drivers")** — display, audio, input, media,
   and network drivers the kernel probes at boot and every feature talks
   through; gracefully degrades (no audio device, no display, offline).
4. **Real-OS persistence** — session resume (no cold blank desktop), first-boot
   wizard, activity log + recents + session summary, clipboard with history.
5. **A proper app catalog** — data-driven manifest, categorized scrollable
   launcher with descriptions + version badges, curated-first tab.
6. **Polished chrome** — notification center, sound design, wallpaper gallery +
   accent picker, workspaces, window tiling, global search, screenshots, system
   tray, statusline widgets, motion-level accessibility.
7. **New apps** — Help, System Health, Inbox (quick-capture), Today/Timeline;
   **Media Player rebuilt on the media driver**.
8. **Configure everything to run smoothly** — one comprehensive Settings app and
   robust, correct config/cache plumbing with graceful degradation everywhere.

## 2. Non-goals

- **No required new runtime dependencies** (stays a pure-Python Pygame package).
  The optional video backend only activates if a codec library happens to be
  installed; the core never requires it.
- No network accounts, no cloud sync, no real multi-user security model.
- No Windows/Linux/macOS native integrations beyond what Pygame/SDL exposes.
- No restructuring of the existing 7,800-LOC architecture into new layers
  (evolutionary refactor only — see §4).

## 3. Version & codename

Bump to **2.0.0**, codename **"Majestic"**. Update `pyproject.toml`,
`lionos/__init__.py` (version/build/codename), README badges + notes.

## 4. Architecture approach

**Evolutionary refactor** of the existing structure:

- Keep `kernel.py`, `wm.py`, `widgets.py`, `theme.py`, `config.py`, `cli.py`,
  `ai/`, `apps/` and evolve them in place.
- Add focused new modules for genuinely new subsystems:
  - `lionos/icons.py` — procedural vector icon renderer + per-app icon scenes.
  - `lionos/drivers/` — hardware abstraction layer (package):
    - `drivers/display.py` — video driver selection, mode, vsync.
    - `drivers/audio.py` — mixer init, devices, volume, SFX, music.
    - `drivers/input.py` — keyboard/mouse/scroll/gamepad normalization.
    - `drivers/media.py` — audio file backend, image loading, optional video.
    - `drivers/network.py` — connectivity + online/offline status.
    - `drivers/__init__.py` — `DriverManager` (probe/init/hold/re-probe).
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
| `config.json` | user preferences (existing — extended) |
| `profile.json` | first-boot wizard output (name, pinned apps, what-matters) |
| `session.json` | desktop state snapshot (open windows, positions, z-order, focus, theme, workspace) |
| `session-<n>.json` | last-3 crash-recovery checkpoints |
| `activity.jsonl` | append-only event stream (launches, theme changes, saves) |
| `clipboard.jsonl` | clipboard history |
| `screenshots/` | screenshot output |
| `media/` | Media Player playlists / library metadata |
| `notes/`, `config.json` (existing) | unchanged |
| `logs/` | OS + driver logs |

## 6. Workstreams (6 phases, dependency-ordered)

### Phase 1 — Foundation: icons + smoothness + tokens

#### 6.1 Icon system (`icons.py`)

- **Icon DSL:** each app declares an `IconScene` = list of shape primitives
  drawn with pygame primitives, colored from **semantic theme tokens**, not
  hardcoded hex:
  - primitives: `round_rect`, `circle`, `line`, `arc`, `polygon`, `text`.
  - colors resolved from a token map (`accent`, `accent2`, `panel`, `text`,
    `highlight`, `muted`).
- **Renderer:** renders a scene to a cached `pygame.Surface` at a requested
  pixel size via **2× supersampling + downscale** for clean antialiasing.
  Cache keyed by `(scene_id, size, theme_fingerprint)`.
- **Sizes:** 16 (titlebar/tray), 24 (taskbar), 32 (launcher), 64 (desktop/about).
- **Flagship art:** hand-drawn scenes for all 15 existing apps + new apps
  (~19 total). Fallback to the current glyph tile for any app without a scene.
- **Interactions:** hover glow, pressed inset, launch-bounce micro-animation —
  all additive and motion-flagged. Launcher icons render a small notification
  badge dot/count from the notification service.
- **Integration points:** replace glyph draws in `kernel.py` desktop icons,
  launcher, taskbar, window titlebar, Alt-Tab, and About.

#### 6.2 Smoothness engine

- **Dirty-rect rendering:** accumulate dirty `pygame.Rect`s and call
  `pygame.display.update(rects)` instead of `flip()` when no full redraw is
  needed. Full redraw on large changes only.
- **VSync + fixed timestep:** request vsync in `set_mode` where available;
  keep `clock.tick(60)`; clamp `dt` (already `min(0.05, ...)`); animate against
  fixed-step eased values to kill jitter.
- **Perf counters:** track frame ms, FPS, redraw count, and per-stage ms in the
  main loop; expose a **toggleable telemetry HUD** (focused-window title,
  window count, FPS, frame ms, RAM) composited from cached surfaces.
- **Two-phase startup:** structural pass renders boot → login → wallpaper →
  taskbar → desktop icons → window frames instantly; heavy app content is
  hydrated over the next frames (session-restored apps render skeleton first,
  content second).
- **Cache correctness:** all cached surfaces keyed by their inputs; any
  file-backed asset (wallpaper, theme, fonts) invalidated on `mtime`+`size`
  change. `_needs_redraw` stays the single source of truth for redraws.
- **Background work:** file-watcher/health/snapshot writes run off the main
  loop (thread or defer to update stage) with a ~2s debounce — never block
  input/rendering.

#### 6.3 Theme tokens + contrast

- Add a semantic token set to `Theme` (already has most fields; formalize
  `radius`, `spacing`, `text-disabled`), and **migrate every hardcoded color in
  `widgets.py` and the apps** through theme fields.
- **WCAG-AA contrast pass** across all 8 themes (body ≥ 4.5:1, large ≥ 3:1).
  Adjust palettes where needed; add a contrast assertion to the test suite.
- **Visible keyboard focus states** in taskbar, launcher, and window chrome.

### Phase 2 — Hardware abstraction layer (drivers)

#### 6.4 Driver manager (`drivers/__init__.py`)

- `DriverManager` probes and holds one instance of each driver. Exposed to the
  shell and apps as `os.drivers.<name>`.
- Boot logs a probe line per driver: `[ok]` / `[warn]` / `[offline]`.
- Re-probe action (Settings → Devices & Drivers). Every driver degrades
  gracefully: absence of hardware → `available=False`, all ops no-op.

#### 6.5 Display driver (`drivers/display.py`)

- Selects the SDL video driver: `windows` (or platform default) in normal mode,
  `dummy` under `LION_OS_HEADLESS`, user override via env. Applies mode
  (windowed/fullscreen/borderless), resolution, and vsync flag.
- Reports `DisplayInfo`: driver name, display count, resolutions, refresh rate.
- The smoothness engine (§6.2) consumes this driver for `set_mode`/vsync.

#### 6.6 Audio driver (`drivers/audio.py`)

- `init()`: `pygame.mixer.pre_init` with best-effort sample rate/buffer,
  `pygame.mixer.init()` guarded; **no audio device → `available=False`, every
  method no-ops** (never raises, headless-safe).
- Enumerates output devices (via SDL audio device list when available); the
  user picks a device in Settings (re-init on change).
- **Volume:** master volume, per-SFX, and music volume; mute toggle. Persisted
  in `config.json`.
- **System sounds:** `play_sfx(id)` for boot, window open/close, toast,
  screenshot, error, etc. SFX are generated as small in-memory buffers (no
  bundled audio files). `play_music(path)` / `stop` / `pause` / `seek` via
  `pygame.mixer.music` for Media Player.
- `sound.py` (sound theme) builds on this driver; "Sound" toggle + volume in
  Settings; disabled under Reduced/None motion and headless.

#### 6.7 Input driver (`drivers/input.py`)

- Normalizes `pygame.event` into a stable input state (keyboard, mouse buttons,
  scroll, cursor). Existing kernel event handling routes through it.
- **Optional gamepad navigation** (feature-flagged): initializes
  `pygame.joystick`, maps dpad/sticks/buttons to launcher navigation, window
  move, and Alt-Tab. Detects a new controller at any time.

#### 6.8 Media driver (`drivers/media.py`)

- **Audio file backend:** opens wav/ogg/mp3 via `pygame.mixer.music`; exposes
  duration, position, play/pause/seek/volume, and completion callback (next
  track). `supports(path)` by extension + codec probe.
- **Image loading:** decodes PNG/JPG/BMP/GIF stills for wallpaper and viewers.
- **Optional video backend:** if a codec lib (`imageio-ffmpeg`, `av`, or
  `opencv`) is importable, plays video frames into a surface on a background
  thread; otherwise video files are detected and opened **audio-only** with a
  clear "video codec not available" notice. Core dependency-free.
- Reports a **codec table** (supported formats) used by Media Player and the
  Devices & Drivers panel.

#### 6.9 Network driver (`drivers/network.py`)

- Thin, guarded wrapper around `requests`: connectivity probe (cached ~2s TTL),
  `online`/`offline` status surfaced in the system tray, user-agent, and a
  `no_network` fallback for Browser / App Store / AI so offline use never
  crashes.

### Phase 3 — Persistence & identity

#### 6.10 Session resume (`session.py`)

- Serialize **minimal** state: list of `{app_name, rect, minimized, focused}`,
  `z_order`, active theme, active workspace.
- Save on every mutating event + on quit; keep last-3 checkpoints
  (`session-1/2/3.json`) for crash recovery; register SIGINT/SIGTERM handlers
  that save session and flush caches.
- On boot, restore windows and **animate them in**; toggleable via Settings.
- Wire the existing power-menu "Log out / Shut down" to the same clean path.

#### 6.11 First-boot wizard

- 4-step full-screen flow: (1) name, (2) live theme + accent preview, (3) pin
  apps to launcher/taskbar, (4) "what matters most" (drives focus mode).
- Writes `profile.json`; idempotent (re-runnable from Settings, archives prior
  profile to `~/.lionos/archives/`). Animated transitions + progress dots.
- Boot skips to login directly when `profile.json` exists.

#### 6.12 Activity log + Recents + Session Summary

- `activity.py`: append-only JSONL, one event per `{ts, type, detail}`
  (`app_launch`, `app_close`, `theme_change`, `file_save`, `login`, `screenshot`).
- Launcher **Recents** row + frequency-sorted app ordering read from the log.
- Boot-time **Session Summary card** fades in over the wallpaper
  ("Good morning. Yesterday: Terminal ×5, Notes ×2, switched to Sunset.")
  then fades out; disabled if the log is empty/first boot.

#### 6.13 Clipboard (`clipboard.py`)

- Single clipboard service: `copy(kind, value)` / `paste()` used by
  Text Editor, Notes, Terminal, Browser, and the shell (copy path from File
  Manager). History ring stored in `clipboard.jsonl`.
- **Super+V** opens a clipboard-history palette; entries are searchable and
  click-to-paste.

### Phase 4 — Catalog & chrome

#### 6.14 App manifest + catalog launcher

- Add per-app metadata to the registry: `version`, `keywords`, `description`
  (mostly present). Expose a manifest view: `{id, name, icon, category,
  description, version}`.
- **Catalog launcher:** categorized, scrollable list with one-line description +
  version badge per app; category index that collapses/expands; a
  **curated-first tab** (frequent/pinned apps) + full catalog tab.
- Keyboard-first: type-ahead filter, arrow navigation (existing launcher
  behavior extended).

#### 6.15 Chrome polish

- **Statusline widgets:** taskbar tray splits into toggleable cached widgets
  (clock, date, theme name, CPU, workspace, network). Each widget cached to its
  own surface; toggled from Settings.
- **Telemetry HUD strip** (see 6.2) — translucent, composited, off by default.
- **Motion-level setting:** `Full / Reduced / None`; every animation gated
  behind it. **Feature flags** for beta behaviors.
- **Progressive disclosure:** advanced controls behind right-click context
  menus / "More" flyouts in the new power-user features.

#### 6.16 Notification center

- Upgrade toasts → notification service: `os.notify(title, body, app, kind,
  action=None)`. Notifications time out like toasts but persist in a history.
- **Notification center panel** (taskbar icon) lists recent notifications with
  per-app grouping, click-to-open (calls `action` or launches the app), and
  clear-all. Launcher/taskbar icons render badge dots from unread counts.

#### 6.17 Wallpaper gallery + accent picker

- Several procedural wallpapers (gradient, aurora, grid, dots, mountain) —
  each generated once and cached by theme fingerprint.
- **Accent color picker** in Settings overrides the accent tokens (re-themes
  icons + chrome live). Theme + accent + wallpaper are all live-switchable.

#### 6.18 System tray

- Tray area in the taskbar: running-app indicators, quick toggles (sound,
  motion, notifications), network online/offline, battery if available via
  psutil, open notification center, and a "Show desktop" behavior.

### Phase 5 — Power-user features + new apps

#### 6.19 Workspaces / virtual desktops

- 4 workspaces; each owns its set of windows. Ctrl+Alt+←/→ to switch
  (Win+number to jump). Taskbar workspace indicator. Windows animate between
  workspaces; per-workspace session state included in `session.json`.

#### 6.20 Window tiling

- Win+←/→/↑/↓ tile half/quarter/center; snap preview polish (existing snap
  extended); "Tiling" toggle (manual only). Auto-arrange action to restore a
  saved window layout.

#### 6.21 Global search (`search.py`)

- Super+Space (or Win+S) opens a centered search box.
- Indexes: app names/descriptions, Notes filenames + content (lazy, on demand),
  Settings sections, activity log entries. Results carry **source attribution**
  and open the target app/file/setting on Enter.

#### 6.22 Screenshot tool

- Win+Shift+S captures the screen to `~/.lionos/screenshots/YYYYmmdd-HHMMSS.png`
  (copy the screen and `pygame.image.save`). Toast with preview; screenshot
  event appended to activity log. Also reachable from the Power menu.

#### 6.23 Media Player rebuild

- Rebuilt on the **media driver**: open audio files (wav/ogg/mp3) and supported
  video/images; play/pause/seek/volume via the driver; playlist with
  next/prev/shuffle/loop (existing) plus **drag-and-drop** and **open-with**.
- **Live audio visualizer** (spectrum-style bars driven by mixer volume/FFT-free
  amplitude) rendered from cached bars; metadata (title, artist, duration)
  parsed from filenames/tags when available.
- If the optional video backend is absent, video files open audio-only with a
  clear notice; the Devices & Drivers panel shows supported formats.

#### 6.24 New apps

- **Help** — self-documenting catalog: every app with description, tips,
  shortcuts; searchable; reachable from a "?" in each window chrome + launcher.
- **System Health** — scored audit: apps available, themes, widgets, animations
  on, profile complete, driver status → score /100 with stage label and top-3
  suggested next steps; connections-style registry with "last checked" freshness.
- **Inbox + quick-capture** — Super+N opens a small always-on-top capture box
  appending to a unified inbox (To Do / Someday / Ideas); promote-to-task action.
- **Today / Timeline** — the activity log as a view (per-day timeline, app usage
  counts).
- **Focus mode** — user marks apps "not today"; they dim in the launcher, hide
  from taskbar recents, and their notifications are swallowed (toggleable).

### Phase 6 — Config, verification, release

#### 6.25 Settings app overhaul

Central panel with sections:
- **Appearance** — theme, accent, wallpaper.
- **Devices & Drivers** — display info, audio device picker + volume + mute,
  input/gamepad status, media codec table, network status, **re-probe**.
- **Motion** — Full/Reduced/None + feature flags.
- **Sound** — master volume, system-sounds on/off.
- **Statusline** — widget toggles (clock, date, theme, CPU, network, workspace).
- **Shortcuts** — view/remap core hotkeys.
- **System** — session-resume toggle, clean uninstall of an app, reset config,
  About/Health.

#### 6.26 Smoothness & config hardening ("configure everything so it runs smoothly")

- Every subsystem reads config through `LionConfig` with sane defaults and
  validation; no config = still boots.
- All caches keyed by inputs + invalidated correctly (no stale render).
- Graceful degradation paths verified: no audio device, no display
  (`--headless`), very slow machine (motion=None → deterministic cached path),
  corrupt `session.json`/`profile.json` (fall back to defaults), offline
  network (apps use cached/empty states).
- Deterministic main loop with perf counters; a slow-frame invariant logs.

#### 6.27 Testing

Extend the pytest suite (headless, `SDL_VIDEODRIVER=dummy`):
- Icon renderer: every app scene renders without error at 16/32/64; cache hits.
- Drivers: audio no-device no-op; display dummy mode; media `supports()`;
  network offline fallback; driver manager probe/init/re-probe.
- Session: save → restore round-trip preserves windows/positions/theme/
  workspace; corrupt file tolerated; checkpoint rotation.
- Activity log: append + query; Recents ordering.
- Catalog launcher: manifest completeness, categories, filtering.
- Wizard: profile write/idempotence/archive.
- Workspaces: switch moves windows; session includes workspace.
- Clipboard: copy/paste + history; Super+V data path.
- Notification center: create/timeout/clear.
- Sound: guarded; no-audio path no-ops.
- Search: apps/notes/settings hits with source attribution.
- Theme contrast: WCAG-AA assertions for all 8 themes.
- Media Player: open audio, play/pause/seek state, visualizer render, unsupported
  format handled.
- New apps: launch + render + one interaction each.
- Existing 35 tests + headless smoke stay green.

#### 6.28 Release (2.0.0)

- README overhaul (new features, diagrams; install unchanged:
  `pip install lion-os-desktop` → `lionos`).
- Clean build → fresh-venv install verify → publish **2.0.0** to GitHub (tag →
  release workflow) and PyPI (`twine`), same flow as v1.1.2.

## 7. Risks & mitigations

- **Scope is large** → phased so the top-impact "wow" (icons, smoothness,
  session) lands first and is guaranteed; later phases are additive.
- **Regression risk in kernel/wm** → evolutionary refactor + existing 35 tests +
  headless smoke after every phase.
- **Pygame performance ceiling** → all rendering cache-backed, dirty-rects,
  supersampling only at load, no per-frame transforms.
- **Audio/video absence** → drivers fully guarded; never raise; optional video
  backend degrades to audio-only.

## 8. Decisions taken

- Procedural vector icons (not PNG assets, not emoji) — theme-aware, crisp,
  no dependencies.
- Drivers/HAL layer for display/audio/input/media/network, all graceful.
- No new required runtime dependencies; optional video backend opt-in.
- No new third-party skills installed (apply design-review/debugging/TDD
  patterns directly; the useful ones are already installed).
- New apps added (Help, System Health, Inbox, Today); Media Player rebuilt.
- Version 2.0.0 "Majestic".
