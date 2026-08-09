//! Theming — Month 6, Path A.
//!
//! A small `Theme` (a named palette) that recolors a `gfx::Window` set: the
//! focused window uses `accent`, the rest `fg`. Pure + host-tested; the boot
//! shell applies a default "dark" theme and logs it.

use crate::gfx::Window;

/// A named color palette.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Theme {
    pub name: &'static str,
    pub bg: u32,
    pub fg: u32,
    pub accent: u32,
    pub border: u32,
}

impl Theme {
    /// A light palette (for the boot marker, deterministic).
    pub const fn light() -> Self {
        Self { name: "light", bg: 0xF0F0F0, fg: 0x101010, accent: 0x0044FF, border: 0x888888 }
    }
    /// A dark palette (the default UI theme).
    pub const fn dark() -> Self {
        Self { name: "dark", bg: 0x101014, fg: 0xE0E0E0, accent: 0xFFAA00, border: 0x444444 }
    }
}

/// Recolor a `windows` slice: windows[ focused ] → `accent`, the rest → `fg`.
/// Pure; `windows` may be empty or `focused` out of range.
pub fn recolor(t: &Theme, windows: &mut [Window], focused: usize) {
    for (i, w) in windows.iter_mut().enumerate() {
        w.color = if i == focused { t.accent } else { t.fg };
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dark_theme_values() {
        let d = Theme::dark();
        assert_eq!(d.name, "dark");
        assert_eq!(d.accent, 0xFFAA00);
        assert_ne!(d.bg, d.fg);
    }

    #[test]
    fn recolor_sets_focus_accent_others_fg() {
        let d = Theme::dark();
        let mut wins = [
            Window { x: 0, y: 0, w: 4, h: 4, color: 0 },
            Window { x: 0, y: 0, w: 4, h: 4, color: 0 },
            Window { x: 0, y: 0, w: 4, h: 4, color: 0 },
        ];
        recolor(&d, &mut wins, 1);
        assert_eq!(wins[1].color, d.accent);
        assert_eq!(wins[0].color, d.fg);
        assert_eq!(wins[2].color, d.fg);
    }

    #[test]
    fn recolor_out_of_range_focus_is_safe() {
        let d = Theme::light();
        let mut wins = [Window { x: 0, y: 0, w: 2, h: 2, color: 0 }];
        recolor(&d, &mut wins, 9); // no focus -> all fg
        assert_eq!(wins[0].color, d.fg);
    }
}