# tests/test_notifications.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
from lionos.kernel import LionOS


def test_notify_adds_and_expires():
    os_ = LionOS()
    os_.notify("Title", "Body")
    assert len(os_._notifications) == 1
    os_._notifications[0].timeout = 0.001
    os_._update_notifications(0.01)
    assert len(os_._notifications) == 0


def test_notify_clear_all():
    os_ = LionOS()
    os_.notify("A", "1")
    os_.notify("B", "2")
    os_.clear_notifications()
    assert len(os_._notifications) == 0
