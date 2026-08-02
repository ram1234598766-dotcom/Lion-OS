# tests/test_anim.py
from lionos.anim import (ease_out_cubic, ease_in_out, ease_out_back,
                         ease_out_elastic, ease_out_bounce, HoverState)


def test_easing_endpoints():
    assert ease_out_cubic(0) == 0 and ease_out_cubic(1) == 1
    assert ease_in_out(0) == 0 and ease_in_out(1) == 1
    assert ease_out_back(1) == 1


def test_easing_in_range():
    for fn in (ease_out_cubic, ease_in_out, ease_out_back,
               ease_out_elastic, ease_out_bounce):
        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
            v = fn(t)
            assert v >= -0.2 and v <= 1.2, (fn.__name__, t, v)


def test_hover_state_tweens():
    h = HoverState(speed=10.0)
    h.update(0.016, True)
    assert h.t > 0
    for _ in range(200):
        h.update(0.016, True)
    assert h.t == 1.0
    for _ in range(200):
        h.update(0.016, False)
    assert h.t == 0.0
