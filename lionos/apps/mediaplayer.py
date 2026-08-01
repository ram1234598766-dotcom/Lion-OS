"""Media Player app for Lion-OS — plays audio files."""

from __future__ import annotations

import os
import random
import time

import pygame

from .base import App
from ..widgets import Button, rounded_rect


class MediaPlayerApp(App):
    name = "Media Player"
    icon = "🎵"
    description = "Play audio files"
    category = "Media"
    default_w = 520
    default_h = 460
    resizable = True

    def __init__(self, os, window=None, path=None):
        super().__init__(os, window)
        self.playlist = []
        self.current = -1
        self.playing = False
        self.paused = False
        self.duration = 0.0
        self.position = 0.0
        self.volume = 0.8
        self.loop = False
        self.shuffle = False
        self.scroll = 0
        self._scan()
        if path:
            self.add_file(path)
        try:
            pygame.mixer.init(frequency=44100)
        except Exception:
            pass

    def _scan(self):
        # scan common music dirs
        dirs = []
        home = os.path.expanduser("~")
        for d in (os.path.join(home, "Music"), os.path.join(home, "Downloads")):
            if os.path.isdir(d):
                dirs.append(d)
        for d in dirs:
            try:
                for f in os.listdir(d):
                    if f.lower().endswith((".mp3", ".wav", ".ogg", ".flac", ".m4a")):
                        self.playlist.append(os.path.join(d, f))
            except OSError:
                pass

    def add_file(self, path):
        if path not in self.playlist:
            self.playlist.append(path)

    def on_resize(self, rect):
        self.rect = rect

    def on_close(self):
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

    def handle_event(self, event, local_pos):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # controls
            if self._play_btn().collidepoint(local_pos):
                self._toggle_play()
                return True
            if self._prev_btn().collidepoint(local_pos):
                self._skip(-1)
                return True
            if self._next_btn().collidepoint(local_pos):
                self._skip(1)
                return True
            if self._loop_btn().collidepoint(local_pos):
                self.loop = not self.loop
                return True
            if self._shuffle_btn().collidepoint(local_pos):
                self.shuffle = not self.shuffle
                return True
            # volume slider
            if self._volume_bar().collidepoint(local_pos):
                x = local_pos[0]
                self.volume = max(0.0, min(1.0, (x - self._volume_bar().x) / self._volume_bar().width))
                try:
                    pygame.mixer.music.set_volume(self.volume)
                except Exception:
                    pass
                return True
            # playlist
            pl = self._playlist_rect()
            if pl.collidepoint(local_pos):
                idx = (local_pos[1] - pl.y - 8) // 30
                if 0 <= idx < len(self.playlist):
                    self._play_index(idx)
                return True
            # open folder
            if self._open_btn().collidepoint(local_pos):
                self.show_toast("Media Player",
                                "Tip: drop audio files into your Music/Downloads folder, then press Refresh",
                                "info")
                self._scan()
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            self.scroll = max(0, min(200, self.scroll + (-30 if event.button == 4 else 30)))
            return True
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(200, self.scroll - event.y * 30))
            return True
        return False

    def _ctrl_y(self):
        return self.rect.y + self.rect.height - 70

    def _play_btn(self):
        return pygame.Rect(self.rect.centerx - 24, self._ctrl_y(), 48, 40)

    def _prev_btn(self):
        return pygame.Rect(self.rect.centerx - 84, self._ctrl_y(), 44, 40)

    def _next_btn(self):
        return pygame.Rect(self.rect.centerx + 40, self._ctrl_y(), 44, 40)

    def _loop_btn(self):
        return pygame.Rect(self.rect.x + 12, self._ctrl_y(), 40, 40)

    def _shuffle_btn(self):
        return pygame.Rect(self.rect.x + 58, self._ctrl_y(), 40, 40)

    def _volume_bar(self):
        return pygame.Rect(self.rect.right - 150, self._ctrl_y() + 16, 130, 8)

    def _open_btn(self):
        return pygame.Rect(self.rect.x + 10, self.rect.y + 10, 70, 30)

    def _playlist_rect(self):
        return pygame.Rect(self.rect.x + 10, self.rect.y + 48, self.rect.width - 20, self.rect.height - 170)

    def _toggle_play(self):
        if self.current < 0 and self.playlist:
            self._play_index(0)
            return
        if self.playing and not self.paused:
            try:
                pygame.mixer.music.pause()
            except Exception:
                pass
            self.paused = True
        elif self.paused:
            try:
                pygame.mixer.music.unpause()
            except Exception:
                pass
            self.paused = False
        else:
            self._play_index(self.current if self.current >= 0 else 0)

    def _play_index(self, idx):
        if not (0 <= idx < len(self.playlist)):
            return
        self.current = idx
        path = self.playlist[idx]
        self.playing = True
        self.paused = False
        self.set_title(f"Media Player — {os.path.basename(path)}")
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self.volume)
            pygame.mixer.music.play()
            self.duration = 0.0
        except Exception as e:
            self.show_toast("Media Player", f"Cannot play: {e}", "error")
            self.playing = False

    def _skip(self, delta):
        if not self.playlist:
            return
        if self.shuffle:
            self._play_index(random.randrange(len(self.playlist)))
            return
        self._play_index((self.current + delta) % len(self.playlist))

    def update(self, dt):
        if self.playing and not self.paused:
            try:
                if pygame.mixer.music.get_busy():
                    self.position = pygame.mixer.music.get_pos() / 1000.0
                elif self.current >= 0:
                    # track finished
                    if self.loop:
                        self._play_index(self.current)
                    else:
                        self._skip(1)
            except Exception:
                pass

    def _fmt(self, t):
        t = max(0, int(t))
        return f"{t // 60}:{t % 60:02d}"

    def draw(self, surface, rect):
        self.rect = rect
        font = pygame.font.Font(None, self.os.config.font_size)
        small = pygame.font.Font(None, 14)
        # open button
        ob = self._open_btn()
        rounded_rect(surface, ob, 8, self.theme.surface_alt)
        oimg = font.render("Open", True, self.theme.text)
        surface.blit(oimg, oimg.get_rect(center=ob.center))

        # now playing
        np = pygame.Rect(self.rect.x + 10, self.rect.y + 44, self.rect.width - 20, 56)
        rounded_rect(surface, np, 10, self.theme.surface_alt)
        if self.current >= 0:
            name = os.path.basename(self.playlist[self.current])
            nimg = small.render(name, True, self.theme.accent)
            surface.blit(nimg, (np.x + 14, np.y + 10))
            stat = "Paused" if self.paused else ("Playing" if self.playing else "Stopped")
            simg = small.render(stat, True, self.theme.text_dim)
            surface.blit(simg, (np.x + 14, np.y + 32))
        else:
            nimg = small.render("No track selected", True, self.theme.text_dim)
            surface.blit(nimg, (np.x + 14, np.centery - nimg.get_height() // 2))

        # playlist
        pl = self._playlist_rect()
        rounded_rect(surface, pl, 10, self.theme.surface)
        clip = pygame.Rect(pl)
        old = surface.get_clip()
        surface.set_clip(clip)
        for i, p in enumerate(self.playlist):
            ty = pl.y + 8 + i * 30 - self.scroll
            if ty + 30 < pl.y or ty > pl.bottom:
                continue
            row = pygame.Rect(pl.x + 4, ty, pl.width - 8, 26)
            if i == self.current:
                rounded_rect(surface, row, 6, self.theme.selection[:3] if len(self.theme.selection) == 3 else self.theme.selection)
            elif row.collidepoint(pygame.mouse.get_pos()):
                rounded_rect(surface, row, 6, self.theme.hover[:3] if len(self.theme.hover) == 3 else self.theme.hover)
            nm = small.render(os.path.basename(p), True, self.theme.text)
            surface.blit(nm, (row.x + 8, row.centery - nm.get_height() // 2))
        surface.set_clip(old)
        if len(self.playlist) * 30 > pl.height:
            sh = max(30, int(pl.height * pl.height / max(1, len(self.playlist) * 30)))
            ratio = self.scroll / max(1, len(self.playlist) * 30 - pl.height)
            sy = pl.y + ratio * (pl.height - sh)
            pygame.draw.rect(surface, self.theme.scrollbar, pygame.Rect(pl.right - 8, sy, 6, sh), border_radius=3)

        # progress bar
        py = self.rect.bottom - 96
        prog = pygame.Rect(self.rect.x + 60, py, self.rect.width - 120, 6)
        rounded_rect(surface, prog, 3, self.theme.surface_alt)
        ratio = self.position / self.duration if self.duration > 0 else 0
        if ratio > 0 and self.duration > 0:
            rounded_rect(surface, pygame.Rect(prog.x, prog.y, int(prog.width * ratio), 6), 3, self.theme.accent)

        # controls
        for b, glyph, active in ((self._loop_btn(), "⟳", self.loop),
                                 (self._shuffle_btn(), "⇄", self.shuffle),
                                 (self._prev_btn(), "⏮", False),
                                 (self._next_btn(), "⏭", False)):
            hover = b.collidepoint(pygame.mouse.get_pos())
            rounded_rect(surface, b, 8, self.theme.accent if active else
                         (self.theme.hover if hover and len(self.theme.hover) == 3 else
                          (self.theme.hover[:3] if hover and len(self.theme.hover) == 4 else self.theme.surface_alt)))
            gimg = font.render(glyph, True, self.theme.accent if active else self.theme.text)
            surface.blit(gimg, gimg.get_rect(center=b.center))
        pb = self._play_btn()
        rounded_rect(surface, pb, 10, self.theme.accent)
        play_glyph = "⏸" if self.playing and not self.paused else "▶"
        gimg = font.render(play_glyph, True, (255, 255, 255))
        surface.blit(gimg, gimg.get_rect(center=pb.center))
        # volume
        vimg = small.render("🔊", True, self.theme.text_dim)
        surface.blit(vimg, (self._volume_bar().x - 22, self._volume_bar().centery - 8))
        rounded_rect(surface, self._volume_bar(), 4, self.theme.surface_alt)
        rounded_rect(surface, pygame.Rect(self._volume_bar().x, self._volume_bar().y,
                                          int(self._volume_bar().width * self.volume), 8), 4, self.theme.accent)
