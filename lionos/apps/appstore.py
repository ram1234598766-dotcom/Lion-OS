"""App Store for Lion-OS — install system Python packages via pip."""

from __future__ import annotations

import subprocess
import sys

import pygame

from .base import App
from ..widgets import Button, ProgressBar, cached_font, rounded_rect

CATALOG = [
    # (name, pkg, description, icon)
    ("Code Blocks", "pygame-ce", "Graphics toolkit (already bundled)", "🧩"),
    ("Files", "pyautogui", "GUI automation for scripts", "🖱"),
    ("Math", "numpy", "Fast numeric computation", "🧮"),
    ("Data", "pandas", "Data analysis library", "📊"),
    ("Plots", "matplotlib", "Plotting and charts", "📈"),
    ("Web", "requests", "HTTP client (already bundled)", "🌐"),
    ("Images", "pillow", "Image processing library", "🖼"),
    ("Sounds", "numpy", "Audio arrays", "🔊"),
]


class AppStoreApp(App):
    name = "App Store"
    icon = "🛍"
    description = "Install packages for your OS"
    category = "System"
    default_w = 620
    default_h = 520
    resizable = True

    def __init__(self, os, window=None):
        super().__init__(os, window)
        self.scroll = 0
        self.installing = None
        self.install_log = ""
        self.installed = self._detect_installed()

    def _detect_installed(self):
        installed = []
        for name, pkg, desc, icon in CATALOG:
            try:
                __import__(pkg.replace("-", "_").split(">=")[0])
                installed.append(pkg)
            except Exception:
                pass
        return installed

    def on_resize(self, rect):
        self.rect = rect

    def handle_event(self, event, local_pos):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, (name, pkg, desc, icon) in enumerate(CATALOG):
                card = self._card(i)
                if card.collidepoint(local_pos):
                    btn = pygame.Rect(card.right - 100, card.centery - 16, 84, 32)
                    if btn.collidepoint(local_pos):
                        self._install(pkg)
                        return True
                    return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            self.scroll = max(0, min(self._max_scroll(), self.scroll + (-60 if event.button == 4 else 60)))
            return True
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(self._max_scroll(), self.scroll - event.y * 60))
            return True
        return False

    def _card(self, i):
        return pygame.Rect(self.rect.x + 16, self.rect.y + 60 + i * 76 - self.scroll,
                           self.rect.width - 32, 68)

    def _max_scroll(self):
        return max(0, len(CATALOG) * 76 - (self.rect.height - 80))

    def _install(self, pkg):
        if self.installing:
            self.show_toast("App Store", "An install is already running", "warn")
            return
        self.installing = pkg
        self.install_log = f"Installing {pkg}..."
        import threading
        def worker():
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "--user", pkg],
                               capture_output=True, text=True, timeout=180)
                self.installed = self._detect_installed()
                self.install_log = f"✓ {pkg} installed"
            except Exception as e:
                self.install_log = f"Install failed: {e}"
            finally:
                self.installing = None
        threading.Thread(target=worker, daemon=True).start()

    def draw(self, surface, rect):
        self.rect = rect
        font = cached_font(self.os.config.font_size)
        small = cached_font(14)
        t = font.render("App Store", True, self.theme.text)
        surface.blit(t, (rect.x + 16, rect.y + 14))
        note = small.render("Installs Python packages system-wide via pip", True, self.theme.text_dim)
        surface.blit(note, (rect.x + 16, rect.y + 38))
        clip = pygame.Rect(rect.x + 8, rect.y + 56, rect.width - 16, rect.height - 66)
        old = surface.get_clip()
        surface.set_clip(clip)
        for i, (name, pkg, desc, icon) in enumerate(CATALOG):
            card = self._card(i)
            if card.bottom < clip.y or card.y > clip.bottom:
                continue
            rounded_rect(surface, card, 10, self.theme.surface_alt)
            ic = pygame.Rect(card.x + 10, card.y + 10, 46, 46)
            rounded_rect(surface, ic, 10, self.theme.accent + (50,))
            ig = font.render(icon, True, self.theme.accent)
            surface.blit(ig, ig.get_rect(center=ic.center))
            n = font.render(name, True, self.theme.text)
            surface.blit(n, (ic.right + 12, card.y + 10))
            d = small.render(desc, True, self.theme.text_dim)
            surface.blit(d, (ic.right + 12, card.y + 36))
            is_installed = pkg in self.installed
            installing = self.installing == pkg
            btn = pygame.Rect(card.right - 100, card.centery - 16, 84, 32)
            if is_installed:
                rounded_rect(surface, btn, 8, self.theme.surface)
                bimg = small.render("✓ Installed", True, self.theme.success)
            elif installing:
                rounded_rect(surface, btn, 8, self.theme.accent)
                bimg = small.render("Installing...", True, (255, 255, 255))
            else:
                rounded_rect(surface, btn, 8, self.theme.accent)
                bimg = small.render("Install", True, (255, 255, 255))
            surface.blit(bimg, bimg.get_rect(center=btn.center))
        surface.set_clip(old)
        if self.install_log:
            log = small.render(self.install_log, True, self.theme.accent)
            surface.blit(log, (rect.x + 16, rect.bottom - 24))
        max_s = self._max_scroll()
        if max_s > 0:
            sh = max(30, int(rect.height * rect.height / max(1, len(CATALOG) * 76)))
            ratio = self.scroll / max_s
            sy = rect.y + ratio * (rect.height - sh)
            pygame.draw.rect(surface, self.theme.scrollbar, pygame.Rect(rect.right - 8, sy, 6, sh), border_radius=3)
