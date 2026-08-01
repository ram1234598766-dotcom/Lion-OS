# Lion-OS Refinement — Design Spec

Date: 2026-08-01
Status: Approved by user
Goal: Make Lion-OS "the best in all aspects" — performance, shell completeness, visual identity, and app depth.

## Approach

**Approach B — Shell-layer rebirth.** Rebuild the desktop experience on a small rendering upgrade, then layer the evolved identity on top. No wholesale app rewrites (that's Approach C). Top 6 apps get real feature depth; the rest stay stable.

## 1. Performance Engine

- **Cached window chrome.** Each `Window` prerenders shadow, body, and titlebar into reusable `pygame.Surface`s. Invalidated only on resize / focus change / theme change / title change. Replaces the per-frame allocation in `kernel._draw_window` (currently 3+ surfaces per window per frame).
  - `Window.cache`: `{shadow, body, titlebar}` surfaces + a cache-key (`(rect.size, focused, state)` + theme id + title text).
  - `Window.invalidate_cache()` called on: `resize_with`, `maximize`, `restore`, `snap`, `focus`, `set_title`, theme switch.
  - `kernel._draw_window` blits cached surfaces; only redraws app content each frame.
- **Prerendered wallpaper.** Gradient rendered once into a surface at init + on theme/wallpaper change. Animated glow drawn onto a small cached overlay (rendered every N frames, not every frame).
- **Dirty-flag redraw.** `_dirty` (present but unused) becomes real: `kernel._draw` early-returns most layers when nothing changed. Content windows request repaint via `win._dirty = True`. Animation frames still force a redraw.
- **Font/text cache.** `kernel` keeps a small dict `{(size, bold): Font}` and a rendered-title cache keyed by `(text, color, size)`. Reused for taskbar, clock, launcher, titlebars.
- **Target:** no surface allocation inside the per-frame hot loop.

## 2. Shell Completeness

- **Desktop icons.** `DESKTOP_ICONS` is currently empty and `_draw_icons` is `pass`. Add real desktop icons:
  - Icon tiles rendered with `draw_app_tile()` (see §3).
  - Double-click (within 300ms, both hits in the icon rect) launches the app.
  - Single click selects (highlight ring); click empty desktop clears selection.
  - Right-click on a desktop icon → small context menu (Open / Launch); right-click on empty desktop → desktop menu (Open Terminal, Change Wallpaper, Settings, Refresh).
- **Working power menu.** Currently a bare title. Add buttons: Lock (back to login screen), Restart (animated, then reboot to login), Shutdown (fade out + quit), Sleep (dim + lock), each with icon + label + hover. Power menu panel drawn as a glass panel; click-outside closes.
- **Alt-Tab window switcher.** Overlay strip of running windows with title + tile. `Alt` held, `Tab` cycles, release `Alt` activates the selected window. Keyboard-only nav.
- **Keyboard-first nav.** Win-key (K_LSUPER / K_RSUPER) toggles the launcher. In launcher: arrow keys move grid focus, Enter launches, Esc closes, typing filters. Also global: `Ctrl+W` closes focused window? (optional, keep minimal).
- **Window animations.** Reuse unused `anim_scale`:
  - Open: scale 0.85→1.0 + fade-in over ~120ms (draw scaled chrome, skip during drag).
  - Close: fade-out + shrink ~90ms before window actually removed.
  - Minimize: shrink toward taskbar position ~120ms then hide.
  - Maximize/restore: animate rect toward target (~150ms).
  - Focus change: titlebar accent / border glow eases to focused color.
  - Gate all behind `config.anim_enabled` and a `self._anim_active` guard so tests run deterministically (dt-driven, but snap-to-end when `anim_enabled` off or headless).
- **Snap corners.** Extend `_update_snap_preview` + drag-release to trigger `snap("tl"/"tr"/"bl"/"br")` when the cursor is within `SNAP_MARGIN` of a corner (both x and y near edges). Preview shows the corner rect.

## 3. Identity Evolution

- **Theme model.** Extend `Theme` with: `titlebar_top`, `titlebar_bottom`, `glow`, `accent2`, `icon_grad1`, `icon_grad2`. Add 2 new themes ("Sunset", "Midnight"). Update existing 6 themes with the new fields (computed defaults so tests that construct `Theme(...)` don't break).
- **Animated theme transitions.** When theme changes, `kernel` interpolates live between old and new palette over ~0.4s using `theme.blend`. Store `self._theme_from`, `self._theme_to`, `self._theme_t`. Draw uses `self.theme` (the current blended instance). Skip in headless/test mode (snap).
- **Real app icons.** `draw_app_tile(surface, rect, app, theme)` in `widgets.py`: rounded gradient tile (icon_grad1→icon_grad2) + glyph, with subtle border and pressed/hover variant. Used in: launcher grid, taskbar, desktop icons, About screen.
- **Launcher upgrade.** Category tabs (All / per-category), search box, keyboard grid nav, recent-apps row (from `config.mru_apps`, updated on launch). Glass panel look.
- **Login/boot polish.** Login: avatar with accent ring, animated background glow, better error shake. Boot: progress bar with shimmer sweep, centered lion logo.

## 4. App-Depth Pass (top 6)

- **Calculator:** keyboard input (0-9, +,-,*,/,.,=,Enter,Backspace), history panel (last N expressions), percent.
- **Terminal:** command history (↑/↓ recall), cwd prompt, better `help` output.
- **File Manager:** breadcrumbs bar, back/forward history, right-click context menu (Open / Rename / Delete / Copy path), double-click folder navigation, symlink-safe.
- **Text Editor:** line numbers, find-in-text (Ctrl+F box), dirty indicator in title.
- **Media Player:** seek bar (draggable), volume slider, next/prev, playlist display, real elapsed/total time.
- **Notes:** autosave to `~/.lionos/notes/`, note list sidebar, title from first line.

Each stays within its existing file; no new app files unless required.

## 5. Testing

Extend `tests/test_lionos.py`:
- Window chrome cache invalidation on resize/focus.
- Snap corners (tl/tr/bl/br) produce correct rects.
- Alt-Tab selects next window; launcher keyboard nav moves focus.
- Theme transition reaches target palette; animation snap when disabled.
- Calculator keyboard entry produces correct expression.
- Terminal history recall restores previous command.
- Notes autosave writes a file; File Manager breadcrumb builds.

Keep all 22 existing tests passing.

## Non-Goals

- No wholesale app rewrites (Approach C rejected).
- No new apps beyond what exists (15).
- No sound system, no networking beyond current browser/assistant.
- No change to the packaging / CI / release workflows unless a bug demands it.

## Risks

- Animation loops must not fight the dirty-redraw system (guard with `anim_enabled` and a single "animating" flag).
- Theme blend adds per-frame color math; keep it to a cached interpolated palette, not per-pixel.
- Windows/chrome cache must invalidate on *every* thing that changes appearance (title, focus, size, theme) or stale visuals appear.
