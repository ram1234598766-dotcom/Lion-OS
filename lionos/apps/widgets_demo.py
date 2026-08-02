"""Widgets demo — showcases the UI toolkit (buttons, sliders, toggles, lists)."""

from __future__ import annotations

import pygame

from .base import App
from ..widgets import Button, Label, ListBox, ListItem, Slider, Toggle, cached_font, rounded_rect


class WidgetsDemoApp(App):
    name = "UI Toolkit"
    icon = "🧰"
    description = "Explore Lion-OS widgets"
    category = "Developer"
    default_w = 560
    default_h = 480
    resizable = True

    def __init__(self, os, window=None):
        super().__init__(os, window)
        self.toggle = True
        self.slider = 0.5
        self.counter = 0
        self.selected = None
        self.listbox = ListBox(pygame.Rect(0, 0, 220, 220))
        self.listbox.set_items([ListItem("Dark theme", data="dark"),
                                ListItem("Light theme", data="light"),
                                ListItem("Ocean theme", data="ocean"),
                                ListItem("Forest theme", data="forest"),
                                ListItem("Violet theme", data="violet"),
                                ListItem("Rose theme", data="rose")])

    def on_resize(self, rect):
        self.rect = rect

    def handle_event(self, event, local_pos):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # buttons
            for i, b in enumerate(self._buttons()):
                if b.collidepoint(local_pos):
                    if i == 0:
                        self.counter += 1
                    elif i == 1:
                        self.counter -= 1
                    elif i == 2:
                        self.counter = 0
                    return True
            # toggle
            tg = self._toggle_rect()
            if tg.collidepoint(local_pos):
                self.toggle = not self.toggle
                return True
            # listbox
            lb = self._list_rect()
            if lb.collidepoint(local_pos):
                idx = (local_pos[1] - lb.y - 8) // 32
                if 0 <= idx < len(self.listbox.items):
                    self.selected = self.listbox.items[idx]
                    self.os.set_theme(self.selected.data)
                return True
        if event.type == pygame.MOUSEMOTION:
            # slider drag
            sr = self._slider_rect()
            if sr.collidepoint(local_pos) and event.buttons[0]:
                self.slider = max(0.0, min(1.0, (local_pos[0] - sr.x) / sr.width))
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self._slider_rect().collidepoint(local_pos):
            self.slider = max(0.0, min(1.0, (local_pos[0] - self._slider_rect().x) / self._slider_rect().width))
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            return True
        return False

    def _buttons(self):
        y = self.rect.y + 60
        return [pygame.Rect(self.rect.x + 20, y, 90, 34),
                pygame.Rect(self.rect.x + 118, y, 90, 34),
                pygame.Rect(self.rect.x + 216, y, 90, 34)]

    def _toggle_rect(self):
        return pygame.Rect(self.rect.x + 380, self.rect.y + 60, 44, 22)

    def _slider_rect(self):
        return pygame.Rect(self.rect.x + 20, self.rect.y + 130, 220, 20)

    def _list_rect(self):
        return pygame.Rect(self.rect.x + 20, self.rect.y + 190, 230, 230)

    def draw(self, surface, rect):
        self.rect = rect
        font = cached_font(self.os.config.font_size)
        small = cached_font(14)
        t = font.render("UI Toolkit Demo", True, self.theme.text)
        surface.blit(t, (rect.x + 20, rect.y + 16))
        desc = small.render("Try the widgets below — they all update live.", True, self.theme.text_dim)
        surface.blit(desc, (rect.x + 20, rect.y + 40))

        # buttons
        labels = ["+1", "-1", "Reset"]
        for i, b in enumerate(self._buttons()):
            hover = b.collidepoint(pygame.mouse.get_pos())
            rounded_rect(surface, b, 8, self.theme.accent if hover else self.theme.surface_alt)
            img = font.render(labels[i], True, self.theme.text)
            surface.blit(img, img.get_rect(center=b.center))

        # counter + toggle
        cimg = font.render(f"Counter: {self.counter}", True, self.theme.text)
        surface.blit(cimg, (rect.x + 20, rect.y + 104))
        timg = font.render("Enable:", True, self.theme.text)
        surface.blit(timg, (rect.x + 300, rect.y + 64))
        tg = self._toggle_rect()
        rounded_rect(surface, tg, 11, self.theme.accent if self.toggle else self.theme.surface_alt)
        pygame.draw.circle(surface, (255, 255, 255),
                           (tg.right - 10 if self.toggle else tg.left + 10, tg.centery), 8)

        # slider
        simg = font.render(f"Slider: {self.slider:.2f}", True, self.theme.text)
        surface.blit(simg, (rect.x + 20, rect.y + 168))
        sr = self._slider_rect()
        rounded_rect(surface, pygame.Rect(sr.x, sr.centery - 3, sr.width, 6), 3, self.theme.surface_alt)
        fx = sr.x + int(sr.width * self.slider)
        rounded_rect(surface, pygame.Rect(sr.x, sr.centery - 3, fx - sr.x, 6), 3, self.theme.accent)
        pygame.draw.circle(surface, self.theme.accent, (fx, sr.centery), 9)
        pygame.draw.circle(surface, (255, 255, 255), (fx, sr.centery), 4)

        # listbox
        lb = self._list_rect()
        rounded_rect(surface, lb, 10, self.theme.surface_alt)
        for i, item in enumerate(self.listbox.items):
            row = pygame.Rect(lb.x + 4, lb.y + 6 + i * 32, lb.width - 8, 28)
            if self.selected is item:
                rounded_rect(surface, row, 6, self.theme.selection[:3] if len(self.theme.selection) == 3 else self.theme.selection)
            elif row.collidepoint(pygame.mouse.get_pos()):
                rounded_rect(surface, row, 6, self.theme.hover if len(self.theme.hover) == 3 else self.theme.hover[:3])
            iimg = small.render(item.text, True, self.theme.text)
            surface.blit(iimg, (row.x + 10, row.centery - iimg.get_height() // 2))
        hint = small.render("Click a theme to switch instantly", True, self.theme.text_dim)
        surface.blit(hint, (lb.x + 6, lb.bottom + 6))
