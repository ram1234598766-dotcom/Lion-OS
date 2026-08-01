"""Notes app for Lion-OS — persistent sticky notes."""

from __future__ import annotations

import json
import os
import time

import pygame

from .base import App
from ..widgets import Button, ListBox, ListItem, rounded_rect, wrap_text


class NotesApp(App):
    name = "Notes"
    icon = "🗒"
    description = "Keep quick notes and ideas"
    category = "Productivity"
    default_w = 720
    default_h = 480
    resizable = True

    def __init__(self, os, window=None):
        super().__init__(os, window)
        self.notes = {}            # title -> content
        self.order = []            # list of titles
        self.selected = None
        self.edit_title = ""
        self.edit_content = ""
        self.scroll = 0
        self._blink = 0.0
        self._load()
        if self.order:
            self.selected = self.order[0]
            self._load_editor()

    def _path(self):
        d = os.path.join(os.path.expanduser("~"), ".lionos", "notes.json")
        return d

    def _load(self):
        try:
            with open(self._path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            self.notes = data.get("notes", {})
            self.order = data.get("order", list(self.notes.keys()))
            if not self.order:
                self.order = list(self.notes.keys())
        except (OSError, json.JSONDecodeError):
            self.notes = {}
            self.order = []

    def _save(self):
        os.makedirs(os.path.dirname(self._path()), exist_ok=True)
        with open(self._path(), "w", encoding="utf-8") as f:
            json.dump({"notes": self.notes, "order": self.order}, f, indent=2)

    def _load_editor(self):
        if self.selected and self.selected in self.notes:
            self.edit_title = self.selected
            self.edit_content = self.notes[self.selected]
        else:
            self.edit_title = ""
            self.edit_content = ""

    def handle_event(self, event, local_pos):
        if event.type == pygame.KEYDOWN:
            if self.selected and (event.key == pygame.K_s and event.mod & pygame.KMOD_CTRL):
                self._save_current()
                self.show_toast("Notes", "Saved", "success")
                return True
            if event.key == pygame.K_BACKSPACE and self._in_content(local_pos):
                if self.edit_content:
                    self.edit_content = self.edit_content[:-1]
                    self.redraw()
                    return True
            if event.unicode and event.unicode.isprintable() and self._in_content(local_pos):
                self.edit_content += event.unicode
                self.redraw()
                return True
            if event.unicode and event.unicode == " " and self._in_content(local_pos):
                self.edit_content += " "
                self.redraw()
                return True
            if event.key == pygame.K_RETURN and self._in_content(local_pos):
                self.edit_content += "\n"
                self.redraw()
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # sidebar list handled via ListBox-like manual
            side = self._sidebar_rect()
            if side.collidepoint(local_pos):
                idx = (local_pos[1] - side.y - 8) // 34
                if 0 <= idx < len(self.order):
                    self._save_current()
                    self.selected = self.order[idx]
                    self._load_editor()
                return True
            # new / delete buttons
            if self._new_btn().collidepoint(local_pos):
                self._new_note()
                return True
            if self._delete_btn().collidepoint(local_pos):
                self._delete_note()
                return True
            if self._save_btn().collidepoint(local_pos):
                self._save_current()
                self.show_toast("Notes", "Saved", "success")
                return True
            if self._content_rect().collidepoint(local_pos):
                self.redraw()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            self.scroll = max(0, min(self._max_scroll(), self.scroll + (-30 if event.button == 4 else 30)))
            return True
        if event.type == pygame.MOUSEWHEEL and self._content_rect().collidepoint(local_pos):
            self.scroll = max(0, min(self._max_scroll(), self.scroll - event.y * 30))
            return True
        return False

    def _sidebar_rect(self):
        return pygame.Rect(self.rect.x + 8, self.rect.y + 46, 180, self.rect.height - 60)

    def _content_rect(self):
        return pygame.Rect(self.rect.x + 200, self.rect.y + 46, self.rect.width - 214, self.rect.height - 60)

    def _new_btn(self):
        return pygame.Rect(self.rect.x + 8, self.rect.y + 8, 84, 30)

    def _delete_btn(self):
        return pygame.Rect(self.rect.x + 100, self.rect.y + 8, 84, 30)

    def _save_btn(self):
        return pygame.Rect(self.rect.x + self.rect.width - 96, self.rect.y + 8, 88, 30)

    def _in_content(self, pos):
        return self._content_rect().collidepoint(pos)

    def _new_note(self):
        self._save_current()
        n = 1
        title = f"Note {n}"
        while title in self.notes:
            n += 1
            title = f"Note {n}"
        self.notes[title] = ""
        self.order.insert(0, title)
        self.selected = title
        self._load_editor()
        self._save()
        self.redraw()

    def _delete_note(self):
        if self.selected and self.selected in self.notes:
            del self.notes[self.selected]
            if self.selected in self.order:
                self.order.remove(self.selected)
            self.selected = self.order[0] if self.order else None
            self._load_editor()
            self._save()
            self.redraw()

    def _save_current(self):
        if self.selected and self.selected in self.notes:
            self.notes[self.selected] = self.edit_content
            self._save()

    def _max_scroll(self):
        font = pygame.font.Font(None, self.os.config.font_size)
        lh = font.get_height() + 6
        return max(0, len(self.edit_content.split("\n")) * lh - self._content_rect().height + 30)

    def update(self, dt):
        self._blink += dt

    def draw(self, surface, rect):
        self.rect = rect
        font = pygame.font.Font(None, self.os.config.font_size)
        small = pygame.font.Font(None, 15)
        # buttons
        for label, b, primary in (("＋ New", self._new_btn(), True),
                                  ("Delete", self._delete_btn(), False),
                                  ("Save", self._save_btn(), True)):
            hover = b.collidepoint(pygame.mouse.get_pos())
            rounded_rect(surface, b, 8, self.theme.accent if primary and hover else
                         (self.theme.accent if primary else self.theme.surface_alt))
            img = font.render(label, True, self.theme.text)
            surface.blit(img, img.get_rect(center=b.center))
        # sidebar
        side = self._sidebar_rect()
        rounded_rect(surface, side, 10, self.theme.surface_alt)
        for i, title in enumerate(self.order[:50]):
            row = pygame.Rect(side.x + 4, side.y + 4 + i * 34, side.width - 8, 30)
            if title == self.selected:
                rounded_rect(surface, row, 6, self.theme.selection[:3] if len(self.theme.selection) == 3 else self.theme.selection)
            elif row.collidepoint(pygame.mouse.get_pos()):
                rounded_rect(surface, row, 6, self.theme.hover[:3] if len(self.theme.hover) == 3 else self.theme.hover)
            timg = small.render(title, True, self.theme.text)
            surface.blit(timg, (row.x + 8, row.centery - timg.get_height() // 2))
        # editor
        cr = self._content_rect()
        rounded_rect(surface, cr, 10, self.theme.surface)
        pygame.draw.rect(surface, self.theme.glass_border[:3] if len(self.theme.glass_border) == 4 else self.theme.glass_border, cr, 1, border_radius=10)
        # title display
        tfont = pygame.font.Font(None, self.os.config.font_size + 4)
        ttitle = self.selected or "No note selected"
        timg = tfont.render(ttitle, True, self.theme.accent)
        surface.blit(timg, (cr.x + 12, cr.y + 10))
        # content
        clip = pygame.Rect(cr.x + 4, cr.y + 44, cr.width - 16, cr.height - 52)
        old = surface.get_clip()
        surface.set_clip(clip)
        font2 = pygame.font.Font(None, self.os.config.font_size)
        lh = font2.get_height() + 6
        lines = self.edit_content.split("\n")
        for i, ln in enumerate(lines):
            ty = clip.y - self.scroll + i * lh
            if ty + lh < clip.y or ty > clip.bottom:
                continue
            limg = font2.render(ln, True, self.theme.text)
            surface.blit(limg, (clip.x, ty))
        surface.set_clip(old)
        max_s = self._max_scroll()
        if max_s > 0:
            sh = max(30, int(clip.height * clip.height / max(1, len(lines) * lh)))
            ratio = self.scroll / max_s
            sy = clip.y + ratio * (clip.height - sh)
            pygame.draw.rect(surface, self.theme.scrollbar, pygame.Rect(cr.right - 8, sy, 6, sh), border_radius=3)
