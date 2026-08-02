"""Tiny animation toolkit — easing curves + hover tweens.

Easing functions take ``t`` in [0, 1] and return an eased value in [0, 1]
(overshooting for ``*_back``). ``HoverState`` tweens toward 0/1 so UI can
animate hover, focus and pressed feedback smoothly instead of snapping.
"""
from __future__ import annotations


def ease_out_cubic(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


def ease_in_out(t: float) -> float:
    return 3.0 * t * t - 2.0 * t * t * t if t < 0.5 else \
        (1.0 - (3.0 * (1.0 - t) * (1.0 - t) - 2.0 * (1.0 - t) ** 3))


def ease_out_back(t: float) -> float:
    """Ease-out with a subtle overshoot (great for hover/scale)."""
    c1, c3 = 1.70158, 2.70158
    u = t - 1.0
    return 1.0 + c3 * u * u * u + c1 * u * u


def ease_out_elastic(t: float) -> float:
    """Elastic ease-out (playful entrance)."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    c4 = (2.0 * 3.141592653589793) / 3.0
    return 2 ** (-10 * t) * __import__("math").sin((t * 10 - 0.75) * c4) + 1.0


def ease_out_bounce(t: float) -> float:
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1:
        return n1 * t * t
    if t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


class HoverState:
    """Tweens a value toward ``1.0`` while hovered and ``0.0`` otherwise."""

    def __init__(self, speed: float = 12.0):
        self.speed = speed
        self.t = 0.0

    def update(self, dt: float, active: bool) -> float:
        if active:
            self.t = min(1.0, self.t + self.speed * dt)
        else:
            self.t = max(0.0, self.t - self.speed * dt)
        return self.t
