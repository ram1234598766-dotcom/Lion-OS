"""Terminal app for Lion-OS — an embedded interactive shell."""

from __future__ import annotations

import os
import os as os_module
import queue
import shlex
import subprocess
import sys
import threading
from typing import List

import pygame

from .base import App
from ..widgets import cached_font, rounded_rect

PROMPT_COLOR = (247, 148, 0)
CMD_COLOR = (215, 215, 225)
OUT_COLOR = (205, 205, 215)
ERR_COLOR = (255, 120, 120)


class TerminalApp(App):
    name = "Terminal"
    icon = "▣"
    description = "A shell for your machine"
    category = "System"
    default_w = 720
    default_h = 460
    resizable = True

    def __init__(self, os, window=None):
        super().__init__(os, window)
        self.lines: List[tuple] = [("Lion-OS Terminal", PROMPT_COLOR),
                                   ("Type 'help' for commands.", OUT_COLOR), ("", OUT_COLOR)]
        self.cwd = os_module.path.expanduser("~")
        self.input_line = ""
        self.cursor = 0
        self.scroll = 0
        self._blink = 0.0
        self.history: List[str] = []
        self.history_idx = 0
        self.proc = None
        self.proc_queue = queue.Queue()
        self._spawn_worker()
        self.font_size = self.os.config.font_size
        self._print(f"Python {sys.version.split()[0]} · {os_module.name} shell", OUT_COLOR)
        self._print("Lion-OS virtual terminal ready.", OUT_COLOR)

    def _spawn_worker(self):
        """Read a persistent shell subprocess's output in the background."""
        def worker():
            try:
                shell = os.environ.get("COMSPEC") if os.name == "nt" else "/bin/sh"
                self.proc = subprocess.Popen(
                    [shell], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True,
                    cwd=self.cwd, bufsize=1,
                )
                while self.proc and self.proc.poll() is None:
                    line = self.proc.stdout.readline()
                    if line:
                        self.proc_queue.put(("out", line.rstrip("\n")))
            except Exception:
                self.proc_queue.put(("err", "Shell unavailable"))
        threading.Thread(target=worker, daemon=True).start()

    def on_close(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass

    def _print(self, text, color=OUT_COLOR):
        for ln in text.split("\n"):
            self.lines.append((ln, color))
        if len(self.lines) > 4000:
            self.lines = self.lines[-2000:]

    def _prompt(self):
        home = os_module.path.expanduser("~")
        if self.cwd == home:
            shown = "~"
        elif self.cwd.startswith(home + os_module.sep):
            shown = "~" + self.cwd[len(home):]
        else:
            shown = self.cwd
        return f"{shown} > "

    def on_resize(self, rect):
        self.rect = rect

    def handle_event(self, event, local_pos):
        if event.type == pygame.KEYDOWN:
            return self._key(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            self.scroll = max(0, min(self._max_scroll(), self.scroll + (-30 if event.button == 4 else 30)))
            return True
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(self._max_scroll(), self.scroll - event.y * 30))
            return True
        return False

    def _key(self, event):
        k = event.key
        if k == pygame.K_RETURN:
            self._submit()
            return True
        if k == pygame.K_BACKSPACE:
            if self.cursor > 0:
                self.input_line = self.input_line[:self.cursor - 1] + self.input_line[self.cursor:]
                self.cursor -= 1
            return True
        if k == pygame.K_DELETE:
            self.input_line = self.input_line[:self.cursor] + self.input_line[self.cursor + 1:]
            return True
        if k == pygame.K_LEFT:
            self.cursor = max(0, self.cursor - 1)
            return True
        if k == pygame.K_RIGHT:
            self.cursor = min(len(self.input_line), self.cursor + 1)
            return True
        if k == pygame.K_HOME:
            self.cursor = 0
            return True
        if k == pygame.K_END:
            self.cursor = len(self.input_line)
            return True
        if k == pygame.K_UP:
            if self.history and self.history_idx > 0:
                self.history_idx -= 1
                self.input_line = self.history[self.history_idx]
                self.cursor = len(self.input_line)
            return True
        if k == pygame.K_DOWN:
            if self.history_idx < len(self.history):
                self.history_idx += 1
                self.input_line = self.history[self.history_idx] if self.history_idx < len(self.history) else ""
                self.cursor = len(self.input_line)
            return True
        if k == pygame.K_c and event.mod & pygame.KMOD_CTRL:
            if self.input_line:
                self.input_line = ""
            elif self.proc and self.proc.poll() is None:
                try:
                    self.proc.terminate()
                except Exception:
                    pass
                self._print("^C", OUT_COLOR)
            return True
        if k == pygame.K_l and event.mod & pygame.KMOD_CTRL:
            self.lines = []
            return True
        if event.unicode and event.unicode.isprintable():
            self.input_line = self.input_line[:self.cursor] + event.unicode + self.input_line[self.cursor:]
            self.cursor += 1
            return True
        return False

    def _submit(self):
        self._print(self._prompt() + self.input_line, CMD_COLOR)
        cmd = self.input_line.strip()
        self.input_line = ""
        self.cursor = 0
        if cmd:
            self.history.append(cmd)
            self.history_idx = len(self.history)
        if not cmd:
            return
        if self._handle_builtin(cmd):
            return
        self._run_shell(cmd)
        self.scroll = self._max_scroll()

    def _handle_builtin(self, cmd) -> bool:
        parts = shlex.split(cmd)
        if not parts:
            return True
        head = parts[0]
        if head in ("help",):
            self._print("Built-in commands: help, ls, cd, pwd, echo, cat, clear, python, history, whoami, date, mkdir, rm, touch", OUT_COLOR)
            self._print("Other commands run in your system shell.", OUT_COLOR)
            return True
        if head in ("clear", "cls"):
            self.lines = []
            return True
        if head == "pwd":
            self._print(self.cwd, OUT_COLOR)
            return True
        if head == "ls" or head == "dir":
            try:
                for name in sorted(os.listdir(self.cwd)):
                    self._print(name, OUT_COLOR)
            except OSError as e:
                self._print(str(e), ERR_COLOR)
            return True
        if head == "cd":
            target = parts[1] if len(parts) > 1 else os.path.expanduser("~")
            try:
                new = os.path.abspath(os.path.join(self.cwd, os.path.expanduser(target)))
                if os.path.isdir(new):
                    self.cwd = new
                    if self.proc and self.proc.poll() is None:
                        try:
                            self.proc.terminate()
                        except Exception:
                            pass
                    self._spawn_worker()
                else:
                    self._print(f"cd: no such directory: {target}", ERR_COLOR)
            except OSError as e:
                self._print(str(e), ERR_COLOR)
            return True
        if head == "echo":
            self._print(" ".join(parts[1:]), OUT_COLOR)
            return True
        if head == "cat":
            for f in parts[1:]:
                try:
                    with open(os.path.join(self.cwd, f), "r", encoding="utf-8", errors="replace") as fp:
                        self._print(fp.read(), OUT_COLOR)
                except OSError as e:
                    self._print(str(e), ERR_COLOR)
            return True
        if head == "whoami":
            self._print(os.environ.get("USERNAME") or os.environ.get("USER") or "lion", OUT_COLOR)
            return True
        if head == "date" or head == "time":
            import time as _t
            self._print(_t.ctime(), OUT_COLOR)
            return True
        if head == "mkdir":
            for d in parts[1:]:
                try:
                    os.makedirs(os.path.join(self.cwd, d), exist_ok=True)
                except OSError as e:
                    self._print(str(e), ERR_COLOR)
            return True
        if head == "touch":
            for f in parts[1:]:
                try:
                    with open(os.path.join(self.cwd, f), "a"):
                        pass
                except OSError as e:
                    self._print(str(e), ERR_COLOR)
            return True
        if head == "rm":
            for f in parts[1:]:
                try:
                    os.remove(os.path.join(self.cwd, f))
                except OSError as e:
                    self._print(str(e), ERR_COLOR)
            return True
        if head == "history":
            for i, h in enumerate(self.history[-50:]):
                self._print(f"{i + 1:4d}  {h}", OUT_COLOR)
            return True
        if head == "python" or head == "py":
            self._print("Use 'python -c \"...\"' or run a file.", OUT_COLOR)
            return True
        if head == "start":
            for f in parts[1:]:
                self._print(f"Opening {f}...", OUT_COLOR)
            return True
        if head in ("exit", "quit"):
            self._print("Use the window close button.", OUT_COLOR)
            return True
        return False

    def _run_shell(self, cmd):
        try:
            proc = subprocess.Popen(
                cmd, shell=True, cwd=self.cwd, stdout=subprocess.PIPE,  # nosec B602 — terminal emulator; running shell commands is its purpose
                stderr=subprocess.PIPE, text=True,
            )
            out, err = proc.communicate(timeout=10)
            if out:
                self._print(out.rstrip("\n"), OUT_COLOR)
            if err:
                self._print(err.rstrip("\n"), ERR_COLOR)
        except subprocess.TimeoutExpired:
            self._print("Command timed out.", ERR_COLOR)
        except Exception as e:
            self._print(f"Error: {e}", ERR_COLOR)

    def update(self, dt):
        self._blink += dt
        # drain background shell output
        try:
            while True:
                kind, text = self.proc_queue.get_nowait()
                self._print(text, OUT_COLOR if kind == "out" else ERR_COLOR)
                self.scroll = self._max_scroll()
        except queue.Empty:
            pass

    def _font(self):
        get = getattr(self.os, "get_font", None)
        if get is not None:
            return get(self.font_size)
        return cached_font(self.font_size)

    def _max_scroll(self):
        font = self._font()
        lh = font.get_height() + 4
        return max(0, len(self.lines) * lh - self.rect.height + 30)

    def draw(self, surface, rect):
        self.rect = rect
        rounded_rect(surface, rect, 0, (14, 16, 22))
        font = self._font()
        lh = font.get_height() + 4
        clip = pygame.Rect(rect)
        old = surface.get_clip()
        surface.set_clip(clip)
        x, y = rect.x + 10, rect.y + 8
        start = max(0, self.scroll // lh)
        for i in range(start, len(self.lines)):
            text, color = self.lines[i]
            ty = rect.y + 8 - (self.scroll % lh) + i * lh
            if ty + lh < rect.y or ty > rect.bottom:
                continue
            img = font.render(text, True, color)
            surface.blit(img, (x, ty))
            if ty + lh > rect.bottom:
                break
        # current input line
        iy = rect.y + 8 - (self.scroll % lh) + len(self.lines) * lh
        p = self._prompt()
        pimg = font.render(p, True, self.theme.accent)
        surface.blit(pimg, (x, iy))
        in_x = x + pimg.get_width()
        iimg = font.render(self.input_line, True, CMD_COLOR)
        surface.blit(iimg, (in_x, iy))
        if int(self._blink * 2) % 2 == 0:
            cx = in_x + font.size(self.input_line[:self.cursor])[0]
            pygame.draw.line(surface, (240, 240, 245), (cx, iy), (cx, iy + font.get_height()), 1)
        surface.set_clip(old)
        max_s = self._max_scroll()
        if max_s > 0:
            sh = max(30, int(rect.height * rect.height / max(1, len(self.lines) * lh)))
            ratio = self.scroll / max_s
            sy = rect.y + ratio * (rect.height - sh)
            pygame.draw.rect(surface, (70, 80, 90), pygame.Rect(rect.right - 8, sy, 6, sh), border_radius=3)
