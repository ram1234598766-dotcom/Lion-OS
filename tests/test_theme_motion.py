# tests/test_theme_motion.py
from lionos.theme import THEMES, accented
from lionos.kernel import LionOS


def test_accent_override_changes_palette():
    t = accented(THEMES["dark"], (255, 0, 0))
    assert t.accent == (255, 0, 0)


def test_kernel_motion_setting():
    os_ = LionOS()
    os_.config.motion = "none"
    assert os_.motion_ok() is False
    os_.config.motion = "full"
    assert os_.motion_ok() is True


def test_kernel_apply_accent():
    os_ = LionOS()
    os_.apply_accent((0, 200, 0))
    assert os_.theme.accent == (0, 200, 0)
