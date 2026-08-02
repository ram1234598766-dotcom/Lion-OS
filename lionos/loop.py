"""Deterministic main-loop helpers: fixed timestep, dirty tracking, perf.

All classes are pure logic (no display calls) so the suite can test them
headlessly.
"""
from __future__ import annotations

import time
from typing import List

import pygame

MAX_DT = 0.05  # clamp to avoid the spiral-of-death after a hitch


class FrameBudget:
    def __init__(self, fps: int = 60):
        self.fps = fps
        self._last = time.perf_counter()
        self.frame_ms = 0.0

    def tick(self, dt: float) -> float:
        self.frame_ms = dt * 1000.0
        return min(MAX_DT, max(0.0001, dt))


class DirtyTracker:
    """Accumulate changed rects; union overlaps; degrade to a full redraw
    when too many regions accumulate."""

    def __init__(self, max_rects: int = 32):
        self.max_rects = max_rects
        self._rects: List[pygame.Rect] = []
        self._full = False

    def mark(self, rect: pygame.Rect):
        if self._full:
            return
        r = rect.inflate(4, 4)  # bleed for shadows/antialias
        for existing in self._rects:
            if existing.colliderect(r):
                existing.union_ip(r)
                return
        self._rects.append(r)
        if len(self._rects) > self.max_rects:
            self._full = True

    def clear(self):
        self._rects = []
        self._full = False

    def consume_full(self) -> bool:
        full = self._full
        self.clear()
        return full

    def consume_rects(self) -> List[pygame.Rect]:
        rects = list(self._rects)
        self.clear()
        return rects


class PerfCounters:
    def __init__(self, window: float = 0.5):
        self._window = window
        self._start = 0.0
        self._frames = 0
        self._acc = 0.0
        self.frame_ms = 0.0
        self.fps = 60.0
        self.redraw_count = 0

    def begin_frame(self):
        self._start = time.perf_counter()

    def end_frame(self):
        self.frame_ms = (time.perf_counter() - self._start) * 1000.0
        self._frames += 1
        self._acc += self.frame_ms
        if self._acc >= self._window * 1000.0:
            self.fps = self._frames / (self._acc / 1000.0)
            self._frames = 0
            self._acc = 0.0

    def mark_redraw(self):
        self.redraw_count += 1
