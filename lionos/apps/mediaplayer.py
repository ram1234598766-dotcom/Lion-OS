"""Media Player app for Lion-OS — plays audio files."""

from __future__ import annotations

import os
import random

import pygame

from .base import App
from ..widgets import TextInput, cached_font, rounded_rect


class MediaPlayerApp(App):
    name = "Media Player"
    icon = "🎵"
    description = "Play audio files"
    category = "Media"
    default_w = 520
    default_h = 460
    resizable = True

    # built-in synth/tone track (played when no audio device / no real files)
    _TONE_NAME = "♪ Synth Tone (440 Hz)"
    _TONE_FREQ = 440.0
    _TONE_SECONDS = 5.0

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
        self.synth = False                 # True = internal tone mode (no mixer file)
        self._tone_sound = None
        self._tone_channel = None
        self.adding = False                # "Add" text field visible?
        self.add_input = TextInput(pygame.Rect(0, 0, 220, 30), font=None,
                                   placeholder="Path or filename to add…",
                                   on_submit=self._add_from_input)
        self._dragging_seek = False        # seek-bar drag state
        self._dragging_vol = False         # volume-slider drag state
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
        ch = getattr(self, "_tone_channel", None)
        if ch:
            try:
                ch.stop()
            except Exception:
                pass

    def handle_event(self, event, local_pos):
        if event.type == pygame.KEYDOWN and self.adding:
            # route typing to the "Add" text field (Enter submits via on_submit)
            if self.add_input.handle_event(event, local_pos, self.theme):
                self.redraw()
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # add / tone buttons
            if self._add_btn().collidepoint(local_pos):
                self.adding = not self.adding
                if self.adding:
                    self.add_input.text = ""
                    self.add_input.cursor = 0
                    self.add_input.focused = True
                self.redraw()
                return True
            if self._tone_btn().collidepoint(local_pos):
                self._play_tone()
                return True
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
            if self._volume_grab().collidepoint(local_pos):
                self._dragging_vol = True
                self._volume_to_x(local_pos[0])
                self.redraw()
                return True
            # seek bar
            if self._seek_grab().collidepoint(local_pos):
                self._dragging_seek = True
                self._seek_to_x(local_pos[0])
                self.redraw()
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
            # "Add" text field: click inside to focus, click elsewhere to dismiss
            if self.adding:
                if self._add_input_rect().collidepoint(local_pos):
                    self.add_input.handle_event(event, local_pos, self.theme)
                else:
                    self.adding = False
                self.redraw()
                return True
        if event.type == pygame.MOUSEMOTION:
            # scrub seek bar / volume while holding the mouse button
            if self._dragging_seek and event.buttons[0]:
                self._seek_to_x(local_pos[0])
                self.redraw()
                return True
            if self._dragging_vol and event.buttons[0]:
                self._volume_to_x(local_pos[0])
                self.redraw()
                return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._dragging_seek or self._dragging_vol:
                self._dragging_seek = False
                self._dragging_vol = False
                self.redraw()
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

    def _seek_bar(self):
        py = self.rect.bottom - 96
        return pygame.Rect(self.rect.x + 60, py, max(40, self.rect.width - 120), 6)

    def _seek_grab(self):
        return self._seek_bar().inflate(0, 14)

    def _volume_grab(self):
        return self._volume_bar().inflate(0, 12)

    def _add_btn(self):
        return pygame.Rect(self.rect.x + 84, self.rect.y + 10, 56, 30)

    def _tone_btn(self):
        return pygame.Rect(self.rect.x + 146, self.rect.y + 10, 70, 30)

    def _add_input_rect(self):
        return pygame.Rect(self.rect.x + 84, self.rect.y + 44, 220, 30)

    def _toggle_play(self):
        if self.current < 0 and self.playlist:
            self._play_index(0)
            return
        if self.playing and not self.paused:
            if self.synth:
                try:
                    self._tone_channel.pause()
                except Exception:
                    pass
            else:
                try:
                    pygame.mixer.music.pause()
                except Exception:
                    pass
            self.paused = True
        elif self.paused:
            if self.synth:
                try:
                    self._tone_channel.unpause()
                except Exception:
                    pass
            else:
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
        if path == self._TONE_NAME:
            self._play_tone()
            return
        self.synth = False
        self.playing = True
        self.paused = False
        self.set_title(f"Media Player — {os.path.basename(path)}")
        ch = self._tone_channel
        if ch:
            try:
                ch.stop()
            except Exception:
                pass
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self.volume)
            pygame.mixer.music.play()
            # estimate duration for the seek bar / elapsed time label
            try:
                snd = pygame.mixer.Sound(path)
                self.duration = snd.get_length()
                snd.stop()
            except Exception:
                self.duration = 0.0
        except Exception as e:
            self.show_toast("Media Player", f"Cannot play: {e}", "error")
            self.playing = False

    def _play_tone(self):
        """Play the built-in synth/tone track (no external audio file needed)."""
        try:
            snd = self._make_tone()
        except Exception as e:
            self.show_toast("Media Player", f"Tone unavailable: {e}", "error")
            return
        if self._TONE_NAME not in self.playlist:
            self.playlist.append(self._TONE_NAME)
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        self.current = self.playlist.index(self._TONE_NAME)
        self.synth = True
        self.playing = True
        self.paused = False
        self.duration = snd.get_length()
        self.position = 0.0
        self._tone_sound = snd
        self._tone_channel = None
        self.set_title(f"Media Player — {self._TONE_NAME}")
        self.redraw()
        try:
            self._tone_channel = snd.play()
        except Exception:
            self.playing = False

    def _make_tone(self, seconds=None, freq=None):
        """Synthesize a short sine-wave tone into a pygame.mixer Sound buffer."""
        import array
        import math
        if seconds is None:
            seconds = self._TONE_SECONDS
        if freq is None:
            freq = self._TONE_FREQ
        init = pygame.mixer.get_init()
        if not init:
            raise RuntimeError("audio mixer unavailable")
        rate, fmt, channels = init
        n = int(rate * seconds)
        amp = 3200
        mono = array.array("h", (int(amp * math.sin(2.0 * math.pi * freq * i / rate))
                                 for i in range(n)))
        buf = mono
        if channels > 1:
            buf = array.array("h")
            for v in mono:
                for _ in range(channels):
                    buf.append(v)
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def _skip(self, delta):
        if not self.playlist:
            return
        if self.shuffle:
            self._play_index(random.randrange(len(self.playlist)))
            return
        self._play_index((self.current + delta) % len(self.playlist))

    def _volume_to_x(self, x):
        vb = self._volume_bar()
        self.volume = max(0.0, min(1.0, (x - vb.x) / vb.width))
        try:
            pygame.mixer.music.set_volume(self.volume)
        except Exception:
            pass

    def _seek_to_x(self, x):
        bar = self._seek_bar()
        ratio = max(0.0, min(1.0, (x - bar.x) / bar.width))
        if self.duration > 0:
            self.position = ratio * self.duration
        if self.synth:
            # synth/tone mode: just advance the internal clock (wraps in update())
            return
        try:
            pygame.mixer.music.set_pos(self.position)
        except Exception:
            pass

    def _add_from_input(self, text):
        text = (text or "").strip()
        if text:
            self.add_file(text)
            self.show_toast("Media Player", "Added to playlist", "success")
        self.adding = False
        self.redraw()

    def update(self, dt):
        if self.playing and not self.paused:
            if self.synth:
                # synth/tone mode: advance the internal clock, wrap at duration
                self.position += dt
                if self.duration > 0 and self.position >= self.duration:
                    if self.loop:
                        self.position = 0.0
                        try:
                            self._tone_channel = self._tone_sound.play()
                        except Exception:
                            pass
                    else:
                        self.playing = False
                        self.position = 0.0
            else:
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
        if self.adding:
            self.add_input.update(dt, self.theme)

    def _fmt(self, t):
        t = max(0, int(t))
        return f"{t // 60}:{t % 60:02d}"

    def draw(self, surface, rect):
        self.rect = rect
        font = cached_font(self.os.config.font_size)
        small = cached_font(14)
        # open button
        ob = self._open_btn()
        rounded_rect(surface, ob, 8, self.theme.surface_alt)
        oimg = font.render("Open", True, self.theme.text)
        surface.blit(oimg, oimg.get_rect(center=ob.center))

        # add / tone buttons
        ab = self._add_btn()
        rounded_rect(surface, ab, 8, self.theme.surface_alt)
        aimg = font.render("Add", True, self.theme.text)
        surface.blit(aimg, aimg.get_rect(center=ab.center))
        tb = self._tone_btn()
        rounded_rect(surface, tb, 8, self.theme.surface_alt)
        timg = font.render("Tone", True, self.theme.text)
        surface.blit(timg, timg.get_rect(center=tb.center))

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

        # seek bar (draggable) + elapsed / total time
        py = self.rect.bottom - 96
        prog = self._seek_bar()
        rounded_rect(surface, prog, 3, self.theme.surface_alt)
        ratio = self.position / self.duration if self.duration > 0 else 0.0
        ratio = max(0.0, min(1.0, ratio))
        if self.duration > 0:
            fill_w = int(prog.width * ratio)
            if fill_w > 0:
                rounded_rect(surface, pygame.Rect(prog.x, prog.y, fill_w, 6), 3, self.theme.accent)
            kx = prog.x + fill_w
            pygame.draw.circle(surface, self.theme.accent, (kx, prog.centery), 7)
            pygame.draw.circle(surface, (255, 255, 255), (kx, prog.centery), 3)
        eimg = small.render(self._fmt(self.position), True, self.theme.text)
        timg = small.render(self._fmt(self.duration), True, self.theme.text_dim)
        surface.blit(eimg, (self.rect.x + 8, py - eimg.get_height() // 2))
        surface.blit(timg, (self.rect.right - 8 - timg.get_width(), py - timg.get_height() // 2))

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
        # volume slider
        vbar = self._volume_bar()
        vimg = small.render("🔊", True, self.theme.text_dim)
        surface.blit(vimg, (vbar.x - 22, vbar.centery - 8))
        rounded_rect(surface, vbar, 4, self.theme.surface_alt)
        vfill = int(vbar.width * self.volume)
        if vfill > 0:
            rounded_rect(surface, pygame.Rect(vbar.x, vbar.y, vfill, 8), 4, self.theme.accent)
        vkx = vbar.x + vfill
        pygame.draw.circle(surface, self.theme.accent, (vkx, vbar.centery), 6)
        pygame.draw.circle(surface, (255, 255, 255), (vkx, vbar.centery), 3)
        pct = small.render(f"{int(self.volume * 100)}%", True, self.theme.text)
        surface.blit(pct, (vbar.centerx - pct.get_width() // 2, vbar.y - 16))

        # "Add" text field (drawn last so it sits on top of the now-playing panel)
        if self.adding:
            self.add_input.font = font
            self.add_input.rect = self._add_input_rect()
            self.add_input.draw(surface, self.theme)
