"""AI Assistant app for Lion-OS — chat with a local or cloud LLM."""

from __future__ import annotations

import threading
from typing import List

import pygame

from .base import App
from ..widgets import rounded_rect
from ..ai.providers import get_provider, AIDisabled

SYSTEM_PROMPT = (
    "You are the built-in AI assistant of Lion-OS, a desktop operating system "
    "written in Python with Pygame. Be concise, helpful and friendly. "
    "Keep answers short unless asked for detail."
)

SUGGESTIONS = [
    "What can you do?",
    "Give me a tour of Lion-OS",
    "Write a Python one-liner to list files",
    "Tell me a programming joke",
]


class AIAssistantApp(App):
    name = "AI Assistant"
    icon = "💬"
    description = "Chat with the built-in assistant"
    category = "AI"
    default_w = 620
    default_h = 520
    resizable = True
    singleton = True

    def __init__(self, os, window=None):
        super().__init__(os, window)
        self.messages: List[dict] = []       # {"role", "content"}
        self.input_text = ""
        self.cursor = 0
        self.scroll = 0
        self._blink = 0.0
        self.busy = False
        self.error = ""
        self.status = "connecting"
        self._init_message()
        self._check_provider()

    def _init_message(self):
        self.messages.append({
            "role": "assistant",
            "content": "Hello! I'm the Lion-OS assistant. Ask me anything — or "
                       "use Settings → AI Assistant to pick your provider and model.",
        })

    def _check_provider(self):
        try:
            prov = get_provider(self.os.config)
            self.status = prov.info()
        except AIDisabled:
            self.status = "disabled (Settings → AI Assistant)"
        except Exception as e:
            self.status = f"error: {e}"

    def on_resize(self, rect):
        self.rect = rect

    def handle_event(self, event, local_pos):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN and not (event.mod & pygame.KMOD_SHIFT):
                self._send()
                return True
            if event.key == pygame.K_BACKSPACE:
                if self.cursor > 0:
                    self.input_text = self.input_text[:self.cursor - 1] + self.input_text[self.cursor:]
                    self.cursor -= 1
                return True
            if event.key == pygame.K_LEFT:
                self.cursor = max(0, self.cursor - 1)
                return True
            if event.key == pygame.K_RIGHT:
                self.cursor = min(len(self.input_text), self.cursor + 1)
                return True
            if event.unicode and event.unicode.isprintable():
                self.input_text = self.input_text[:self.cursor] + event.unicode + self.input_text[self.cursor:]
                self.cursor += 1
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # send button
            if self._send_btn().collidepoint(local_pos):
                self._send()
                return True
            # suggestion chips
            for i, s in enumerate(SUGGESTIONS):
                r = self._chip(i)
                if r.collidepoint(local_pos):
                    self.input_text = s
                    self._send()
                    return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            self.scroll = max(0, min(self._max_scroll(), self.scroll + (-40 if event.button == 4 else 40)))
            return True
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(self._max_scroll(), self.scroll - event.y * 40))
            return True
        return False

    def _send(self):
        text = self.input_text.strip()
        if not text or self.busy:
            return
        self.messages.append({"role": "user", "content": text})
        self.input_text = ""
        self.cursor = 0
        self.busy = True
        self.error = ""
        self.scroll = self._max_scroll()
        t = threading.Thread(target=self._ask, args=(text,), daemon=True)
        t.start()

    def _ask(self, text):
        try:
            prov = get_provider(self.os.config)
            history = [{"role": "system", "content": SYSTEM_PROMPT}]
            for m in self.messages[-12:]:
                history.append({"role": m["role"], "content": m["content"]})
            reply = prov.chat(history)
            self.messages.append({"role": "assistant", "content": reply})
        except AIDisabled:
            self.error = "AI assistant is disabled. Enable it in Settings → AI Assistant."
        except Exception as e:
            self.error = f"Could not reach the model: {e}"
            self.messages.append({"role": "assistant",
                                  "content": "⚠️ I couldn't reach my model. Check Settings → AI Assistant "
                                             "(provider, endpoint, API key) and try again."})
        finally:
            self.busy = False
            self._check_provider()

    def _chat_rect(self):
        return pygame.Rect(self.rect.x + 10, self.rect.y + 8, self.rect.width - 20,
                           self.rect.height - 86)

    def _input_rect(self):
        return pygame.Rect(self.rect.x + 10, self.rect.bottom - 62, self.rect.width - 90, 46)

    def _send_btn(self):
        return pygame.Rect(self.rect.right - 74, self.rect.bottom - 62, 60, 46)

    def _chip(self, i):
        return pygame.Rect(self.rect.x + 10 + (i % 2) * 190, self.rect.bottom - 20 + (i // 2) * -14, 180, 26)

    def _max_scroll(self):
        total = sum(self._message_height(m) for m in self.messages)
        return max(0, total - self._chat_rect().height + 20)

    def _message_height(self, m):
        font = pygame.font.Font(None, self.os.config.font_size)
        max_w = self._chat_rect().width - 60
        lines = len(self._wrap(m["content"], font, max_w)) or 1
        return lines * 22 + 30

    def _wrap(self, text, font, max_w):
        out = []
        for para in text.split("\n"):
            words = para.split(" ")
            cur = ""
            for w in words:
                trial = (cur + " " + w).strip()
                if font.size(trial)[0] <= max_w or not cur:
                    cur = trial
                else:
                    out.append(cur)
                    cur = w
            if cur:
                out.append(cur)
        return out

    def update(self, dt):
        self._blink += dt

    def draw(self, surface, rect):
        self.rect = rect
        font = pygame.font.Font(None, self.os.config.font_size)
        small = pygame.font.Font(None, 14)
        cr = self._chat_rect()
        rounded_rect(surface, cr, 12, self.theme.surface)
        # status header
        st = small.render(self.status, True, self.theme.accent)
        surface.blit(st, (cr.x + 14, cr.y + 8))
        pygame.draw.line(surface, self.theme.surface_alt, (cr.x + 8, cr.y + 28), (cr.right - 8, cr.y + 28))

        # messages
        clip = pygame.Rect(cr.x + 6, cr.y + 32, cr.width - 12, cr.height - 40)
        old = surface.get_clip()
        surface.set_clip(clip)
        y = clip.y - self.scroll
        max_w = cr.width - 60
        for m in self.messages:
            is_user = m["role"] == "user"
            text = m["content"]
            lines = self._wrap(text, font, max_w)
            h = len(lines) * 22 + 24
            if is_user:
                bubble = pygame.Rect(cr.right - 20 - max_w, y, max_w, h)
                rounded_rect(surface, bubble, 14, self.theme.accent)
                ty = y + 10
                for ln in lines:
                    li = font.render(ln, True, (255, 255, 255))
                    surface.blit(li, (bubble.x + 12, ty))
                    ty += 22
            else:
                bubble = pygame.Rect(cr.x + 14, y, max_w, h)
                rounded_rect(surface, bubble, 14, self.theme.surface_alt)
                ty = y + 10
                for ln in lines:
                    li = font.render(ln, True, self.theme.text)
                    surface.blit(li, (bubble.x + 12, ty))
                    ty += 22
            y += h + 8
            if y > clip.bottom + 200:
                break
        if self.busy:
            dots = "." * (int(self._blink * 2) % 4)
            di = font.render("thinking" + dots, True, self.theme.text_dim)
            surface.blit(di, (cr.x + 14, y + 4))
        if self.error:
            ei = small.render(self.error[:80], True, self.theme.danger)
            surface.blit(ei, (cr.x + 14, y + 4))
        surface.set_clip(old)

        # input box
        ir = self._input_rect()
        rounded_rect(surface, ir, 10, self.theme.surface_alt)
        pygame.draw.rect(surface, self.theme.accent, ir, 1, border_radius=10)
        shown = self.input_text if self.input_text else "Message the assistant..."
        col = self.theme.text if self.input_text else self.theme.text_dim
        iimg = font.render(shown, True, col)
        surface.blit(iimg, (ir.x + 10, ir.centery - iimg.get_height() // 2))
        if self.input_text and int(self._blink * 2) % 2 == 0:
            cx = ir.x + 10 + font.size(self.input_text[:self.cursor])[0]
            pygame.draw.line(surface, self.theme.accent, (cx, ir.y + 8), (cx, ir.bottom - 8), 2)
        sb = self._send_btn()
        rounded_rect(surface, sb, 10, self.theme.accent if not self.busy else self.theme.surface_alt)
        s = font.render("➤", True, (255, 255, 255))
        surface.blit(s, s.get_rect(center=sb.center))

        # suggestion chips (when empty)
        if not self.input_text and not self.busy:
            for i, sug in enumerate(SUGGESTIONS):
                r = self._chip(i)
                if r.collidepoint(pygame.mouse.get_pos()):
                    rounded_rect(surface, r, 13, self.theme.active)
                else:
                    rounded_rect(surface, r, 13, self.theme.surface_alt)
                si = small.render(sug, True, self.theme.text_dim)
                surface.blit(si, si.get_rect(center=r.center))
