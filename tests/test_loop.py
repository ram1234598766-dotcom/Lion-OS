# tests/test_loop.py
import pygame
from lionos.loop import FrameBudget, DirtyTracker, PerfCounters


def test_frame_budget_clamps_dt():
    fb = FrameBudget(60)
    assert fb.tick(0.5) <= 0.05  # clamped to max dt
    assert fb.tick(0.016) <= 0.05


def test_dirty_tracker_small_updates_partial():
    # consume_full and consume_rects are mutually exclusive (each clears);
    # two small, non-overlapping regions stay a partial redraw.
    dt = DirtyTracker()
    dt.mark(pygame.Rect(0, 0, 40, 40))
    dt.mark(pygame.Rect(50, 50, 40, 40))
    rects = dt.consume_rects()
    assert len(rects) >= 1
    assert pygame.Rect(0, 0, 40, 40).inflate(4, 4).colliderect(rects[0])
    dt2 = DirtyTracker()
    dt2.mark(pygame.Rect(0, 0, 40, 40))
    dt2.mark(pygame.Rect(50, 50, 40, 40))
    assert not dt2.consume_full()


def test_dirty_tracker_full_when_many():
    # Widely-spaced rects do not merge, so 10 regions exceed max_rects=4.
    dt = DirtyTracker(max_rects=4)
    for i in range(10):
        dt.mark(pygame.Rect(i * 200, 0, 40, 40))
    assert dt.consume_full()


def test_perf_counters():
    pc = PerfCounters()
    pc.begin_frame()
    pc.end_frame()
    assert pc.fps > 0
    pc.mark_redraw()
    assert pc.redraw_count == 1


def test_kernel_loop_helpers_wire_in():
    # The kernel imports these helpers; ensure they resolve and are the same
    # classes the kernel depends on.
    import lionos.kernel as K
    assert K.MAX_DT == 0.05
    assert hasattr(K, "FrameBudget") and hasattr(K, "DirtyTracker") and hasattr(K, "PerfCounters")
    os_env = K.LionOS()
    assert os_env._frame_budget is not None
    assert os_env._dirty is not None
    assert os_env._perf is not None
    assert os_env.fps == 60.0
