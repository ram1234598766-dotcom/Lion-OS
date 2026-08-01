"""File Manager app for Lion-OS."""

from __future__ import annotations

import os
import os as os_module
import shutil
import subprocess
import sys
from datetime import datetime

import pygame

from .base import App
from ..widgets import Button, rounded_rect, wrap_text

HIDDEN_PREFIXES = (".", "$")


def human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def file_icon(name):
    ext = os.path.splitext(name)[1].lower()
    mapping = {
        ".py": "🐍", ".txt": "📄", ".md": "📝", ".json": "📊", ".png": "🖼",
        ".jpg": "🖼", ".jpeg": "🖼", ".gif": "🖼", ".mp3": "🎵", ".wav": "🎵",
        ".zip": "📦", ".exe": "⚙", ".pdf": "📕", ".html": "🌐", ".css": "🎨",
        ".js": "🟨", ".csv": "📋", ".doc": "📘", ".mp4": "🎬",
    }
    if os.path.isdir(name):
        return "📁"
    return mapping.get(ext, "📄")


class FileManagerApp(App):
    name = "File Manager"
    icon = "📁"
    description = "Browse and manage your files"
    category = "System"
    default_w = 820
    default_h = 540
    resizable = True

    def __init__(self, os, window=None, path=None):
        super().__init__(os, window)
        self.cwd = path or os_module.path.expanduser("~")
        self.entries = []
        self.history = []
        self.fwd = []
        self.history_back = self.history
        self.history_forward = self.fwd
        self.selected = None
        self.show_hidden = False
        self.search = ""
        self.scroll = 0
        self.cols = 4
        self.icon_size = 76
        self._clipboard = None      # (src_path, cut)
        self._load_dir()

    def on_resize(self, rect):
        self.rect = rect
        self.cols = max(2, (rect.width - 20) // self.icon_size)

    def _load_dir(self):
        try:
            items = os.listdir(self.cwd)
        except OSError as e:
            self.show_toast("File Manager", f"Cannot open: {e}", "error")
            items = []
        entries = []
        for name in items:
            if not self.show_hidden and name.startswith(HIDDEN_PREFIXES):
                continue
            full = os.path.join(self.cwd, name)
            try:
                is_dir = os.path.isdir(full)
                size = 0 if is_dir else os.path.getsize(full)
                mtime = os.path.getmtime(full)
            except OSError:
                is_dir = os.path.isdir(full) or not os.path.exists(full)
                size = 0
                mtime = 0
            entries.append({
                "name": name, "path": full, "dir": is_dir,
                "size": size, "mtime": mtime,
            })
        entries.sort(key=lambda e: (not e["dir"], e["name"].lower()))
        self.entries = entries
        self.selected = None
        self.scroll = 0
        self.set_title(f"File Manager — {os.path.basename(self.cwd) or self.cwd}")

    def handle_event(self, event, local_pos):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE and self.search:
                self.search = self.search[:-1]
                return True
            if event.unicode and (event.unicode.isprintable() or event.unicode == " "):
                self.search += event.unicode
                return True
            if event.key == pygame.K_ESCAPE:
                self.search = ""
                return True
            if event.key == pygame.K_RETURN:
                if self.search:
                    self.search = ""
                    return True
            if event.key == pygame.K_F5:
                self._load_dir()
                return True
            if event.key == pygame.K_UP:
                self._go_up()
                return True
            if event.key == pygame.K_DELETE:
                self._delete_selected()
                return True
            if event.key == pygame.K_c and event.mod & pygame.KMOD_CTRL:
                self._copy_selected()
                return True
            if event.key == pygame.K_x and event.mod & pygame.KMOD_CTRL:
                self._cut_selected()
                return True
            if event.key == pygame.K_v and event.mod & pygame.KMOD_CTRL:
                self._paste()
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # toolbar buttons
            if self._toolbar_rect().collidepoint(local_pos):
                y = local_pos[1]
                if y < 40:
                    idx = (local_pos[0] - self._toolbar_rect().x) // 60
                    if idx == 0:
                        self._go_back()
                    elif idx == 1:
                        self._go_forward()
                    elif idx == 2:
                        self._go_up()
                    elif idx == 3:
                        self._go_home()
                    elif idx == 4:
                        self._load_dir()
                    elif idx == 5:
                        self._toggle_hidden()
                    elif idx == 6:
                        self._copy_selected()
                    elif idx == 7:
                        self._paste()
                return True
            # breadcrumbs bar
            if self._breadcrumbs_rect().collidepoint(local_pos):
                crumb = self._breadcrumb_at(local_pos)
                if crumb is not None:
                    self._enter_dir(crumb["path"])
                return True
            # navigate to a tile
            tile = self._tile_at(local_pos)
            if tile is not None:
                self.selected = tile["name"]
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 2:
            tile = self._tile_at(local_pos)
            if tile:
                self._open(tile)
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            tile = self._tile_at(local_pos)
            self._show_context_menu(local_pos, tile)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            self.scroll = max(0, min(self._max_scroll(), self.scroll + (-80 if event.button == 4 else 80)))
            return True
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(self._max_scroll(), self.scroll - event.y * 80))
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            tile = self._tile_at(local_pos)
            if tile and self.selected == tile["name"]:
                self._open(tile)
                return True
        return False

    def _toolbar_rect(self):
        return pygame.Rect(self.rect.x, self.rect.y, self.rect.width, 44)

    def _show_context_menu(self, pos, tile):
        items = []
        items.append(("Open", lambda: self._open(tile) if tile else None))
        if tile:
            items.append(("Copy path", lambda: self._copy_path_to_clipboard(tile["path"])))
            items.append(("Copy", lambda: self._copy_path(tile["path"])))
            items.append(("Cut", lambda: self._cut_path(tile["path"])))
            items.append(("Rename", lambda: self._rename(tile)))
            items.append(("Delete", lambda: self._delete(tile["path"])))
        else:
            items.append(("Copy path", lambda: self._copy_path_to_clipboard(self.cwd)))
        items.append(("New Folder", self._new_folder))
        items.append(("Refresh", self._load_dir))
        self.os.open_menu(items, (pos[0] + self.window.content_rect.x,
                                  pos[1] + self.window.content_rect.y))

    def _enter_dir(self, path):
        """Enter path, pushing the current cwd onto the back history."""
        if path and os.path.abspath(path) != os.path.abspath(self.cwd):
            self.history_back.append(self.cwd)
            self.history_forward.clear()
            self.cwd = path
            self._load_dir()

    def _go_back(self):
        if not self.history_back:
            self.show_toast("File Manager", "No previous folder", "info")
            return
        self.history_forward.append(self.cwd)
        self.cwd = self.history_back.pop()
        self._load_dir()

    def _go_forward(self):
        if not self.history_forward:
            self.show_toast("File Manager", "No next folder", "info")
            return
        self.history_back.append(self.cwd)
        self.cwd = self.history_forward.pop()
        self._load_dir()

    def _go_up(self):
        parent = os.path.dirname(self.cwd)
        if parent and parent != self.cwd:
            self._enter_dir(parent)

    def _go_home(self):
        self._enter_dir(os.path.expanduser("~"))

    def _toggle_hidden(self):
        self.show_hidden = not self.show_hidden
        self._load_dir()

    def _breadcrumbs(self):
        """Return (label, path) pairs for each ancestor of the current cwd."""
        home = os.path.expanduser("~")
        crumbs = []
        path = self.cwd
        while True:
            label = os.path.basename(path) or path
            if os.path.abspath(path) == home:
                label = "~"
            crumbs.insert(0, (label, path))
            parent = os.path.dirname(path)
            if not parent or parent == path:
                break
            path = parent
        return crumbs

    def _breadcrumbs_rect(self):
        tb = self._toolbar_rect()
        return pygame.Rect(tb.x + 8, tb.bottom + 2, self.rect.width - 16, 24)

    def _breadcrumb_rects(self, font):
        """Compute clickable rects for each breadcrumb segment."""
        bar = self._breadcrumbs_rect()
        x = bar.x + 8
        out = []
        crumbs = self._breadcrumbs()
        last = len(crumbs) - 1
        for i, (label, path) in enumerate(crumbs):
            sep = font.size("/")[0] + 4 if i < last else 0
            w = font.size(label)[0] + 12 + sep
            out.append({
                "name": label,
                "path": path,
                "last": i == last,
                "rect": pygame.Rect(x, bar.y + 2, w, bar.height - 4),
            })
            x += w
        return out

    def _breadcrumb_at(self, pos):
        if self.search:
            return None
        font = pygame.font.Font(None, 15)
        for b in self._breadcrumb_rects(font):
            if b["rect"].collidepoint(pos):
                return b
        return None

    def _body_rect(self):
        return pygame.Rect(self.rect.x, self.rect.y + 72, self.rect.width, self.rect.height - 104)

    def _max_scroll(self):
        return max(0, (len(self._visible()) + self.cols - 1) // self.cols * self.icon_size -
                   self._body_rect().height)

    def _visible(self):
        if not self.search:
            return self.entries
        q = self.search.lower()
        return [e for e in self.entries if q in e["name"].lower()]

    def _tile_at(self, pos):
        items = self._visible()
        body = self._body_rect()
        cols = self.cols
        for i, e in enumerate(items):
            r = i // cols
            c = i % cols
            tx = body.x + c * self.icon_size
            ty = body.y + r * self.icon_size - self.scroll
            if pygame.Rect(tx, ty, self.icon_size, self.icon_size).collidepoint(pos):
                return e
        return None

    def _open(self, tile):
        if tile["dir"]:
            self._enter_dir(tile["path"])
        else:
            ext = os.path.splitext(tile["name"])[1].lower()
            if ext in (".txt", ".md", ".py", ".json", ".csv", ".log", ".html", ".css", ".js", ".ini", ".toml", ".yml", ".yaml", ".cfg"):
                self.open_app("Text Editor", path=tile["path"])
            elif ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp"):
                self.show_toast("File Manager", "Opening image...", "info")
                self._open_external(tile["path"])
            elif ext in (".mp3", ".wav", ".ogg"):
                self.open_app("Media Player", path=tile["path"])
            else:
                self._open_external(tile["path"])

    def _open_external(self, path):
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            self.show_toast("File Manager", f"Cannot open: {e}", "error")

    def _delete_selected(self):
        if self.selected:
            for e in self.entries:
                if e["name"] == self.selected:
                    self._delete(e["path"])
                    return

    def _delete(self, path):
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            self.show_toast("File Manager", "Deleted", "info")
            self._load_dir()
        except OSError as e:
            self.show_toast("File Manager", f"Delete failed: {e}", "error")

    def _copy_selected(self):
        if self.selected:
            for e in self.entries:
                if e["name"] == self.selected:
                    self._copy_path(e["path"])
                    return

    def _copy_path(self, path):
        self._clipboard = (path, False)
        self.show_toast("File Manager", "Copied", "info")

    def _copy_path_to_clipboard(self, path):
        """Copy a path string to the system clipboard if pyperclip is available."""
        try:
            import pyperclip  # noqa: PLC0415
            pyperclip.copy(path)
            self.show_toast("File Manager", "Path copied", "info")
        except Exception:  # noqa: BLE001
            self.show_toast("File Manager", "Copy path: clipboard unavailable", "info")

    def _cut_selected(self):
        if self.selected:
            for e in self.entries:
                if e["name"] == self.selected:
                    self._cut_path(e["path"])
                    return

    def _cut_path(self, path):
        self._clipboard = (path, True)
        self.show_toast("File Manager", "Cut", "info")

    def _paste(self):
        if not self._clipboard:
            self.show_toast("File Manager", "Clipboard is empty", "info")
            return
        src, cut = self._clipboard
        dst = os.path.join(self.cwd, os.path.basename(src))
        if src == dst:
            self.show_toast("File Manager", "Already here", "info")
            return
        try:
            if cut:
                shutil.move(src, dst)
                self.show_toast("File Manager", "Moved", "success")
            else:
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
                self.show_toast("File Manager", "Copied", "success")
            self._load_dir()
        except OSError as e:
            self.show_toast("File Manager", f"Failed: {e}", "error")

    def _rename(self, tile):
        self.show_toast("File Manager", "Rename: edit in Text Editor & save", "info")

    def _new_folder(self):
        n = 1
        while os.path.exists(os.path.join(self.cwd, f"New Folder {n}")):
            n += 1
        try:
            os.mkdir(os.path.join(self.cwd, f"New Folder {n}"))
            self._load_dir()
        except OSError as e:
            self.show_toast("File Manager", f"Failed: {e}", "error")

    def draw(self, surface, rect):
        self.rect = rect
        font = pygame.font.Font(None, self.os.config.font_size)
        small = pygame.font.Font(None, 15)
        # toolbar
        tb = self._toolbar_rect()
        rounded_rect(surface, tb, 0, self.theme.surface_alt)
        icons = ["←", "→", "↑", "⌂", "⟳", "👁", "⧉", "📋"]
        tips = ["Back", "Forward", "Up", "Home", "Refresh", "Hidden files", "Copy", "Paste"]
        for i, g in enumerate(icons):
            r = pygame.Rect(tb.x + 8 + i * 58, tb.y + 5, 50, 34)
            if r.collidepoint(pygame.mouse.get_pos()):
                rounded_rect(surface, r, 8, self.theme.hover if len(self.theme.hover) == 3 else self.theme.hover[:3])
                tip = small.render(tips[i], True, self.theme.text)
                bg = pygame.Surface((tip.get_width() + 10, tip.get_height() + 6), pygame.SRCALPHA)
                pygame.draw.rect(bg, (40, 40, 50, 230), bg.get_rect(), border_radius=4)
                bg.blit(tip, (5, 3))
                surface.blit(bg, (r.x, r.y - tip.get_height() - 8))
            gimg = font.render(g, True, self.theme.text)
            surface.blit(gimg, gimg.get_rect(center=r.center))
        # breadcrumbs bar
        bc_bar = self._breadcrumbs_rect()
        rounded_rect(surface, bc_bar, 6, self.theme.surface)
        if self.search:
            pimg = small.render(self.search, True, self.theme.accent)
            surface.blit(pimg, (bc_bar.x + 8, bc_bar.centery - pimg.get_height() // 2))
        else:
            for b in self._breadcrumb_rects(small):
                r = b["rect"]
                if b["last"]:
                    bg = self.theme.selection[:3] if len(self.theme.selection) == 3 else self.theme.selection
                elif r.collidepoint(pygame.mouse.get_pos()):
                    bg = self.theme.hover[:3] if len(self.theme.hover) == 3 else self.theme.hover
                else:
                    bg = None
                if bg is not None:
                    rounded_rect(surface, r, 6, bg)
                label = b["name"] + (" /" if not b["last"] else "")
                col = self.theme.accent if b["last"] else self.theme.text_dim
                bimg = small.render(label, True, col)
                surface.blit(bimg, (r.x + 6, r.centery - bimg.get_height() // 2))

        # grid
        body = self._body_rect()
        clip = pygame.Rect(body)
        old = surface.get_clip()
        surface.set_clip(clip)
        items = self._visible()
        if not items:
            eimg = font.render("Empty folder", True, self.theme.text_dim)
            surface.blit(eimg, eimg.get_rect(center=body.center))
        for i, e in enumerate(items):
            r = i // self.cols
            c = i % self.cols
            tx = body.x + c * self.icon_size
            ty = body.y + r * self.icon_size - self.scroll
            if ty + self.icon_size < body.y or ty > body.bottom:
                continue
            tile = pygame.Rect(tx + 2, ty + 2, self.icon_size - 4, self.icon_size - 6)
            selected = self.selected == e["name"]
            if selected:
                rounded_rect(surface, tile, 10,
                             self.theme.selection[:3] if len(self.theme.selection) == 3 else self.theme.selection)
            elif tile.collidepoint(pygame.mouse.get_pos()):
                rounded_rect(surface, tile, 10,
                             self.theme.hover[:3] if len(self.theme.hover) == 3 else self.theme.hover)
            ic = pygame.Rect(tx + (self.icon_size - 40) // 2, ty + 6, 40, 40)
            if e["dir"]:
                rounded_rect(surface, ic, 10, self.theme.accent + (50,))
            ig = font.render(file_icon(e["name"]), True, self.theme.text)
            surface.blit(ig, ig.get_rect(center=ic.center))
            # label (wrapped)
            lines = wrap_text(e["name"], small, self.icon_size - 8)[:2]
            for li, ln in enumerate(lines):
                limg = small.render(ln, True, self.theme.text if e["dir"] else self.theme.text_dim)
                surface.blit(limg, limg.get_rect(midtop=(tile.centerx, ic.bottom + 4 + li * 14)))
        surface.set_clip(old)
        # status bar
        st = pygame.Rect(rect.x, rect.bottom - 26, rect.width, 26)
        s2 = pygame.Surface(st.size, pygame.SRCALPHA)
        pygame.draw.rect(s2, self.theme.surface_alt + (200,), s2.get_rect())
        surface.blit(s2, st.topleft)
        n = len(items)
        sinfo = f"{n} items"
        if self.selected:
            for e in items:
                if e["name"] == self.selected:
                    sinfo += f" · {e['name']}"
                    if not e["dir"]:
                        sinfo += f" · {human_size(e['size'])}"
        simg = small.render(sinfo, True, self.theme.text_dim)
        surface.blit(simg, (st.x + 10, st.centery - simg.get_height() // 2))
        # scrollbar
        max_s = self._max_scroll()
        if max_s > 0:
            rows = (len(items) + self.cols - 1) // self.cols
            sh = max(30, int(body.height * body.height / max(1, rows * self.icon_size)))
            ratio = self.scroll / max_s
            sy = body.y + ratio * (body.height - sh)
            pygame.draw.rect(surface, self.theme.scrollbar, pygame.Rect(body.right - 8, sy, 6, sh), border_radius=3)
