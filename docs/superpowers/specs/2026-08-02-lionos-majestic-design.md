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
3. **Real-OS persistence** — session resume (no cold blank desktop), first-boot
   wizard, activity log + recents + session summary, clipboard with history.
4. **A proper app catalog** — data-driven manifest, categorized scrollable
   launcher with descriptions + version badges, curated-first tab.
5. **Polished chrome** — notification center, sound design, wallpaper gallery +
   accent picker, workspaces, window tiling, global search, screenshots, system
   tray, statusline widgets, motion-level accessibility.
6. **New apps** — Help, System Health, Inbox (quick-capture), Today/Timeline.
7. **Configure everything to run smoothly** — one comprehensive Settings app and
   robust, correct config/cache plumbing with graceful degradation everywhere.

## 2. Non-goals

- No new runtime dependencies (stays a pure-Python Pygame package). All
  additions are implemented with `pygame`, the stdlib, and the existing
  `psutil`/`requests`.
- No network accounts, no cloud sync, no real multi-user security model.
- No Windows/Linux/macOS native integrations beyond what Pygame offers.
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
  - `lionos/session.py` — session snapshot/restore + graceful shutdown.
  - `lionos/catalog.py` — app manifest + categorized catalog model.
  - `lionos/activity.py` — append-only JSONL activity log.
  - `lionos/sound.py` — guarded sound effects engine.
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
| `session.json` | desktop state snapshot (open windows, positions, z-order, focus, theme) |
| `session-<n>.json` | last-3 crash-recovery checkpoints |
| `activity.jsonl` | append-only event stream (launches, theme changes, saves) |
| `clipboard.jsonl` | clipboard history |
| `screenshots/` | screenshot output |
| `notes/`, `config.json` (existing) | unchanged |
| `logs/` | OS logs if needed |

## 6. Workstreams (5 phases, dependency-ordered)

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

### Phase 2 — Persistence & identity

#### 6.4 Session resume (`session.py`)

- Serialize **minimal** state: list of `{app_name, rect, minimized, focused}`,
  `z_order`, active theme, active workspace.
- Save on every mutating event + on quit; keep last-3 checkpoints
  (`session-1/2/3.json`) for crash recovery; register SIGINT/SIGTERM handlers
  that save session and flush caches.
- On boot, restore windows and **animate them in**; toggleable via Settings.
- Wire the existing power-menu "Log out / Shut down" to the same clean path.

#### 6.5 First-boot wizard

- 4-step full-screen flow: (1) name, (2) live theme + accent preview, (3) pin
  apps to launcher/taskbar, (4) "what matters most" (drives focus mode).
- Writes `profile.json`; idempotent (re-runnable from Settings, archives prior
  profile to `~/.lionos/archives/`). Animated transitions + progress dots.
- Boot skips to login directly when `profile.json` exists.

#### 6.6 Activity log + Recents + Session Summary

- `activity.py`: append-only JSONL, one event per `{ts, type, detail}`
  (`app_launch`, `app_close`, `theme_change`, `file_save`, `login`, `screenshot`).
- Launcher **Recents** row + frequency-sorted app ordering read from the log.
- Boot-time **Session Summary card** fades in over the wallpaper
  ("Good morning. Yesterday: Terminal ×5, Notes ×2, switched to Sunset.")
  then fades out; disabled if the log is empty/first boot.

#### 6.7 Clipboard (`clipboard.py`)

- Single clipboard service: `copy(kind, value)` / `paste()` used by
  Text Editor, Notes, Terminal, Browser, and the shell (copy path from File
  Manager). History ring stored in `clipboard.jsonl`.
- **Super+V** opens a clipboard-history palette; entries are searchable and
  click-to-paste.

### Phase 3 — Catalog & chrome

#### 6.8 App manifest + catalog launcher

- Add per-app metadata to the registry: `version`, `keywords`, `description`
  (mostly present). Expose a manifest view: `{id, name, icon, category,
  description, version}`.
- **Catalog launcher:** categorized, scrollable list with one-line description +
  version badge per app; category index that collapses/expands; a
  **curated-first tab** (frequent/pinned apps) + full catalog tab.
- Keyboard-first: type-ahead filter, arrow navigation (existing launcher
  behavior extended).

#### 6.9 Chrome polish

- **Statusline widgets:** taskbar tray splits into toggleable cached widgets
  (clock, date, theme name, CPU, workspace). Each widget cached to its own
  surface; toggled from Settings.
- **Telemetry HUD strip** (see 6.2) — translucent, composited, off by default.
- **Motion-level setting:** `Full / Reduced / None`; every animation gated
  behind it. **Feature flags** for beta behaviors.
- **Progressive disclosure:** advanced controls behind right-click context
  menus / "More" flyouts in the new power-user features.

#### 6.10 Notification center

- Upgrade toasts → notification service: `os.notify(title, body, app, kind,
  action=None)`. Notifications time out like toasts but persist in a history.
- **Notification center panel** (taskbar icon) lists recent notifications with
  per-app grouping, click-to-open (calls `action` or launches the app), and
  clear-all. Launcher/taskbar icons render badge dots from unread counts.

