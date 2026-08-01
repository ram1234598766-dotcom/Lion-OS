"""Lion-OS kernel — the main desktop environment and event loop."""

from __future__ import annotations

import os
import random
import sys
import time
from typing import Dict, List, Optional

import pygame

from . import __version__
from .config import ConfigStore, LionConfig, ensure_config_dir
from .theme import Theme, THEMES, blend
from .wm import Window, WindowManager, TITLEBAR_H, WINDOW_STATE_MAXIMIZED, WINDOW_STATE_MINIMIZED
from .widgets import Menu, Toast, draw_glass_panel, rounded_rect

BOOT_LINES = [
    ("Lion-OS Kernel v" + __version__, True),
    ("Initializing graphics subsystem...", False),
    ("Loading window manager...", False),
    ("Mounting virtual filesystem...", False),
    ("Starting services...", False),
    ("Loading desktop environment...", False),
    ("Pride edition ready.", True),
]

DESKTOP_ICONS = [
    # (label, app name)
]


class LionOS:
    """The main desktop environment."""

    def __init__(self, config: LionConfig = None):
        self.config_store = ConfigStore()
        self.config = config or self.config_store.cfg
        self.theme: Theme = THEMES.get(self.config.theme, THEMES["dark"])

        pygame.init()
        pygame.font.init()
        pygame.display.set_caption("Lion-OS — Pride Edition")
        self.screen_w = self.config.screen_w
        self.screen_h = self.config.screen_h

        flags = 0
        if self.config.resolution == "fullscreen":
            flags = pygame.FULLSCREEN | pygame.SCALED
        self.screen = pygame.display.set_mode((self.screen_w, self.screen_h), flags)
        self.screen_rect = self.screen.get_rect()

        self.clock = pygame.time.Clock()
        self.running = True
        self.booted = False
        self.logged_in = False
        self.shutdown = False

        # state
        self.wm = WindowManager(self.screen_rect, self.theme)
        self.apps_registry = None          # set by apps loader
        self.launched: Dict[str, object] = {}   # singleton instances
        self.instances: List = []          # all running app instances
        self.toasts: List[Toast] = []
        self.menus: List[Menu] = []
        self.launcher_open = False
        self.launcher_search = ""
        self.launcher_filter = ""
        self.power_menu_open = False
        self.context_menu = None           # (pos, items)

        # boot state
        self._boot_progress = 0.0
        self._boot_lines_done = 0
        self._boot_ready = False

        # login state
        self._login_attempt = 0
        self._login_pw = ""
        self._login_error = ""
        self._login_focus = 0
        self._login_clock = time.time()

        # decorations
        self._show_clock_sec = False

        self._bg_shift = 0.0
        self._dt = 0.016

        # hidden for testing
        self._no_draw = os.environ.get("LION_OS_HEADLESS") == "1"

        self._load_apps()

    # ------------------------------------------------------------------ apps
    def _load_apps(self):
        from .apps import load_apps
        self.apps_registry = load_apps()

    def launch(self, name: str, **kwargs):
        cls = self.apps_registry.get(name)
        if cls is None:
            self.show_toast("Lion-OS", f"App '{name}' not found", "error")
            return None
        if cls.singleton and name in self.launched and self.launched[name]:
            inst = self.launched[name]
            if inst.window.state == WINDOW_STATE_MINIMIZED:
                inst.window.restore()
            self.wm.focus(inst.window)
            return inst
        inst = cls(self, **kwargs)
        self.instances.append(inst)
        if cls.singleton:
            self.launched[name] = inst
        inst.on_open()
        return inst

    # ------------------------------------------------------------------ utils
    def show_toast(self, title, message, kind="info"):
        self.toasts.append(Toast(title, message, self.theme, kind=kind))
        if len(self.toasts) > 4:
            self.toasts.pop(0)

    def open_menu(self, items, pos):
        font = pygame.font.Font(None, self.config.font_size)
        m = Menu(items, pos, font, self.theme)
        self.menus.append(m)

    def close_menus(self):
        for m in self.menus:
            m.visible = False
        self.menus = []
        self.context_menu = None

    def set_theme(self, name: str):
        self.theme = THEMES.get(name, self.theme)
        self.config_store.set(theme=name)
        self.wm.theme = self.theme

    def set_wallpaper(self, kind=None, color=None):
        if kind:
            self.config_store.set(wallpaper=kind)
            self.config.wallpaper = kind
        if color:
            self.config_store.set(wallpaper_color=color)
            self.config.wallpaper_color = color

    # ------------------------------------------------------------------ boot
    def _update_boot(self, dt):
        self._boot_progress += dt * 14
        self._boot_lines_done = min(len(BOOT_LINES) - 1,
                                    int(self._boot_progress / (100 / len(BOOT_LINES))))
        if self._boot_progress >= 100:
            self._boot_ready = True

    # ------------------------------------------------------------------ loop
    def run(self):
        while self.running:
            dt = min(0.05, self.clock.tick(60) / 1000.0)
            self._dt = dt
            for event in pygame.event.get():
                self._handle_event(event)
            self._update(dt)
            if not self._no_draw:
                self._draw()
            else:
                self._headless_tick()
        self.shutdown = True
        pygame.quit()
        return 0

    def _headless_tick(self):
        """When LION_OS_HEADLESS=1, keep the loop alive without rendering
        so automated smoke tests can drive it."""
        if self._boot_progress >= 100 and self.logged_in:
            if self._smoke_test_done:
                self.running = False

    def _update(self, dt):
        self._bg_shift += dt * 0.05
        if not self.booted:
            self._update_boot(dt)
            if self._boot_ready:
                self.booted = True
            return

        if not self.logged_in:
            self._login_clock += dt
            return

        for t in self.toasts:
            t.update(dt)
        self.toasts = [t for t in self.toasts if not t.done]

        for inst in list(self.instances):
            if inst.closed:
                if inst in self.instances:
                    self.instances.remove(inst)
                if self.apps_registry and inst.window.app and \
                   self.launched.get(inst.window.app.name) is inst:
                    self.launched.pop(inst.window.app.name, None)
                continue
            if inst.window.state != WINDOW_STATE_MINIMIZED:
                inst.update(dt)
            # window content rect may have changed
            if inst.window.content_rect != inst.rect:
                inst.rect = pygame.Rect(inst.window.content_rect)
                inst.on_resize(inst.rect)
            inst._last = pygame.Rect(inst.window.content_rect)

    def _handle_event(self, event):
        if event.type == pygame.QUIT:
            self._request_quit()
            return

        if not self.booted:
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_SPACE, pygame.K_RETURN):
                    self._skip_boot()
            return

        if not self.logged_in:
            self._handle_login_event(event)
            return

        # context menu
        if self.context_menu:
            consumed = self.context_menu[2].handle_event(event, event.pos, self.theme) if hasattr(self.context_menu[2], "handle_event") else False
            if not consumed:
                self.context_menu = None
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.launcher_open:
                    self.launcher_open = False
                    return
                if self.menus:
                    self.close_menus()
                    return

        # power menu
        if self.power_menu_open:
            self._handle_power_menu(event)
            return

        # launcher (fullscreen overlay) gets priority when open
        if self.launcher_open:
            self._handle_launcher_event(event)
            return

        # taskbar interactions
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) and event.button == 1:
            tb_h = 46
            tb_top = self.screen_h - tb_h
            pos = event.pos
            if pos[1] >= tb_top:
                start_r = pygame.Rect(10, tb_top + 6, 34, 34)
                if start_r.collidepoint(pos):
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        self.launcher_open = not self.launcher_open
                        self.power_menu_open = False
                        return
                # power menu toggle (right of start)
                power_r = pygame.Rect(48, tb_top + 6, 24, 24)
                if power_r.collidepoint(pos):
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        self.power_menu_open = not self.power_menu_open
                        self.launcher_open = False
                        return
                # running app icons
                x = 82
                for inst in list(self.instances):
                    if inst.closed:
                        continue
                    item = pygame.Rect(x, tb_top + 6, 44, 34)
                    if item.collidepoint(pos):
                        if event.type == pygame.MOUSEBUTTONDOWN:
                            if inst.window.state == WINDOW_STATE_MINIMIZED:
                                inst.window.restore()
                                self.wm.focus(inst.window)
                            elif inst.window is self.wm.focused:
                                inst.window.minimize()
                            else:
                                self.wm.focus(inst.window)
                        return
                    x += 52
                    if x > self.screen_w - 260:
                        break
                # clock area right-click opens power? keep simple: ignore

        # window manager first
        if self.wm.handle_event(event):
            return

        # dispatch to focused app
        win = self.wm.focused
        if win and win.state != WINDOW_STATE_MINIMIZED and win.app:
            local = event.pos if hasattr(event, "pos") else None
            cr = win.content_rect
            if local and cr.collidepoint(local):
                local_pos = (local[0] - cr.x, local[1] - cr.y)
            elif local and win.titlebar_rect.collidepoint(local):
                local_pos = None
            else:
                local_pos = None
            if local_pos is not None and win.app.handle_event(event, local_pos):
                return

    # ---------------------------------------------------------------- boot UI
    def _skip_boot(self):
        self._boot_progress = 100
        self._boot_ready = True
        self.booted = True

    # --------------------------------------------------------------- login UI
    def _handle_login_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self._login_attempt += 1
                if self.config.auto_login or not self.config.password or \
                   self._login_pw == self.config.password:
                    self._do_login()
                else:
                    self._login_error = "Incorrect password. Try again."
                    self._login_pw = ""
            elif event.key == pygame.K_BACKSPACE:
                self._login_pw = self._login_pw[:-1]
            elif event.unicode and event.unicode.isprintable():
                self._login_pw += event.unicode

    def _do_login(self):
        self.logged_in = True
        self._login_error = ""
        self.launcher_open = False
        # reopen running apps after login
        from .apps import AUTO_LAUNCH
        for app_name in AUTO_LAUNCH:
            try:
                self.launch(app_name)
            except Exception:
                pass
        self.show_toast("Welcome", f"Welcome back, {self.config.username}!", "success")

    # ------------------------------------------------------------- launcher UI
    def _handle_launcher_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.launcher_open = False
                return
            if event.key == pygame.K_BACKSPACE:
                self.launcher_search = self.launcher_search[:-1]
                return
            if event.unicode and (event.unicode.isprintable() or event.unicode == " "):
                self.launcher_search += event.unicode
                return
            if event.key == pygame.K_RETURN:
                # launch first result
                results = self._launcher_results()
                if results:
                    self.launch(results[0].name)
                    self.launcher_open = False
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # click on app tile
            x, y = event.pos
            if self._launcher_tile_at(x, y) is not None:
                name = self._launcher_tile_at(x, y)
                self.launch(name)
                self.launcher_open = False

    def _launcher_results(self):
        q = self.launcher_search.lower()
        apps = list(self.apps_registry.all().values())
        if q:
            apps = [a for a in apps if q in a.name.lower() or q in a.category.lower() or
                    q in a.description.lower()]
        return apps

    def _launcher_tile_at(self, x, y):
        if not self.launcher_open:
            return None
        results = self._launcher_results()
        if not results:
            return None
        cols = 8
        size = 96
        start_x = (self.screen_w - cols * size) // 2
        for i, app in enumerate(results):
            cx = start_x + (i % cols) * size
            cy = 170 + (i // cols) * size
            if x in range(cx, cx + size) and y in range(cy, cy + size):
                return app.name
        return None

    # -------------------------------------------------------------- power menu
    def _handle_power_menu(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.power_menu_open = False
        # handled during draw via buttons; simple: click outside closes

    def _request_quit(self):
        self.running = False

    # ------------------------------------------------------------- window chrome
    def _hit_window_button(self, win: Window, pos) -> Optional[str]:
        """Return which chrome button was clicked: close/min/max."""
        if win.state == WINDOW_STATE_MAXIMIZED:
            return None
        tr = win.titlebar_rect
        b = 16
        right = tr.right - 8
        close_rect = pygame.Rect(right - b, tr.centery - b // 2, b, b)
        max_rect = pygame.Rect(right - 3 * b - 8, tr.centery - b // 2, b, b)
        min_rect = pygame.Rect(right - 2 * b - 8, tr.centery - b // 2, b, b)
        if close_rect.collidepoint(pos):
            if win.app:
                win.app.close()
            else:
                self.wm.remove_window(win)
            return "close"
        if max_rect.collidepoint(pos):
            win.toggle_maximize(self.screen_rect)
            return "max"
        if min_rect.collidepoint(pos):
            win.minimize()
            return "min"
        return None

    # ------------------------------------------------------------------ draw
    def _draw(self):
        self._draw_wallpaper()
        self._draw_icons()
        self._draw_windows()
        self._draw_launcher()
        self._draw_power_menu()
        self._draw_context_menu()
        self._draw_taskbar()
        self._draw_toasts()
        if not self.booted:
            self._draw_boot()
        elif not self.logged_in:
            self._draw_login()
        pygame.display.flip()

    def _draw_wallpaper(self):
        top = self.theme.wallpaper_top
        bottom = self.theme.wallpaper_bottom
        h = self.screen_h
        for y in range(0, h, 4):
            t = y / max(1, h)
            color = blend(top, bottom, t)
            pygame.draw.line(self.screen, color, (0, y), (self.screen_w, y))
        # subtle animated glow
        cx = self.screen_w // 2
        cy = self.screen_h // 2
        for i in range(3):
            radius = int(180 + self._bg_shift * 20 + i * 90)
            alpha = 10 - i * 3
            s = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
            pygame.draw.circle(s, self.theme.accent + (alpha,), (cx, cy), radius, 1)
            self.screen.blit(s, (0, 0))

    def _draw_icons(self):
        """Desktop icons are kept minimal; the launcher is the primary app menu."""
        pass

    def _draw_windows(self):
        # draw from back to front
        for win in self.wm.windows:
            if not win.visible or win.state == WINDOW_STATE_MINIMIZED:
                continue
            self._draw_window(win)
        self.wm.draw_snap_preview(self.screen, self.theme)

    def _draw_window(self, win: Window):
        if win.state == WINDOW_STATE_MAXIMIZED:
            rect = win.rect
        else:
            rect = win.rect
            # shadow
            sh = pygame.Surface((rect.width + 12, rect.height + 12), pygame.SRCALPHA)
            pygame.draw.rect(sh, self.theme.shadow[:3] + (120,), (6, 6, rect.width, rect.height),
                             border_radius=12)
            self.screen.blit(sh, (rect.x - 6, rect.y - 6))

        # window body
        body = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        bg = self.theme.surface if len(self.theme.surface) == 3 else self.theme.surface
        alpha = 246
        bg_a = bg + (alpha,) if len(bg) == 3 else bg
        pygame.draw.rect(body, bg_a, body.get_rect(), border_radius=12)
        if win is self.wm.focused:
            border = self.theme.accent + (60,) if len(self.theme.accent) == 3 else self.theme.accent
            pygame.draw.rect(body, border, body.get_rect(), 1, border_radius=12)
        else:
            pygame.draw.rect(body, (255, 255, 255, 30), body.get_rect(), 1, border_radius=12)
        self.screen.blit(body, rect.topleft)

        # titlebar
        tr = win.titlebar_rect
        tb = pygame.Surface((tr.width, TITLEBAR_H), pygame.SRCALPHA)
        pygame.draw.rect(tb, (255, 255, 255, 14), tb.get_rect())
        self.screen.blit(tb, tr.topleft)
        font = pygame.font.Font(None, self.config.font_size)
        active = win is self.wm.focused
        tcol = self.theme.text if active else self.theme.text_dim
        title_img = font.render(win.title or win.app.name, True, tcol)
        self.screen.blit(title_img, (tr.x + 12, tr.centery - title_img.get_height() // 2))
        # window buttons
        self._draw_window_buttons(win, tr)

        # content
        cr = win.content_rect
        if cr.width > 0 and cr.height > 0:
            clip = pygame.Rect(cr)
            old = self.screen.get_clip()
            self.screen.set_clip(clip)
            if win.app:
                try:
                    win.app.draw(self.screen, cr)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self._draw_error_screen(cr, e)
            self.screen.set_clip(old)

    def _draw_error_screen(self, rect, error):
        font = pygame.font.Font(None, 18)
        s = pygame.Surface(rect.size, pygame.SRCALPHA)
        s.fill((40, 20, 20, 220))
        img = font.render("Application error", True, (255, 200, 200))
        s.blit(img, (20, 20))
        detail = font.render(str(error)[:80], True, (255, 230, 230))
        s.blit(detail, (20, 50))
        self.screen.blit(s, rect.topleft)

    def _draw_window_buttons(self, win: Window, tr):
        font = pygame.font.Font(None, 16)
        b = 16
        right = tr.right - 8
        cy = tr.centery
        # minimize
        min_rect = pygame.Rect(right - 2 * b - 8, cy - b // 2, b, b)
        if min_rect.collidepoint(pygame.mouse.get_pos()):
            pygame.draw.rect(self.screen, self.theme.hover[:3] if len(self.theme.hover) == 3 else self.theme.hover, min_rect, border_radius=4)
        pygame.draw.line(self.screen, self.theme.text_dim, (min_rect.centerx - 4, min_rect.centery), (min_rect.centerx + 4, min_rect.centery), 2)
        # maximize
        max_rect = pygame.Rect(right - 3 * b - 8, cy - b // 2, b, b)
        if max_rect.collidepoint(pygame.mouse.get_pos()):
            pygame.draw.rect(self.screen, self.theme.hover[:3] if len(self.theme.hover) == 3 else self.theme.hover, max_rect, border_radius=4)
        if win.state == WINDOW_STATE_MAXIMIZED:
            pygame.draw.rect(self.screen, self.theme.text_dim, (max_rect.centerx - 4, max_rect.centery - 4, 8, 8), 1)
        else:
            pygame.draw.rect(self.screen, self.theme.text_dim, (max_rect.centerx - 4, max_rect.centery - 4, 8, 8), 1)
        # close
        close_rect = pygame.Rect(right - b, cy - b // 2, b, b)
        if close_rect.collidepoint(pygame.mouse.get_pos()):
            pygame.draw.rect(self.screen, self.theme.danger[:3], close_rect, border_radius=4)
        pygame.draw.line(self.screen, self.theme.text if close_rect.collidepoint(pygame.mouse.get_pos()) else self.theme.text_dim,
                         (close_rect.centerx - 4, close_rect.centery - 4),
                         (close_rect.centerx + 4, close_rect.centery + 4), 2)
        pygame.draw.line(self.screen, self.theme.text if close_rect.collidepoint(pygame.mouse.get_pos()) else self.theme.text_dim,
                         (close_rect.centerx - 4, close_rect.centery + 4),
                         (close_rect.centerx + 4, close_rect.centery - 4), 2)

    def _draw_taskbar(self):
        h = 46
        tb = pygame.Rect(0, self.screen_h - h, self.screen_w, h)
        # translucent bar
        s = pygame.Surface((self.screen_w, h), pygame.SRCALPHA)
        base = self.theme.taskbar
        pygame.draw.rect(s, base[:4] if len(base) == 4 else base + (235,), s.get_rect())
        self.screen.blit(s, tb.topleft)
        pygame.draw.line(self.screen, (255, 255, 255, 30), (0, tb.top), (self.screen_w, tb.top))

        # start button
        start_r = pygame.Rect(10, tb.y + 6, 34, 34)
        self._draw_start_button(start_r)
        # running apps
        x = 52
        for inst in self.instances:
            if inst.closed:
                continue
            app = inst.window.app
            item = pygame.Rect(x, tb.y + 6, 44, 34)
            focused = inst.window is self.wm.focused
            if item.collidepoint(pygame.mouse.get_pos()):
                pygame.draw.rect(self.screen, self.theme.hover[:3] if len(self.theme.hover) == 3 else self.theme.hover, item, border_radius=6)
            elif focused:
                pygame.draw.rect(self.screen, self.theme.taskbar_active[:3] + (40,), item, border_radius=6)
            pygame.draw.rect(self.screen, self.theme.taskbar_active[:3] if focused else (100, 100, 120), (item.x + 14, item.bottom - 3, 16, 3), border_radius=2)
            font = pygame.font.Font(None, self.config.font_size)
            img = font.render(app.icon, True, self.theme.text)
            self.screen.blit(img, img.get_rect(center=item.center))
            # tooltip
            if item.collidepoint(pygame.mouse.get_pos()):
                tip = font.render(app.name, True, self.theme.text)
                bg = pygame.Surface((tip.get_width() + 16, tip.get_height() + 8), pygame.SRCALPHA)
                pygame.draw.rect(bg, (40, 40, 50, 220), bg.get_rect(), border_radius=6)
                bg.blit(tip, (8, 4))
                self.screen.blit(bg, (item.x, tb.y - tip.get_height() - 16))
            x += 52
            if x > self.screen_w - 260:
                break

        # clock
        clock_font = pygame.font.Font(None, 18)
        now = time.localtime()
        if self.config.clock_24h:
            timestr = time.strftime("%H:%M", now)
        else:
            timestr = time.strftime("%I:%M %p", now).lstrip("0")
        date = time.strftime("%a %b %d", now)
        tc = self.theme.text
        t1 = clock_font.render(timestr, True, tc)
        t2 = clock_font.render(date, True, self.theme.text_dim)
        tx = self.screen_w - t1.get_width() - 16
        self.screen.blit(t1, (tx, tb.y + 5))
        self.screen.blit(t2, (tx, tb.y + 24))

    def _draw_start_button(self, r):
        if r.collidepoint(pygame.mouse.get_pos()):
            pygame.draw.rect(self.screen, self.theme.hover[:3] if len(self.theme.hover) == 3 else self.theme.hover, r, border_radius=8)
        if self.launcher_open:
            pygame.draw.rect(self.screen, self.theme.active[:3] if len(self.theme.active) == 3 else self.theme.active, r, border_radius=8)
        pygame.draw.circle(self.screen, self.theme.accent, r.center, 13)
        pygame.draw.circle(self.screen, (255, 255, 255), (r.centerx - 3, r.centery - 3), 4)

    def _draw_launcher(self):
        if not self.launcher_open:
            return
        # dim background
        dim = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        dim.fill((10, 10, 18, 180))
        self.screen.blit(dim, (0, 0))
        # title
        font = pygame.font.Font(None, 30)
        title = font.render("Lion-OS Launcher", True, self.theme.text)
        self.screen.blit(title, title.get_rect(midtop=(self.screen_w // 2, 60)))
        # search box
        font = pygame.font.Font(None, self.config.font_size)
        search_r = pygame.Rect(self.screen_w // 2 - 200, 100, 400, 36)
        pygame.draw.rect(self.screen, self.theme.surface, search_r, border_radius=10)
        pygame.draw.rect(self.screen, self.theme.accent, search_r, 1, border_radius=10)
        txt = self.launcher_search or "Search apps..."
        col = self.theme.text if self.launcher_search else self.theme.text_dim
        img = font.render(txt, True, col)
        self.screen.blit(img, (search_r.x + 12, search_r.centery - img.get_height() // 2))
        # results grid
        results = self._launcher_results()
        if results:
            cols = 8
            size = 96
            start_x = (self.screen_w - cols * size) // 2
            for i, app in enumerate(results):
                cx = start_x + (i % cols) * size
                cy = 170 + (i // cols) * size
                tile = pygame.Rect(cx, cy, size, size)
                if tile.collidepoint(pygame.mouse.get_pos()):
                    pygame.draw.rect(self.screen, self.theme.hover[:3] if len(self.theme.hover) == 3 else self.theme.hover, tile, border_radius=12)
                ic = pygame.Rect(cx + 20, cy + 16, 56, 56)
                pygame.draw.rect(self.screen, self.theme.icon_bg[:3] + (40,), ic, border_radius=14)
                ifont = pygame.font.Font(None, 34)
                icimg = ifont.render(app.icon, True, self.theme.accent)
                self.screen.blit(icimg, icimg.get_rect(center=ic.center))
                lfont = pygame.font.Font(None, 15)
                limg = lfont.render(app.name, True, self.theme.text)
                self.screen.blit(limg, limg.get_rect(midtop=(tile.centerx, ic.bottom + 6)))
        else:
            img = font.render("No apps match your search.", True, self.theme.text_dim)
            self.screen.blit(img, img.get_rect(center=(self.screen_w // 2, self.screen_h // 2)))

    def _draw_power_menu(self):
        if not self.power_menu_open:
            return
        dim = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        dim.fill((10, 10, 18, 180))
        self.screen.blit(dim, (0, 0))
        font = pygame.font.Font(None, 28)
        title = font.render("Power", True, self.theme.text)
        self.screen.blit(title, title.get_rect(midtop=(self.screen_w // 2, 120)))

    def _draw_context_menu(self):
        if self.context_menu:
            menu = self.context_menu[2]
            menu.draw(self.screen, self.theme)

    def _draw_toasts(self):
        y = self.screen_h - 60
        for t in self.toasts:
            t.draw(self.screen, self.theme, (self.screen_w - 340, y))
            y -= 76

    def _draw_boot(self):
        # black boot screen with progress
        self.screen.fill((8, 8, 12))
        font = pygame.font.Font(None, 40)
        logo = font.render("🦁 Lion-OS", True, self.theme.accent)
        self.screen.blit(logo, logo.get_rect(midtop=(self.screen_w // 2, self.screen_h // 2 - 100)))
        # progress bar
        bar_r = pygame.Rect(self.screen_w // 2 - 150, self.screen_h // 2 + 10, 300, 8)
        pygame.draw.rect(self.screen, (60, 60, 70), bar_r, border_radius=4)
        pygame.draw.rect(self.screen, self.theme.accent, (bar_r.x, bar_r.y, int(bar_r.width * min(1, self._boot_progress / 100)), bar_r.height), border_radius=4)
        # boot lines
        lfont = pygame.font.Font(None, 16)
        for i, (line, important) in enumerate(BOOT_LINES[:self._boot_lines_done + 1]):
            col = self.theme.accent if important else (150, 150, 165)
            img = lfont.render(line, True, col)
            self.screen.blit(img, (self.screen_w // 2 - 150, self.screen_h // 2 + 30 + i * 22))

    def _draw_login(self):
        dim = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        dim.fill((8, 8, 14, 200))
        self.screen.blit(dim, (0, 0))
        cx = self.screen_w // 2
        # clock
        tfont = pygame.font.Font(None, 60)
        now = time.localtime()
        timestr = time.strftime("%H:%M", now) if self.config.clock_24h else time.strftime("%I:%M %p", now).lstrip("0")
        cimg = tfont.render(timestr, True, (255, 255, 255))
        self.screen.blit(cimg, cimg.get_rect(center=(cx, self.screen_h // 2 - 120)))
        dfont = pygame.font.Font(None, 22)
        dimg = dfont.render(time.strftime("%A, %B %d, %Y", now), True, (220, 220, 230))
        self.screen.blit(dimg, dimg.get_rect(center=(cx, self.screen_h // 2 - 70)))
        # user icon
        pygame.draw.circle(self.screen, self.theme.accent, (cx, self.screen_h // 2 - 10), 34)
        pygame.draw.circle(self.screen, (255, 255, 255), (cx, self.screen_h // 2 - 18), 12)
        ufont = pygame.font.Font(None, 24)
        uimg = ufont.render(self.config.username, True, (255, 255, 255))
        self.screen.blit(uimg, uimg.get_rect(center=(cx, self.screen_h // 2 + 44)))
        # password box
        pw_r = pygame.Rect(cx - 140, self.screen_h // 2 + 70, 280, 40)
        pygame.draw.rect(self.screen, (255, 255, 255, 40), pw_r, border_radius=10)
        pygame.draw.rect(self.screen, self.theme.accent if self._login_attempt % 2 == 0 else (255, 255, 255, 80), pw_r, 1, border_radius=10)
        pfont = pygame.font.Font(None, 22)
        pw_txt = "*" * len(self._login_pw) if self._login_pw else "Password"
        pimg = pfont.render(pw_txt, True, (230, 230, 240) if self._login_pw else (170, 170, 185))
        self.screen.blit(pimg, pimg.get_rect(center=pw_r.center))
        if self._login_error:
            eimg = pfont.render(self._login_error, True, (255, 140, 140))
            self.screen.blit(eimg, eimg.get_rect(center=(cx, pw_r.bottom + 22)))
        hint = pygame.font.Font(None, 15).render("Press Enter to log in", True, (170, 170, 185))
        self.screen.blit(hint, hint.get_rect(center=(cx, pw_r.bottom + 48)))


def boot(config: LionConfig = None):
    """Entry point used by the CLI."""
    os_ = LionOS(config)
    return os_.run()
