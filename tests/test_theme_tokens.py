# tests/test_theme_tokens.py
import pytest
from lionos.theme import Theme, THEMES, contrast_ratio, ensure_contrast, theme_contrast_report


def test_theme_has_semantic_tokens():
    t = THEMES["dark"]
    assert isinstance(t.radius, int) and t.radius > 0
    assert isinstance(t.spacing, int) and t.spacing > 0
    assert isinstance(t.text_disabled, tuple) and len(t.text_disabled) == 3


def test_contrast_ratio_known_values():
    assert contrast_ratio((0, 0, 0), (255, 255, 255)) > 20
    assert contrast_ratio((0, 0, 0), (0, 0, 0)) == 1.0


def test_ensure_contrast_raises_to_minimum():
    out = ensure_contrast((140, 140, 150), (30, 30, 40), 4.5)
    assert contrast_ratio(out, (30, 30, 40)) >= 4.5


def test_all_themes_pass_body_contrast():
    for name, t in THEMES.items():
        report = theme_contrast_report(t)
        assert report["surface"] >= 4.5, f"{name} body text on surface fails: {report['surface']:.2f}"
        assert report["wallpaper"] >= 4.5, f"{name} body text on wallpaper fails: {report['wallpaper']:.2f}"


def test_theme_interpolates_tokens():
    a, b = THEMES["dark"], THEMES["light"]
    m = a.interpolate(b, 0.5)
    assert isinstance(m.radius, int) and m.radius == a.radius  # ints pass through