#### 6.11 Sound design (`sound.py`)

- Guarded `pygame.mixer` init (try/except; no audio device → silent no-op).
- Small synthesized/asset-less sounds via `pygame.mixer.Sound` from generated
  buffers (no bundled audio files): boot, window open/close, toast, screenshot,
  error. Volume from Settings; **Sound** toggle; disabled under Reduced/None
  motion or headless.

#### 6.12 Wallpaper gallery + accent picker

- Several procedural wallpapers (gradient, aurora, grid, dots, mountain) —
  each generated once and cached by theme fingerprint.
- **Accent color picker** in Settings overrides the accent tokens (re-themes
  icons + chrome live). Theme + accent + wallpaper are all live-switchable.

#### 6.13 System tray

- Tray area in the taskbar: running-app indicators, quick toggles (sound,
  motion, notifications), battery/network if available via psutil, open
  notification center, and a "Show desktop" behavior.

### Phase 4 — Power-user features + new apps

#### 6.14 Workspaces / virtual desktops

- 4 workspaces; each owns its set of windows. Ctrl+Alt+←/→ to switch
  (Win+number to jump). Taskbar workspace indicator. Windows animate between
  workspaces; per-workspace session state included in `session.json`.

#### 6.15 Window tiling

- Win+←/→/↑/↓ tile half/quarter/center; snap preview polish (existing snap
  extended); "Tiling" toggle (manual only). Auto-arrange action to restore a
  saved window layout.

#### 6.16 Global search (`search.py`)

- Super+Space (or Win+S) opens a centered search box.
- Indexes: app names/descriptions, Notes filenames + content (lazy, on demand),
  Settings sections, activity log entries. Results carry **source attribution**
  and open the target app/file/setting on Enter.

#### 6.17 Screenshot tool

- Win+Shift+S captures the screen to `~/.lionos/screenshots/YYYYmmdd-HHMMSS.png`
  (use `pygame.image.save` on a copy of the screen, or blit). Toast with
  preview; screenshot event appended to activity log. Also reachable from the
  Power menu.

#### 6.18 New apps

- **Help** — self-documenting catalog: every app with description, tips,
  shortcuts; searchable; reachable from a "?" in each window chrome + launcher.
- **System Health** — scored audit: apps available, themes, widgets, animations
  on, profile complete → score /100 with stage label and top-3 suggested next
  steps; connections-style registry with "last checked" freshness.
- **Inbox + quick-capture** — Super+N opens a small always-on-top capture box
  appending to a unified inbox (To Do / Someday / Ideas); promote-to-task action.
- **Today / Timeline** — the activity log as a view (per-day timeline, app usage
  counts).
- **Focus mode** — user marks apps "not today"; they dim in the launcher, hide
  from taskbar recents, and their notifications are swallowed (toggleable).

### Phase 5 — Config, verification, release

#### 6.19 Settings app overhaul

Central panel with sections: **Appearance** (theme, accent, wallpaper),
**Motion** (Full/Reduced/None + feature flags), **Sound**, **Statusline**
(widget toggles), **Shortcuts** (view/remap core hotkeys), **System**
(session-resume toggle, clean uninstall of an app, reset config, About/Health).

#### 6.20 Smoothness & config hardening ("configure everything so it runs smoothly")

- Every subsystem reads config through `LionConfig` with sane defaults and
  validation; no config = still boots.
- All caches keyed by inputs + invalidated correctly (no stale render).
- Graceful degradation paths verified: no audio device, no display
  (`--headless`), very slow machine (motion=None → deterministic cached path),
  corrupt `session.json`/`profile.json` (fall back to defaults).
- Deterministic main loop with perf counters; a slow-frame invariant logs.

#### 6.21 Testing

Extend the pytest suite (headless, `SDL_VIDEODRIVER=dummy`):
- Icon renderer: every app scene renders without error at 16/32/64; cache hits.
- Session: save → restore round-trip preserves windows/positions/theme; corrupt
  file tolerated; checkpoint rotation.
- Activity log: append + query; Recents ordering.
- Catalog launcher: manifest completeness, categories, filtering.
- Wizard: profile write/idempotence/archive.
- Workspaces: switch moves windows; session includes workspace.
- Clipboard: copy/paste + history; Super+V data path.
- Notification center: create/timeout/clear.
- Sound: init guarded; no-audio path no-ops.
- Search: apps/notes/settings hits with source attribution.
- Theme contrast: WCAG-AA assertions for all 8 themes.
- New apps: launch + render + one interaction each.
- Existing 35 tests + headless smoke stay green.

#### 6.22 Release (2.0.0)

- README overhaul (new features, screenshots/diagrams, install unchanged:
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
- **Audio absence** → `sound.py` fully guarded; never raises.

## 8. Decisions taken

- Procedural vector icons (not PNG assets, not emoji) — theme-aware, crisp,
  no dependencies.
- No new third-party skills installed (apply design-review/debugging/TDD
  patterns directly; the useful ones are already installed).
- New apps added (Help, System Health, Inbox, Today).
- Version 2.0.0 "Majestic".
