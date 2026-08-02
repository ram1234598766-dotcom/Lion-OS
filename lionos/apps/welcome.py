"""Welcome / getting-started app for Lion-OS."""

from __future__ import annotations

import pygame

from .base import App
from ..widgets import cached_font, rounded_rect

FEATURES = [
    ("🪟", "Window Manager", "Drag, resize, snap and stack windows"),
    ("📁", "File Manager", "Browse files, copy, cut, paste, delete"),
    ("💬", "AI Assistant", "Built-in assistant with local + cloud models"),
    ("▣", "Terminal", "Full shell with history and scripts"),
    ("✎", "Text Editor", "Edit code with syntax highlighting"),
    ("🎨", "Paint", "Canvas with brushes, shapes and fill"),
    ("🎵", "Media Player", "Play audio files with a playlist"),
    ("🌐", "Browser", "Search the web and read pages"),
    ("🗒", "Notes", "Persistent sticky notes"),
    ("📊", "System Monitor", "Live CPU, RAM, disk and network"),
]

GETTING_STARTED = [
    "1. Click the 🦁 Start button (bottom-left) to open the launcher.",
    "2. Search for any app by typing its name.",
    "3. Drag windows by their title bar; drag to screen edges to snap.",
    "4. Double-click files in File Manager to open them.",
    "5. Press Ctrl+S in the Text Editor to save.",
    "6. Open AI Assistant and pick a provider in Settings.",
]


class WelcomeApp(App):
    name = "Welcome"
    icon = "👋"
    description = "Welcome to Lion-OS"
    category = "System"
    default_w = 720
    default_h = 540
    resizable = True
    singleton = True

    def __init__(self, os, window=None):
        super().__init__(os, window)
        self.scroll = 0
        self.set_title("Welcome to Lion-OS")

    def on_resize(self, rect):
        self.rect = rect

    def handle_event(self, event, local_pos):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._launch_btn().collidepoint(local_pos):
                self.os.launcher_open = True
                return True
            if self._dismiss_btn().collidepoint(local_pos):
                self.close()
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            self.scroll = max(0, min(self._max_scroll(), self.scroll + (-40 if event.button == 4 else 40)))
            return True
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(self._max_scroll(), self.scroll - event.y * 40))
            return True
        return False

    def _content(self):
        return pygame.Rect(self.rect.x + 20, self.rect.y + 20, self.rect.width - 40, self.rect.height - 90)

    def _launch_btn(self):
        r = self._content()
        return pygame.Rect(r.x + 20, r.bottom - 46, 180, 36)

    def _dismiss_btn(self):
        r = self._content()
        return pygame.Rect(r.x + 210, r.bottom - 46, 120, 36)

    def _max_scroll(self):
        # approximate content height
        content_h = 120 + len(FEATURES) // 2 * 120 + 100
        return max(0, content_h - self._content().height)

    def draw(self, surface, rect):
        self.rect = rect
        font = cached_font(self.os.config.font_size + 6)
        small = cached_font(15)
        r = self._content()
        clip = pygame.Rect(r)
        old = surface.get_clip()
        surface.set_clip(clip)

        y = r.y + 10 - self.scroll
        # hero
        hero = pygame.Rect(r.x, y, r.width, 90)
        pygame.draw.rect(surface, self.theme.accent + (40,), hero, border_radius=14)
        t = font.render(f"Welcome to Lion-OS, {self.os.config.username}!", True, self.theme.accent)
        surface.blit(t, (hero.x + 20, hero.y + 16))
        s = small.render("A complete graphical desktop that runs inside Python.", True, self.theme.text)
        surface.blit(s, (hero.x + 20, hero.y + 52))
        y += 110

        for i, (icon, name, desc) in enumerate(FEATURES):
            col = i % 2
            row = i // 2
            card = pygame.Rect(r.x + col * (r.width // 2 + 6), y + row * 118, r.width // 2 - 6, 110)
            if card.collidepoint(pygame.mouse.get_pos()):
                pygame.draw.rect(surface, self.theme.hover, card, border_radius=12)
            else:
                pygame.draw.rect(surface, self.theme.surface_alt, card, border_radius=12)
            ic = pygame.Rect(card.x + 14, card.y + 12, 40, 40)
            pygame.draw.rect(surface, self.theme.accent + (40,), ic, border_radius=10)
            ig = small.render(icon, True, self.theme.accent)
            surface.blit(ig, ig.get_rect(center=ic.center))
            n = font.render(name, True, self.theme.text)
            surface.blit(n, (card.x + 64, card.y + 14))
            d = small.render(desc, True, self.theme.text_dim)
            surface.blit(d, (card.x + 64, card.y + 44))

        y += (len(FEATURES) // 2 + 1) * 118
        g = font.render("Getting started", True, self.theme.accent)
        surface.blit(g, (r.x + 4, y))
        y += 30
        for ln in GETTING_STARTED:
            gi = small.render(ln, True, self.theme.text)
            surface.blit(gi, (r.x + 4, y))
            y += 22

        surface.set_clip(old)
        # buttons
        for b, label, primary in ((self._launch_btn(), "Open Launcher", True),
                                  (self._dismiss_btn(), "Get Started", False)):
            hover = b.collidepoint(pygame.mouse.get_pos())
            rounded_rect(surface, b, 8, self.theme.accent if primary else self.theme.surface_alt)
            bi = font.render(label, True, self.theme.text if not primary else (255, 255, 255))
            surface.blit(bi, bi.get_rect(center=b.center))
