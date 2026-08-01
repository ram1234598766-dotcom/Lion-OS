"""Settings app for Lion-OS — themes, appearance, AI, system."""

from __future__ import annotations

import os
import sys

import pygame

from .base import App
from ..theme import THEMES, THEME_NAMES
from ..widgets import Button, Toggle, rounded_rect


class SettingsApp(App):
    name = "Settings"
    icon = "⚙"
    description = "Personalize Lion-OS"
    category = "System"
    default_w = 720
    default_h = 520
    resizable = True

    def __init__(self, os, window=None):
        super().__init__(os, window)
        self.tab = "Appearance"     # Appearance | AI Assistant | System | About
        self.tabs = ["Appearance", "AI Assistant", "System", "About"]
        self.ai_provider = self.os.config.ai_provider
        self.ai_model = self.os.config.ai_model
        self.ai_endpoint = self.os.config.ai_endpoint
        self.ai_key = self.os.config.ai_api_key
        self.theme_preview = self.os.config.theme
        self.scroll = 0

    def on_resize(self, rect):
        self.rect = rect

    def handle_event(self, event, local_pos):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # tabs
            for i, t in enumerate(self.tabs):
                r = pygame.Rect(self.rect.x + 10 + i * 120, self.rect.y + 10, 116, 34)
                if r.collidepoint(local_pos):
                    self.tab = t
                    return True
            # content interactions
            if self.tab == "Appearance":
                for i, name in enumerate(THEME_NAMES):
                    r = pygame.Rect(self.rect.x + 30 + i * 110, self.rect.y + 70, 100, 90)
                    if r.collidepoint(local_pos):
                        self.os.set_theme(name)
                        self.show_toast("Settings", f"Theme: {name}", "success")
                        return True
                if self._toggle_res_collide(local_pos):
                    return True
            if self.tab == "AI Assistant":
                self._handle_ai_click(local_pos)
                return True
            if self.tab == "System":
                self._handle_system_click(local_pos)
                return True
        if event.type == pygame.KEYDOWN and self.tab == "AI Assistant":
            return self._handle_ai_key(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            self.scroll = max(0, min(120, self.scroll + (-20 if event.button == 4 else 20)))
            return True
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(120, self.scroll - event.y * 20))
            return True
        return False

    def _toggle_res_collide(self, pos):
        # fullscreen toggle
        r = pygame.Rect(self.rect.x + 30, self.rect.y + 210, 44, 22)
        if r.collidepoint(pos):
            if self.os.config.resolution == "fullscreen":
                self.os.config_store.set(resolution="windowed")
                self.os.config.resolution = "windowed"
            else:
                self.os.config_store.set(resolution="fullscreen")
                self.os.config.resolution = "fullscreen"
            self.show_toast("Settings", "Restart to apply fullscreen", "info")
            return True
        return False

    def _ai_fields(self):
        prov_y = self.rect.y + 60 + self.scroll
        model_y = prov_y + 60
        ep_y = model_y + 60
        key_y = ep_y + 60
        save_y = key_y + 70
        return prov_y, model_y, ep_y, key_y, save_y

    def _field_rect(self, x, y):
        return pygame.Rect(x, y, 320, 36)

    def _handle_ai_click(self, pos):
        x = self.rect.x + 40
        py, my, ey, ky, sy = self._ai_fields()
        # provider buttons
        providers = [("ollama", "Ollama"), ("openai", "OpenAI"), ("deepseek", "DeepSeek")]
        for i, (key, label) in enumerate(providers):
            r = pygame.Rect(x + i * 130, py - 26, 120, 30)
            if r.collidepoint(pos):
                self.ai_provider = key
                if key == "ollama":
                    self.ai_endpoint = self.ai_endpoint or "http://localhost:11434/v1"
                    self.ai_model = self.ai_model or "llama3"
                elif key == "deepseek":
                    self.ai_endpoint = "https://api.deepseek.com/v1"
                    self.ai_model = self.ai_model or "deepseek-chat"
                elif key == "openai":
                    self.ai_endpoint = "https://api.openai.com/v1"
                    self.ai_model = self.ai_model or "gpt-4o-mini"
                return True
        # toggle
        tg = pygame.Rect(x + 320, py - 26, 44, 22)
        if tg.collidepoint(pos):
            self.os.config_store.set(ai_enabled=not self.os.config.ai_enabled)
            self.os.config.ai_enabled = not self.os.config.ai_enabled
            return True
        # save
        sb = pygame.Rect(x, sy, 140, 36)
        if sb.collidepoint(pos):
            self._save_ai()
            return True
        return False

    def _handle_ai_key(self, event):
        x = self.rect.x + 40
        py, my, ey, ky, sy = self._ai_fields()
        f_map = [(my, "model"), (ey, "endpoint"), (ky, "key")]
        if event.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
            return False  # basic: no cursor-level editing
        if event.unicode and event.unicode.isprintable():
            # find focused field by click position — fallback to model
            return False
        return False

    def _save_ai(self):
        self.os.config_store.set(ai_provider=self.ai_provider,
                                 ai_model=self.ai_model,
                                 ai_endpoint=self.ai_endpoint,
                                 ai_api_key=self.ai_key)
        self.os.config.ai_provider = self.ai_provider
        self.os.config.ai_model = self.ai_model
        self.os.config.ai_endpoint = self.ai_endpoint
        self.os.config.ai_api_key = self.ai_key
        self.show_toast("Settings", "AI settings saved", "success")

    def _handle_system_click(self, pos):
        x = self.rect.x + 40
        y = self.rect.y + 120 + self.scroll
        # user name field
        un = pygame.Rect(x, y, 260, 34)
        if un.collidepoint(pos):
            self.show_toast("Settings", "User name editing disabled here", "info")
            return True
        # 24h toggle
        tg = pygame.Rect(x + 340, y, 44, 22)
        if tg.collidepoint(pos):
            self.os.config_store.set(clock_24h=not self.os.config.clock_24h)
            self.os.config.clock_24h = not self.os.config.clock_24h
            return True
        # reset button
        rb = pygame.Rect(x, y + 160, 180, 36)
        if rb.collidepoint(pos):
            cfg = self.os.config_store
            for k in list(cfg.cfg.__dict__.keys()):
                setattr(cfg.cfg, k, None if False else getattr(cfg.cfg, k))
            # simpler: reset file
            try:
                import json
                p = os.path.join(os.path.expanduser("~"), ".lionos", "config.json")
                if os.path.exists(p):
                    os.remove(p)
                self.show_toast("Settings", "Config reset — restart Lion-OS", "success")
            except OSError as e:
                self.show_toast("Settings", f"Reset failed: {e}", "error")
            return True
        return False

    def draw(self, surface, rect):
        self.rect = rect
        font = pygame.font.Font(None, self.os.config.font_size)
        small = pygame.font.Font(None, 15)

        # tabs
        for i, t in enumerate(self.tabs):
            r = pygame.Rect(rect.x + 10 + i * 120, rect.y + 10, 116, 34)
            if t == self.tab:
                rounded_rect(surface, r, 8, self.theme.accent)
                col = (255, 255, 255)
            else:
                rounded_rect(surface, r, 8, self.theme.surface_alt)
                col = self.theme.text
            img = font.render(t, True, col)
            surface.blit(img, img.get_rect(center=r.center))

        x = rect.x + 40
        y = rect.y + 70

        if self.tab == "Appearance":
            header = font.render("Theme", True, self.theme.text)
            surface.blit(header, (x, y - 14))
            for i, name in enumerate(THEME_NAMES):
                r = pygame.Rect(x + i * 110, y, 100, 90)
                if r.collidepoint(pygame.mouse.get_pos()):
                    rounded_rect(surface, r, 10, self.theme.hover if len(self.theme.hover) == 3 else self.theme.hover[:3])
                else:
                    rounded_rect(surface, r, 10, self.theme.surface_alt)
                th = THEMES[name]
                # color dots
                for j, c in enumerate([th.accent, th.surface_alt, th.text, th.bg]):
                    pygame.draw.circle(surface, c, (r.x + 18 + j * 20, r.y + 22), 7)
                name_img = small.render(name.capitalize(), True, self.theme.text)
                surface.blit(name_img, name_img.get_rect(midtop=(r.centerx, r.y + 40)))
                if name == self.theme.name.lower():
                    pygame.draw.rect(surface, self.theme.accent, r, 2, border_radius=10)
                    check = small.render("✓", True, self.theme.accent)
                    surface.blit(check, (r.right - 18, r.y + 4))
            # resolution
            ry = rect.y + 190
            rimg = font.render("Fullscreen", True, self.theme.text)
            surface.blit(rimg, (x, ry))
            tg = pygame.Rect(x + 320, ry - 4, 44, 22)
            rounded_rect(surface, tg, 11, self.theme.accent if self.os.config.resolution == "fullscreen" else self.theme.surface_alt)
            pygame.draw.circle(surface, (255, 255, 255),
                               (tg.right - 10 if self.os.config.resolution == "fullscreen" else tg.left + 10, tg.centery), 8)
            note = small.render("Fullscreen applies after restart", True, self.theme.text_dim)
            surface.blit(note, (x, ry + 30))

        elif self.tab == "AI Assistant":
            py, my, ey, ky, sy = self._ai_fields()
            label = font.render("AI Provider", True, self.theme.text)
            surface.blit(label, (x, py - 46))
            providers = [("ollama", "Ollama (local)"), ("openai", "OpenAI"), ("deepseek", "DeepSeek")]
            for i, (key, label2) in enumerate(providers):
                r = pygame.Rect(x + i * 130, py - 26, 120, 30)
                if key == self.ai_provider:
                    rounded_rect(surface, r, 8, self.theme.accent)
                    col = (255, 255, 255)
                else:
                    rounded_rect(surface, r, 8, self.theme.surface_alt)
                    col = self.theme.text
                img = font.render(label2.split(" (")[0], True, col)
                surface.blit(img, img.get_rect(center=r.center))
            en = font.render("Enable AI", True, self.theme.text)
            surface.blit(en, (x, py - 46 + 34))
            tg = pygame.Rect(x + 320, py - 26, 44, 22)
            rounded_rect(surface, tg, 11, self.theme.accent if self.os.config.ai_enabled else self.theme.surface_alt)
            pygame.draw.circle(surface, (255, 255, 255),
                               (tg.right - 10 if self.os.config.ai_enabled else tg.left + 10, tg.centery), 8)
            # fields
            fields = [("Model", my, self.ai_model, "e.g. llama3 / deepseek-chat"),
                      ("Endpoint", ey, self.ai_endpoint, "https://..."),
                      ("API Key", ky, self.ai_key, "sk-... (stored locally)")]
            for name2, fy, val, ph in fields:
                fimg = small.render(name2, True, self.theme.text_dim)
                surface.blit(fimg, (x, fy - 22))
                fr = self._field_rect(x, fy)
                rounded_rect(surface, fr, 8, self.theme.surface_alt)
                if not val:
                    pimg = small.render(ph, True, self.theme.text_dim)
                    surface.blit(pimg, (fr.x + 10, fr.centery - pimg.get_height() // 2))
                else:
                    shown = val if name2 != "API Key" else ("*" * min(len(val), 20))
                    vimg = small.render(shown, True, self.theme.text)
                    surface.blit(vimg, (fr.x + 10, fr.centery - vimg.get_height() // 2))
            sb = pygame.Rect(x, sy, 140, 36)
            rounded_rect(surface, sb, 8, self.theme.accent)
            s = font.render("Save Settings", True, (255, 255, 255))
            surface.blit(s, s.get_rect(center=sb.center))
            note = small.render("The AI assistant connects to this provider at runtime.", True, self.theme.text_dim)
            surface.blit(note, (x, sy + 44))

        elif self.tab == "System":
            sys_info = self.os.config.system_info
            rows = [
                ("User", self.os.config.username),
                ("Hostname", sys_info.get("hostname", "")),
                ("Platform", f"{sys_info.get('os', '')} {sys_info.get('release', '')}"),
                ("Machine", sys_info.get("machine", "")),
                ("Python", sys_info.get("python", "")),
            ]
            yy = y
            for name2, val in rows:
                n = small.render(name2, True, self.theme.text_dim)
                surface.blit(n, (x, yy))
                v = small.render(val, True, self.theme.text)
                surface.blit(v, (x + 120, yy))
                yy += 26
            # 24h toggle
            yy += 10
            t24 = font.render("24-hour clock", True, self.theme.text)
            surface.blit(t24, (x, yy))
            tg = pygame.Rect(x + 340, yy - 4, 44, 22)
            rounded_rect(surface, tg, 11, self.theme.accent if self.os.config.clock_24h else self.theme.surface_alt)
            pygame.draw.circle(surface, (255, 255, 255),
                               (tg.right - 10 if self.os.config.clock_24h else tg.left + 10, tg.centery), 8)
            rb = pygame.Rect(x, yy + 160, 180, 36)
            rounded_rect(surface, rb, 8, self.theme.danger if len(self.theme.danger) == 3 else self.theme.danger)
            rimg = font.render("Reset Configuration", True, (255, 255, 255))
            surface.blit(rimg, rimg.get_rect(center=rb.center))

        elif self.tab == "About":
            from .. import APP_NAME, VERSION, __codename__
            lines = [
                f"{APP_NAME} {VERSION}",
                f"Codename: {__codename__}",
                "",
                "A desktop operating system built in Python",
                "with a full window manager and built-in apps.",
                "",
                "Technologies: Python, Pygame, psutil",
            ]
            for i, ln in enumerate(lines):
                col = self.theme.accent if i == 0 else self.theme.text_dim
                img = font.render(ln, True, col)
                surface.blit(img, (x, y + i * 30))
            # version badge
            vg = pygame.Rect(x, y + len(lines) * 30 + 10, 200, 40)
            rounded_rect(surface, vg, 10, self.theme.accent + (40,))
            vi = font.render(f"v{VERSION}", True, self.theme.accent)
            surface.blit(vi, vi.get_rect(center=vg.center))
