//! Dock — Month 6, Path A.
//!
//! A horizontal app bar drawn at the bottom of the compositor. The canonical
//! app list is data that the compositor lays out; the pure helpers are
//! host-tested.

use crate::gfx::Canvas;

/// The docked application set (labels only — their bodies live in `fs`/`editor`
/// `/ai`/`theme`).
pub const APPS: [&str; 4] = ["explorer", "editor", "themex", "ai"];

/// Number of docked apps (a stable constant for the boot marker).
pub fn app_count() -> usize {
    APPS.len()
}

/// Return the name of the app button `i` (or None).
pub fn app_name(i: usize) -> Option<&'static str> {
    APPS.get(i).copied()
}

/// Paint the dock as a filled bar `height` rows tall at the bottom of `canvas`
/// (`bg` behind, `accent` app blocks at `col` for each app). Minimal: draw the
/// bar background and a few accent blocks that represent the buttons.
pub fn draw_dock(canvas: &mut Canvas, height: usize, bg: u32, accent: u32) {
    let w = canvas.width();
    let h = canvas.height();
    let y0 = h.saturating_sub(height);
    canvas.fill_rect(0, y0, w, height, bg);
    // one accent "icon" block per app, spread evenly.
    let n = app_count().max(1);
    let step = w / n;
    for i in 0..app_count() {
        canvas.fill_rect(i * step, y0 + 2, step.saturating_sub(2), height.saturating_sub(4), accent);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn canonical_app_set() {
        assert_eq!(app_count(), 4);
        assert_eq!(app_name(0), Some("explorer"));
        assert_eq!(app_name(3), Some("ai"));
        assert_eq!(app_name(99), None);
    }

    #[test]
    fn draw_dock_fills_bottom_bar() {
        let mut buf = [0u8; 12 * 4 * 3]; // 12x4 RGB canvas
        let mut c = crate::gfx::Canvas::new(&mut buf[..], 12, 4, 12 * 3, 3).unwrap();
        draw_dock(&mut c, 2, 0x101010, 0xFFAA00);
        // bottom two rows are non-zero (bar filled)…
        assert_ne!(c.read_pixel(0, 3).unwrap(), 0u32);
        assert_eq!(c.read_pixel(0, 0), Some(0u32)); // top rows untouched
    }
}