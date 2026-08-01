"""Browser app for Lion-OS — lightweight web reader."""

from __future__ import annotations

import html
import re
import threading
import urllib.parse

import pygame

from .base import App
from ..widgets import rounded_rect

import requests


def _clean_text(fragment):
    """Strip tags and collapse whitespace."""
    fragment = re.sub(r"<script.*?</script>", "", fragment, flags=re.S | re.I)
    fragment = re.sub(r"<style.*?</style>", "", fragment, flags=re.S | re.I)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html.unescape(fragment)
    fragment = re.sub(r"[ \t]+", " ", fragment)
    fragment = re.sub(r"\n\s*\n+", "\n", fragment)
    return fragment.strip()


class BrowserApp(App):
    name = "Browser"
    icon = "🌐"
    description = "Search the web and read pages"
    category = "Internet"
    default_w = 800
    default_h = 540
    resizable = True

    def __init__(self, os, window=None):
        super().__init__(os, window)
        self.url = "https://www.google.com"
        self.pages = ["https://www.google.com"]
        self.page_idx = 0
        self.loading = False
        self.result_text = ""
        self.result_title = ""
        self.result_error = ""
        self.scroll = 0
        self._lines = []
        self.search_box = ""
        self._focused = False
        self._last_fetch = 0.0
        self._refresh()

    def on_resize(self, rect):
        self.rect = rect

    def _toolbar_rect(self):
        return pygame.Rect(self.rect.x + 8, self.rect.y + 8, self.rect.width - 16, 38)

    def handle_event(self, event, local_pos):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                q = self.search_box
                if q:
                    self._search(q)
                return True
            if event.key == pygame.K_BACKSPACE and self._focused:
                self.search_box = self.search_box[:-1]
                return True
            if event.key == pygame.K_ESCAPE:
                self._focused = False
                return True
            if event.unicode and (event.unicode.isprintable() or event.unicode == " ") and self._focused:
                self.search_box += event.unicode
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            tb = self._toolbar_rect()
            # back / forward / refresh / home
            for i, (glyph, action) in enumerate((("◀", "back"), ("▶", "fwd"), ("⟳", "refresh"), ("⌂", "home"))):
                b = pygame.Rect(tb.x + 8 + i * 40, tb.y + 4, 36, 30)
                if b.collidepoint(local_pos):
                    getattr(self, f"_do_{action}")()
                    return True
            # search box
            sr = self._search_rect()
            if sr.collidepoint(local_pos):
                self._focused = True
                return True
            self._focused = False
            # click on a result link
            link = self._link_at(local_pos)
            if link:
                self._open(link)
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            self.scroll = max(0, min(self._max_scroll(), self.scroll + (-40 if event.button == 4 else 40)))
            return True
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(self._max_scroll(), self.scroll - event.y * 40))
            return True
        return False

    def _search_rect(self):
        tb = self._toolbar_rect()
        return pygame.Rect(tb.x + 180, tb.y + 4, tb.width - 200, 30)

    def _content_rect(self):
        return pygame.Rect(self.rect.x + 12, self.rect.y + 54, self.rect.width - 24, self.rect.height - 66)

    def _do_back(self):
        if self.page_idx > 0:
            self.page_idx -= 1
            self.url = self.pages[self.page_idx]
            self._refresh()

    def _do_fwd(self):
        if self.page_idx < len(self.pages) - 1:
            self.page_idx += 1
            self.url = self.pages[self.page_idx]
            self._refresh()

    def _do_refresh(self):
        self._refresh()

    def _do_home(self):
        self.url = "https://www.google.com"
        self._refresh()

    def _search(self, q):
        query = urllib.parse.quote(q)
        self.url = f"https://html.duckduckgo.com/html/?q={query}"
        self._open(self.url)

    def _open(self, url):
        if not url.startswith("http"):
            url = "https://" + url
        self.url = url
        if self.pages and self.pages[self.page_idx] != url:
            self.pages = self.pages[:self.page_idx + 1] + [url]
            self.page_idx += 1
        self._refresh()

    def _refresh(self):
        self.loading = True
        self.result_error = ""
        self.result_title = ""
        self.result_text = ""
        self._lines = []
        self.scroll = 0
        t = threading.Thread(target=self._fetch, args=(self.url,), daemon=True)
        t.start()

    def _fetch(self, url):
        try:
            r = requests.get(url, timeout=8, headers={
                "User-Agent": "Mozilla/5.0 (Lion-OS Browser)"
            })
            r.raise_for_status()
            text = _clean_text(r.text)
            self.result_text = text
            m = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.S | re.I)
            self.result_title = html.unescape(m.group(1)).strip() if m else url
            self.loading = False
        except Exception as e:
            self.result_error = f"Could not load {url}: {e}"
            self.loading = False

    def _max_scroll(self):
        if not self._lines:
            return 0
        return max(0, len(self._lines) * 22 - self._content_rect().height + 30)

    def _link_at(self, pos):
        """Very simple link detection: find text resembling URLs in view."""
        if not self._lines:
            return None
        cr = self._content_rect()
        idx = (pos[1] - cr.y + self.scroll) // 22
        if 0 <= idx < len(self._lines):
            line = self._lines[idx]
            m = re.search(r"(https?://[^\s]+)", line)
            if m:
                return m.group(1)
        return None

    def update(self, dt):
        # rebuild wrapped lines periodically
        if self.result_text and not self._lines:
            font = pygame.font.Font(None, self.os.config.font_size)
            max_w = self._content_rect().width
            self._lines = self._wrap(self.result_text, font, max_w)

    def _wrap(self, text, font, max_w):
        out = []
        for para in text.split("\n")[:500]:
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

    def draw(self, surface, rect):
        self.rect = rect
        font = pygame.font.Font(None, self.os.config.font_size)
        small = pygame.font.Font(None, 14)
        tb = self._toolbar_rect()
        rounded_rect(surface, tb, 8, self.theme.surface_alt)
        for i, glyph in enumerate(("◀", "▶", "⟳", "⌂")):
            b = pygame.Rect(tb.x + 8 + i * 40, tb.y + 4, 36, 30)
            if b.collidepoint(pygame.mouse.get_pos()):
                rounded_rect(surface, b, 6, self.theme.hover if len(self.theme.hover) == 3 else self.theme.hover[:3])
            gimg = font.render(glyph, True, self.theme.text)
            surface.blit(gimg, gimg.get_rect(center=b.center))
        sr = self._search_rect()
        rounded_rect(surface, sr, 6, self.theme.surface)
        pygame.draw.rect(surface, self.theme.accent, sr, 1, border_radius=6)
        shown = self.search_box if self.search_box else "Search the web..."
        col = self.theme.text if self.search_box else self.theme.text_dim
        simg = small.render(shown, True, col)
        surface.blit(simg, (sr.x + 8, sr.centery - simg.get_height() // 2))

        cr = self._content_rect()
        rounded_rect(surface, cr, 10, self.theme.surface)
        clip = pygame.Rect(cr)
        old = surface.get_clip()
        surface.set_clip(clip)
        if self.loading:
            limg = font.render("Loading...", True, self.theme.text_dim)
            surface.blit(limg, limg.get_rect(center=cr.center))
        elif self.result_error:
            eimg = font.render(self.result_error, True, self.theme.danger)
            surface.blit(eimg, (cr.x + 16, cr.y + 16))
        elif self.result_title:
            t = font.render(self.result_title, True, self.theme.accent)
            surface.blit(t, (cr.x + 16, cr.y + 12))
            for i, ln in enumerate(self._lines):
                ty = cr.y + 48 + i * 22 - self.scroll
                if ty + 22 < cr.y or ty > cr.bottom:
                    continue
                # highlight links
                col = self.theme.text
                if re.search(r"https?://", ln):
                    col = self.theme.info
                limg = small.render(ln, True, col)
                surface.blit(limg, (cr.x + 16, ty))
        else:
            eimg = font.render("Enter a search or URL above.", True, self.theme.text_dim)
            surface.blit(eimg, eimg.get_rect(center=cr.center))
        surface.set_clip(old)
        max_s = self._max_scroll()
        if max_s > 0:
            sh = max(30, int(cr.height * cr.height / max(1, len(self._lines) * 22)))
            ratio = self.scroll / max_s
            sy = cr.y + ratio * (cr.height - sh)
            pygame.draw.rect(surface, self.theme.scrollbar, pygame.Rect(cr.right - 8, sy, 6, sh), border_radius=3)
        # url bar
        uimg = small.render(self.url[:60], True, self.theme.text_dim)
        surface.blit(uimg, (cr.x + 12, cr.bottom - 24))
