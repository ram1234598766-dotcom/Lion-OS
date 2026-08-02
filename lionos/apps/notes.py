"""Notes app for Lion-OS — persistent sticky notes."""

from __future__ import annotations

import os

import pygame

from .base import App
from ..widgets import Button, ListBox, ListItem, cached_font, rounded_rect, wrap_text


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
        self._files = {}           # title -> absolute path of its .txt file
        self.selected = None
        self.edit_title = ""
        self.edit_content = ""
        self.scroll = 0
        self._blink = 0.0
        self._dirty_since_save = False
        self._dirty_accum = 0.0
        self._load()
        if self.order:
            self.selected = self.order[0]
            self._load_editor()

    def _notes_dir(self):
        return os.path.join(os.path.expanduser("~"), ".lionos", "notes")

    def _slugify(self, text):
        parts = []
        last_alnum = False
        for c in text.lower():
            if c.isalnum():
                parts.append(c)
                last_alnum = True
            elif last_alnum:
                parts.append("-")
                last_alnum = False
        return "".join(parts).strip("-") or "untitled"

    def _title_for(self, content):
        for ln in content.split("\n"):
            t = ln.strip()
            if t:
                return t[:40]
        return ""

    def _file_for(self, title):
        return os.path.join(self._notes_dir(), self._slugify(title) + ".txt")

    def _current_title(self):
        t = self._title_for(self.edit_content)
        return t or (self.selected or "")

    def _load(self):
        self.notes = {}
        self.order = []
        self._files = {}
        d = self._notes_dir()
        try:
            if not os.path.isdir(d):
                return
            entries = []
            for fn in os.listdir(d):
                if not fn.endswith(".txt"):
                    continue
                p = os.path.join(d, fn)
                try:
                    mtime = os.path.getmtime(p)
                except OSError:
                    continue
                entries.append((mtime, fn, p))
            entries.sort(reverse=True)  # most recently edited first
            for _, fn, p in entries:
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        content = f.read()
                except OSError:
                    continue
                title = self._title_for(content) or fn[:-4]
                base, n = title, 2
                while title in self.notes:
                    title = f"{base} ({n})"
                    n += 1
                self.notes[title] = content
                self._files[title] = p
                self.order.append(title)
        except OSError:
            pass

    def _sync_title(self):
        """Re-derive the note title from the first non-empty line of content."""
        if not self.selected:
            return
        new_title = self._title_for(self.edit_content) or self.selected
        if new_title == self.selected:
            return
        base, n = new_title, 2
        while new_title in self.notes and new_title != self.selected:
            new_title = f"{base} ({n})"
            n += 1
        old_file = self._files.pop(self.selected, None)
        self.notes[new_title] = self.notes.pop(self.selected)
        self._files[new_title] = old_file
        if self.selected in self.order:
            self.order[self.order.index(self.selected)] = new_title
        self.selected = new_title
        self.edit_title = new_title

    def _mark_dirty(self):
        self._dirty_since_save = True
        self._dirty_accum = 0.0
        self.redraw()

    def _load_editor(self):
        if self.selected and self.selected in self.notes:
            self.edit_title = self.selected
            self.edit_content = self.notes[self.selected]
        else:
            self.edit_title = ""
            self.edit_content = ""
        self._dirty_since_save = False
        self._dirty_accum = 0.0

    def handle_event(self, event, local_pos):
        if event.type == pygame.KEYDOWN:
            if self.selected and (event.key == pygame.K_s and event.mod & pygame.KMOD_CTRL):
                self._save_current()
                self.show_toast("Notes", "Saved", "success")
                return True
            if event.key == pygame.K_BACKSPACE and self._in_content(local_pos):
                if self.edit_content:
                    self.edit_content = self.edit_content[:-1]
                    self._sync_title()
                    self._mark_dirty()
                    return True
            if event.unicode and event.unicode.isprintable() and self._in_content(local_pos):
                self.edit_content += event.unicode
                self._sync_title()
                self._mark_dirty()
                return True
            if event.unicode and event.unicode == " " and self._in_content(local_pos):
                self.edit_content += " "
                self._sync_title()
                self._mark_dirty()
                return True
            if event.key == pygame.K_RETURN and self._in_content(local_pos):
                self.edit_content += "\n"
                self._sync_title()
                self._mark_dirty()
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
        self._files[title] = None
        self._load_editor()
        self.redraw()

    def _delete_note(self):
        if self.selected and self.selected in self.notes:
            f = self._files.pop(self.selected, None)
            if f:
                try:
                    os.remove(f)
                except OSError:
                    pass
            del self.notes[self.selected]
            if self.selected in self.order:
                self.order.remove(self.selected)
            self.selected = self.order[0] if self.order else None
            self._load_editor()
            self.redraw()

    def _save_current(self):
        if self.selected is None:
            return
        self._sync_title()
        self.notes[self.selected] = self.edit_content
        old_file = self._files.get(self.selected)
        if not self.edit_content.strip() and old_file is None:
            self._dirty_since_save = False
            return
        d = self._notes_dir()
        os.makedirs(d, exist_ok=True)
        new_file = self._file_for(self.selected)
        if old_file and os.path.abspath(old_file) != os.path.abspath(new_file):
            try:
                os.remove(old_file)
            except OSError:
                pass
        with open(new_file, "w", encoding="utf-8") as f:
            f.write(self.edit_content)
        self._files[self.selected] = new_file
        self._dirty_since_save = False

    def _max_scroll(self):
        font = cached_font(self.os.config.font_size)
        lh = font.get_height() + 6
        return max(0, len(self.edit_content.split("\n")) * lh - self._content_rect().height + 30)

    def on_close(self):
        self._save_current()

    def update(self, dt):
        self._blink += dt
        if self._dirty_since_save:
            self._dirty_accum += dt
            if self._dirty_accum >= 1.0:
                self._dirty_accum = 0.0
                self._save_current()

    def draw(self, surface, rect):
        self.rect = rect
        font = cached_font(self.os.config.font_size)
        small = cached_font(15)
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
        ttitle = self._current_title()
        self.set_title(ttitle or self.name)
        display = ttitle or "No note selected"
        tfont = cached_font(self.os.config.font_size + 4)
        timg = tfont.render(display, True, self.theme.accent)
        surface.blit(timg, (cr.x + 12, cr.y + 10))
        # content
        clip = pygame.Rect(cr.x + 4, cr.y + 44, cr.width - 16, cr.height - 52)
        old = surface.get_clip()
        surface.set_clip(clip)
        font2 = cached_font(self.os.config.font_size)
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
