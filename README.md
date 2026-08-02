<div align="center">

# 🦁 Lion-OS

**A complete graphical desktop operating system that runs inside Python.**

Boot, login, a full window manager with snapping, a taskbar with desktop icons,
and 15 built-in apps — all rendered with Pygame. Installable from PyPI and started
with a single command.

[Install](#-install) · [Quick Start](#-quick-start) · [Apps](#-built-in-apps) · [Features](#-features) · [Themes](#-themes) · [Development](#-development)

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![version](https://img.shields.io/badge/version-1.1.1-orange)
![tests](https://img.shields.io/badge/tests-35%20passing-brightgreen)

</div>

---

## ✨ What is Lion-OS?

Lion-OS is a genuine desktop environment built from scratch in Python. It has its
own **boot sequence**, a **login screen**, a **window manager** with drag / resize /
snap-to-edge and corners, **desktop icons**, an **Alt-Tab switcher**, a **taskbar
with a live launcher**, a working **power menu**, and a suite of **15 built-in
applications** — including a **built-in AI assistant** that works with local and
cloud models.

The v1.1 release ("Refined") added a performance engine (cached window chrome,
prerendered wallpaper), window animations, animated theme transitions, and deep
feature upgrades across the most-used apps.

The v1.1.1 patch release focuses on **memory efficiency**: the kernel now reuses
full-screen overlay, glow, taskbar and fade surfaces instead of allocating them
every frame; app-icon tiles and glass panels are cached; fonts are shared through
a global cache instead of being rebuilt per draw call; and the System Monitor's
graph no longer allocates a fresh fill surface each frame.

It's designed to be simple to run and genuinely fun to explore:

```
lionos
```

That's it. The desktop boots, you log in, and you have a working graphical OS.

---

## 🚀 Install

### Option 1 — Install from source (recommended)

```bash
git clone https://github.com/ram1234598766-dotcom/Lion-OS.git
cd Lion-OS
python -m pip install .
lionos
```

### Option 2 — Install from PyPI

```bash
python -m pip install lion-os-desktop
lionos
```

> **Requirements:** Python 3.9+. On first run Lion-OS installs nothing extra —
> Pygame and psutil are dependencies and come automatically.

### Option 3 — Run without installing

```bash
git clone https://github.com/ram1234598766-dotcom/Lion-OS.git
cd Lion-OS
python -m pip install pygame-ce psutil requests
python -m lionos
```

---

## 🖥 Quick Start

| Command | What it does |
|---|---|
| `lionos` | Boot the desktop (windowed) |
| `lionos --fullscreen` | Boot fullscreen |
| `lionos --theme ocean` | Boot with a theme (dark, light, ocean, forest, violet, rose, sunset, midnight) |
| `lionos --screen 1600x900` | Boot at a specific resolution |
| `lionos --reset` | Reset saved configuration |
| `lionos --headless` | Run the smoke test (no display, for CI) |
| `lionos --version` | Print the version |

### First-time use

1. Run `lionos`. The OS boots with a progress bar, then shows the login screen.
2. Press **Enter** to log in as the default user (or set a password in `~/.lionos/config.json`).
3. Click the 🦁 **Start button** (bottom-left) to open the launcher, then search for any app.
4. **Double-click a desktop icon** to launch an app, or right-click the desktop for a context menu.

### Handy shortcuts

| Key | What it does |
|---|---|
| **Win** | Toggle the launcher |
| **Alt-Tab** | Switch between open windows |
| **Alt-Tab → Tab** | Cycle through windows, release Alt to activate |
| **Esc** | Close launcher / menus / power menu |
| **↑ ↓ ← → / Enter** | Navigate the launcher grid and launch |

---

## 📱 Built-in Apps

| App | Icon | Description |
|---|---|---|
| **AI Assistant** | 💬 | Chat with a built-in assistant — Ollama, OpenAI or DeepSeek |
| **Welcome** | 👋 | Getting-started tour of the OS |
| **File Manager** | 📁 | Breadcrumbs, back/forward history, right-click context menu (open/rename/delete/copy path) |
| **Terminal** | ▣ | Full interactive shell with **command history** (↑/↓), cwd prompt, built-in commands |
| **Text Editor** | ✎ | Code editing with syntax highlighting, **line numbers**, Ctrl+S, Ctrl+F find |
| **Calculator** | ∑ | **Keyboard input**, history panel, percent — safe AST-based evaluation |
| **Paint** | 🎨 | Canvas with brushes, shapes, fill, undo/redo, save to PNG |
| **Notes** | 🗒 | **Autosaving** per-note files in `~/.lionos/notes/`, note sidebar, title from first line |
| **System Monitor** | 📊 | Live CPU / RAM / disk / network graphs |
| **Settings** | ⚙ | Themes, appearance, AI provider, system info, config reset |
| **Media Player** | 🎵 | **Draggable seek bar**, volume slider, playlist, next/prev, shuffle & loop |
| **Browser** | 🌐 | Lightweight web reader & search |
| **App Store** | 🛍 | Install Python packages via pip from inside the OS |
| **About** | ℹ | Version and platform info |
| **UI Toolkit** | 🧰 | Interactive demo of every widget |

### 🧠 AI Assistant

Open **AI Assistant**, then configure the provider in **Settings → AI Assistant**:

| Provider | Endpoint | Model |
|---|---|---|
| **Ollama** (default, local) | `http://localhost:11434/v1` | `llama3` |
| **OpenAI** | `https://api.openai.com/v1` | `gpt-4o-mini` |
| **DeepSeek** | `https://api.deepseek.com/v1` | `deepseek-chat` |

API keys are read from the environment (`OPENAI_API_KEY`, `DEEPSEEK_API_KEY`) or
stored in `~/.lionos/config.json`. Nothing is hardcoded. For Ollama, run
`ollama serve` locally first.

---

## 🎨 Themes

Eight built-in themes with a glassmorphism look, switchable live from Settings.
Theme changes **animate smoothly** between palettes:

- **Dark** · **Light** · **Ocean** · **Forest** · **Violet** · **Rose** · **Sunset** · **Midnight**

---

## 🚀 Features

- **Performance engine** — cached window chrome (shadow/body/titlebar), prerendered
  wallpaper, dirty-flag redraw and a font cache keep the desktop smooth at 60fps.
- **Memory-efficient rendering** — full-screen overlays, glow, taskbar and fade
  surfaces are reused instead of reallocated each frame; app-icon tiles, glass
  panels and fonts are cached; the System Monitor's graphs reuse one fill surface.
- **Desktop icons** — double-click to launch, single-click to select, right-click
  the desktop for a context menu.
- **Window manager** — drag, resize, **snap to edges and corners**, maximize,
  minimize with **open/close/minimize animations**, Alt-Tab switcher.
- **Power menu** — lock, sleep, restart and shutdown from the taskbar, with a
  fade-out animation.
- **Launcher** — search-first with **category tabs**, keyboard grid navigation and
  a recent-apps row.
- **Keyboard-first** — Win-key launcher, arrow-key navigation, Alt-Tab window
  switching.
- **Animated theme transitions** — switching themes cross-fades every color.
- **Shared icon tiles** — the same gradient app icons appear in the launcher,
  taskbar, desktop and About screen.

---

## 🧱 Architecture

```
lionos/
├── cli.py          # `lionos` command-line entry point
├── kernel.py       # desktop env: boot, login, icons, taskbar, launcher, power menu
├── wm.py           # window manager: drag, resize, snap, focus, z-order
├── theme.py        # color themes & blending
├── config.py       # persistent user configuration (~/.lionos/config.json)
├── widgets.py      # UI toolkit: buttons, inputs, sliders, lists, menus
├── ai/             # AI provider backends (Ollama / OpenAI / DeepSeek)
└── apps/           # 15 built-in applications
    ├── base.py     # App base class + registry
    └── ...         # calculator, terminal, paint, notes, etc.
```

New apps are trivial to add:

```python
from lionos.apps.base import App

class MyApp(App):
    name = "My App"
    icon = "✨"
    def draw(self, surface, rect):
        ...  # draw into the window

# register in lionos/apps/__init__.py
```

---

## 🧪 Tests & CI

Run the automated suite (headless — no display needed):

```bash
python -m pip install -e ".[dev]"
pytest
```

Tests cover boot, login, app registration, app rendering, calculator math
(mouse + keyboard), window move/snap/close, corner snapping, Alt-Tab, launcher
keyboard nav, desktop icons, theme switching + transitions, window chrome caching,
terminal history and notes autosave — plus the headless smoke test.

CI (`.github/workflows/ci.yml`) runs the full suite on every push and automatically
builds a wheel + sdist and attaches them to a GitHub Release on tags. Tag pushes
create the GitHub release only; publishing to PyPI is opt-in via a manual
workflow run.

---

## 📦 Releases

Pre-built wheels are attached to [GitHub Releases](https://github.com/ram1234598766-dotcom/Lion-OS/releases):

```
pip install https://github.com/ram1234598766-dotcom/Lion-OS/releases/download/v1.1.1/lion_os_desktop-1.1.1-py3-none-any.whl
```

---

## 🛠 Development

```bash
git clone https://github.com/ram1234598766-dotcom/Lion-OS.git
cd Lion-OS
python -m pip install -e ".[dev]"
pytest                      # run tests
python -m lionos --headless # smoke test
lionos                      # run the desktop
```

---

## 📄 License

MIT © Mrityunjay. See [LICENSE](LICENSE).

<div align="center">

**Made with 💛 and Pygame.**

</div>
