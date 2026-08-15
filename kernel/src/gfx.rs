//! Graphics primitives — Month 5, the double-buffer foundation.
//!
//! A safe, bounds-checked drawing surface over a caller-owned pixel plane, and
//! a `BackBuffer` that presents by blitting onto a front. The pixel/bounds math
//! is pure and host-tested; the kernel target hands it the bootloader-mapped
//! framebuffer (see `main.rs`) and a heap/frame back buffer.
//!
//! Colors are 0xRRGGBB (alpha ignored); the frame is written little-endian in
//! the framebuffer's bytes-per-pixel (2/3/4). No pixel is ever written outside
//! `buf[..]` — every draw clamps to the Canvas bounds.

use alloc::boxed::Box;
use alloc::vec;
use crate::drivers::font5x7::{glyph, GLYPH_H, GLYPH_W};

/// A bounds-checked pixel plane.
pub struct Canvas<'a> {
    buf: &'a mut [u8],
    width: usize,
    height: usize,
    pitch: usize,
    bpp: usize,
}

impl<'a> Canvas<'a> {
    /// Wrap a pixel plane. `buf` must be at least `height * pitch` bytes and
    /// `width * bpp <= pitch`. Returns `None` if the geometry is inconsistent.
    pub fn new(buf: &'a mut [u8], width: usize, height: usize, pitch: usize, bpp: usize) -> Option<Self> {
        if bpp == 0 || width == 0 || height == 0 {
            return None;
        }
        if width.checked_mul(bpp).map_or(true, |need| need > pitch) {
            return None;
        }
        if height.checked_mul(pitch).map_or(true, |need| need > buf.len()) {
            return None;
        }
        Some(Self { buf, width, height, pitch, bpp })
    }

    pub fn width(&self) -> usize {
        self.width
    }
    pub fn height(&self) -> usize {
        self.height
    }

    /// Offset of pixel `(x, y)` in `buf`, or `None` if out of bounds.
    fn pixel_offset(&self, x: usize, y: usize) -> Option<usize> {
        if x < self.width && y < self.height {
            Some(y * self.pitch + x * self.bpp)
        } else {
            None
        }
    }

    /// Set one pixel; returns `false` if `(x, y)` is outside the canvas.
    pub fn set_pixel(&mut self, x: usize, y: usize, rgb: u32) -> bool {
        match self.pixel_offset(x, y) {
            Some(off) => {
                self.buf[off..off + self.bpp].copy_from_slice(&rgb.to_le_bytes()[..self.bpp]);
                true
            }
            None => false,
        }
    }

    /// Read the packed color of pixel `(x, y)` (as the LE bytes this surface
    /// stores), or `None` if out of bounds. Pure read — used by tests and by a
    /// a blit-verify path.
    pub fn read_pixel(&self, x: usize, y: usize) -> Option<u32> {
        let off = self.pixel_offset(x, y)?;
        let mut c = [0u8; 4];
        c[..self.bpp].copy_from_slice(&self.buf[off..off + self.bpp]);
        Some(u32::from_le_bytes(c))
    }

    /// Fill `[x, x+w) x [y, y+h)`, clipped to the canvas. A fully out-of-bounds
    /// rectangle fills nothing.
    pub fn fill_rect(&mut self, x: usize, y: usize, w: usize, h: usize, rgb: u32) {
        let x0 = x.min(self.width);
        let y0 = y.min(self.height);
        let x1 = x.saturating_add(w).min(self.width);
        let y1 = y.saturating_add(h).min(self.height);
        for yy in y0..y1 {
            for xx in x0..x1 {
                let _ = self.set_pixel(xx, yy, rgb);
            }
        }
    }

    /// Clear the whole canvas with `rgb`.
    pub fn clear(&mut self, rgb: u32) {
        self.fill_rect(0, 0, self.width, self.height, rgb);
    }

    /// Copy a `sw x sh` region from `src`'s top-left corner to `(dx, dy)` on
    /// this canvas, clipped to both surfaces. Returns bytes copied.
    pub fn blit_from(&mut self, src: &Canvas, sw: usize, sh: usize, dx: usize, dy: usize) -> usize {
        let w = sw.min(src.width).min(self.width.saturating_sub(dx));
        let h = sh.min(src.height).min(self.height.saturating_sub(dy));
        let mut copied = 0;
        for row in 0..h {
            let src_off = row * src.pitch;
            let dst_off = (dy + row) * self.pitch + dx * self.bpp;
            let n = w * self.bpp.min(src.bpp);
            let n = n.min(src.buf.len() - src_off).min(self.buf.len() - dst_off);
            if n == 0 {
                continue;
            }
            self.buf[dst_off..dst_off + n].copy_from_slice(&src.buf[src_off..src_off + n]);
            copied += n;
        }
        copied
    }

    /// Draw the 5x7 font string `s` at `(x, y)` with color `fg` (0xRRGGBB).
    ///
    /// Glyphs come from `drivers::font5x7` in **row-major** order: each byte
    /// is one row and bit `col` (0 = leftmost) marks that column, and
    /// `(col,row)` paints directly (same convention as `fbtext::put_char`).
    /// A character whose cell would start past the right edge stops the line
    /// (no wrap). Rows are clipped by `set_pixel`.
    pub fn draw_text(&mut self, mut x: usize, y: usize, s: &str, fg: u32) {
        for ch in s.chars() {
            if x.saturating_add(GLYPH_W) > self.width {
                break;
            }
            let g = glyph(ch);
            for (row, &mask) in g.iter().enumerate() {
                for col in 0..GLYPH_W {
                    if mask & (1 << col) != 0 {
                        let _ = self.set_pixel(x + col, y.saturating_add(row), fg);
                    }
                }
            }
            x += GLYPH_W + 1;
        }
    }

    /// Blend `fg` over the existing pixel at `(x, y)` with `alpha` in
    /// `[0, 255]`. `alpha == 0` is a no-op (returns `true`); `alpha >= 255`
    /// overwrites. Returns `false` if `(x, y)` is out of bounds.
    pub fn blend_pixel(&mut self, x: usize, y: usize, fg: u32, alpha: u32) -> bool {
        if alpha == 0 {
            return true;
        }
        let bg = match self.read_pixel(x, y) {
            Some(c) => c,
            None => return false,
        };
        if alpha >= 255 {
            let _ = self.set_pixel(x, y, fg);
            return true;
        }
        let inv = 255 - alpha;
        let fr = (fg >> 16) & 0xff;
        let fg_ = (fg >> 8) & 0xff;
        let fb = fg & 0xff;
        let br = (bg >> 16) & 0xff;
        let bg_ = (bg >> 8) & 0xff;
        let bb = bg & 0xff;
        let r = (fr * alpha + br * inv) / 255;
        let g = (fg_ * alpha + bg_ * inv) / 255;
        let b = (fb * alpha + bb * inv) / 255;
        let _ = self.set_pixel(x, y, (r << 16) | (g << 8) | b);
        true
    }

    /// Draw `s` at `(x, y)` with anti-aliased, `scale`-multiplied 5x7 glyphs
    /// using supersampling (SS = 3) and Porter-Duff source-over blending. No
    /// external font dependency. Each output pixel is covered by an `SS x SS`
    /// supersample grid over the scaled glyph; the on-fraction becomes the
    /// blend alpha. `scale == 0` draws nothing. Glyphs that would start past
    /// the right edge stop the line (no wrap).
    pub fn draw_text_aa(&mut self, mut x: usize, y: usize, s: &str, fg: u32, scale: usize) {
        if scale == 0 {
            return;
        }
        let ss = 3usize;
        let fine = ss * scale; // supersample steps per glyph cell
        for ch in s.chars() {
            if x.saturating_add(scale * GLYPH_W) > self.width {
                break;
            }
            let g = glyph(ch);
            let ow = scale * GLYPH_W;
            let oh = scale * GLYPH_H;
            for oy in 0..oh {
                for ox in 0..ow {
                    let mut on = 0u32;
                    for sy in 0..ss {
                        let fy = oy * ss + sy;
                        let grow = fy / fine;
                        if grow >= GLYPH_H {
                            continue;
                        }
                        let row_mask = g[grow];
                        for sx in 0..ss {
                            let fx = ox * ss + sx;
                            let gcol = fx / fine;
                            if gcol < GLYPH_W && (row_mask & (1u8 << gcol)) != 0 {
                                on += 1;
                            }
                        }
                    }
                    let alpha = (on * 255) / ((ss * ss) as u32);
                    let _ = self.blend_pixel(x + ox, y + oy, fg, alpha);
                }
            }
            x += scale * (GLYPH_W + 1);
        }
    }
}

/// An owned back-buffer (`Canvas` over its own plane) that can present onto a
/// front canvas. On the kernel target the plane is leaked (lives for the kernel
/// lifetime — the compositor is a single long-lived object, so this is the
/// intended ownership model); on the host it is a plain `Vec`.
pub struct BackBuffer {
    pub canvas: Canvas<'static>,
}

impl BackBuffer {
    /// Allocate a `w x h` plane with `bpp` bytes per pixel (pitch = w*bpp).
    pub fn new(width: usize, height: usize, bpp: usize) -> Option<Self> {
        let pitch = width.checked_mul(bpp)?;
        let total = pitch.checked_mul(height)?;
        let plane = vec![0u8; total];
        // Leak so the Canvas can borrow it for its lifetime; the kernel owns
        // the result for the whole run.
        let buf: &'static mut [u8] = Box::leak(plane.into_boxed_slice());
        let canvas = Canvas::new(buf, width, height, pitch, bpp)?;
        Some(Self { canvas })
    }
}

// ------------------------- compositor primitives ----------------------------

/// A rectangular, axis-aligned window to be composited. Plain data — a `Canvas`
/// paints an ordered list, later entries are on top (painter's algorithm), and
/// a window is moved/resized by editing these fields.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Window {
    pub x: usize,
    pub y: usize,
    pub w: usize,
    pub h: usize,
    pub color: u32,
}

impl Window {
    /// True if pixel `(px, py)` is inside this window.
    pub fn covers(&self, px: usize, py: usize) -> bool {
        px >= self.x && px < self.x + self.w && py >= self.y && py < self.y + self.h
    }
}

/// Composite `windows` onto `canvas` in list order (index 0 = bottom, the last
/// entry = top). A rectangle drawn later overwrites any overlap from earlier
/// ones — the classic painter's algorithm for axis-aligned rectangles. Each
/// fill_rect clips to the canvas, so fully-offscreen windows draw nothing.
pub fn paint_scene(canvas: &mut Canvas, windows: &[Window]) {
    for w in windows {
        canvas.fill_rect(w.x, w.y, w.w, w.h, w.color);
    }
}

/// Return the index of the **topmost** window containing `(mx, my)` — i.e. the
/// focused window at a pointer/cursor position. Scans top (last) → bottom.
pub fn focus(windows: &[Window], mx: usize, my: usize) -> Option<usize> {
    (0..windows.len()).rev().find(|&i| windows[i].covers(mx, my))
}

/// Height of the title-bar strip painted by [`decorate_window`], in pixels.
pub const TITLE_BAR_H: usize = 18;

/// Paint a window's chrome over an already-composited body: a 1px border in
/// `w.color` plus a `TITLE_BAR_H`-tall title strip (title text vertically
/// centered, left-aligned with a small pad). Everything clips to the canvas,
/// and the strip height is clamped to the window so a tiny window degrades
/// gracefully instead of painting outside its box.
pub fn decorate_window(canvas: &mut Canvas, w: &Window, title: &str, title_fg: u32, title_bg: u32) {
    let strip_h = TITLE_BAR_H.min(w.h);
    // Title bar: background strip, then the title text centered on it.
    canvas.fill_rect(w.x, w.y, w.w, strip_h, title_bg);
    let ty = w.y + strip_h.saturating_sub(2 * GLYPH_H) / 2;
    canvas.draw_text_aa(w.x + 4, ty, title, title_fg, 2);
    // 1px border around the whole window, drawn last so it frames the strip.
    canvas.fill_rect(w.x, w.y, w.w, 1, w.color);
    canvas.fill_rect(w.x, w.y.saturating_add(w.h).saturating_sub(1), w.w, 1, w.color);
    canvas.fill_rect(w.x, w.y, 1, w.h, w.color);
    canvas.fill_rect(w.x.saturating_add(w.w).saturating_sub(1), w.y, 1, w.h, w.color);
}

/// Fill `canvas` with a simple vertical gradient (deterministic per `(x,y)`).
/// `tick` shifts the bands for an animated wallpaper. px `> w` scroll, index.
pub fn gradient_fill(canvas: &mut Canvas, tick: u32) {
    let h = canvas.height();
    let w = canvas.width();
    for y in 0..h {
        // A per-row phase that advances with `tick` (→ animated).
        let phase = (y as u32 + tick) & 0xFF;
        for x in 0..w {
            let _ = x;
            let r = 0x10u32.wrapping_add(phase & 0x3F);
            let g = 0x20u32.wrapping_add((phase >> 1) & 0x3F);
            let b = 0x30u32.wrapping_add((phase >> 2) & 0x3F);
            canvas.set_pixel(x, y, (r << 16) | (g << 8) | b);
        }
    }
}

/// An animated diagonal drifting wallpaper. `tick` advances both the vertical
/// and horizontal phase, so the color bands drift diagonally (rather than the
/// single-axis scroll of `gradient_fill`). Deterministic per `(x, y, tick)`,
/// fully bounded by the canvas (via `set_pixel`), and host-testable.
pub fn wallpaper_drift(canvas: &mut Canvas, tick: u32) {
    let h = canvas.height();
    let w = canvas.width();
    for y in 0..h {
        for x in 0..w {
            // Two-phase: add the column so the pattern shifts horizontally with
            // `tick` too, producing a diagonal drift.
            let phase = (y as u32 + x as u32 + tick) & 0xFF;
            let r = 0x10u32.wrapping_add(phase & 0x3F);
            let g = 0x20u32.wrapping_add((phase >> 1) & 0x3F);
            let b = 0x30u32.wrapping_add((phase >> 2) & 0x3F);
            canvas.set_pixel(x, y, (r << 16) | (g << 8) | b);
        }
    }
}

/// The classic "overshoot" ease (Kenny's ease-out-back, 1.70158 c1): starts at
/// 0, rises past 1, and settles exactly on 1 at `t == 1.0`. Bounded to `[0, 1]`
/// so callers can feed it a scale/duration safely. Pure and host-testable.
pub fn ease_out_back(t: f32) -> f32 {
    let t = t.clamp(0.0, 1.0);
    let c1 = 1.70158;
    let c3 = c1 + 1.0;
    let x = t - 1.0;
    1.0 + c3 * x * x * x + c1 * x * x
}

/// Map `t` in `[0, 1]` to a value that pops from `base - mag` up through
/// `base` (with a slight overshoot) and settles at `base`. Used for a dock /
/// window-focus pop: `dock_pop(t, base, mag)` = `base + mag * ease_out_back(t)`.
pub fn dock_pop(t: f32, base: i32, mag: i32) -> i32 {
    base + (mag as f32 * ease_out_back(t)) as i32
}

#[cfg(test)]
mod tests {
    use super::*;

    fn canvas(w: usize, h: usize, bpp: usize) -> Canvas<'static> {
        let mut v = vec![0u8; w * h * bpp];
        let buf: &'static mut [u8] = Box::leak(v.into_boxed_slice());
        Canvas::new(buf, w, h, w * bpp, bpp).unwrap()
    }

    #[test]
    fn new_rejects_bad_geometry() {
        let mut v = [0u8; 16];
        // bpp 4 with width 8 on pitch 16 (needs 32) -> reject.
        assert!(Canvas::new(&mut v[..], 8, 2, 16, 4).is_none());
        // zero dims reject.
        assert!(Canvas::new(&mut v[..], 0, 2, 8, 1).is_none());
        // too-small buffer rejects (needs 16 bytes, only 15 supplied).
        assert!(Canvas::new(&mut v[..15], 4, 4, 4, 1).is_none());
    }

    #[test]
    fn set_pixel_bounds_and_bytes() {
        let mut c = canvas(4, 2, 3); // 4x2, 24-bit
        assert!(c.set_pixel(0, 0, 0x00FF00)); // green
        assert_eq!(c.read_pixel(0, 0), Some(0x00FF00)); // round-trips
        assert!(!c.set_pixel(4, 0, 0x0)); // x == width -> false
        assert!(!c.set_pixel(0, 2, 0x0)); // y == height -> false
        assert_eq!(c.read_pixel(4, 0), None);
        assert_eq!(c.read_pixel(0, 2), None);
        // rejected writes didn't clobber (1,0) etc.
        assert_eq!(c.read_pixel(1, 0), Some(0));
    }

    #[test]
    fn fill_rect_clips_to_bounds() {
        let mut c = canvas(6, 4, 1); // 1 byte/pixel
        c.fill_rect(0, 0, 6, 4, 0xAA); // full
        let painted = (0..4)
            .flat_map(|y| (0..6).map(move |x| (x, y)))
            .filter(|&(x, y)| c.read_pixel(x, y) == Some(0xAA))
            .count();
        assert_eq!(painted, 24);
        // rectangle partially off-canvas clips.
        let mut c2 = canvas(6, 4, 1);
        c2.fill_rect(4, 3, 5, 5, 0xBB); // x 4..6, y 3..4
        let painted2 = (0..4)
            .flat_map(|y| (0..6).map(move |x| (x, y)))
            .filter(|&(x, y)| c2.read_pixel(x, y) == Some(0xBB))
            .count();
        assert_eq!(painted2, 2);
    }

    #[test]
    fn clear_writes_every_pixel() {
        let mut c = canvas(3, 2, 4);
        c.clear(0x102030);
        assert_eq!(c.read_pixel(0, 0), Some(0x102030));
        assert_eq!(c.read_pixel(2, 1), Some(0x102030));
    }

    #[test]
    fn blit_copies_region_and_respects_bounds() {
        let mut back = canvas(8, 8, 3);
        back.fill_rect(0, 0, 8, 8, 0xFF0000); // red
        let mut front = canvas(8, 8, 3);
        front.blit_from(&back, 8, 8, 0, 0);
        assert_eq!(front.read_pixel(0, 0), back.read_pixel(0, 0));
        assert_eq!(front.read_pixel(7, 7), back.read_pixel(7, 7));
        let mut front2 = canvas(4, 4, 3);
        front2.blit_from(&back, 8, 8, 4, 4);
        assert_eq!(front2.read_pixel(0, 0), Some(0u32));
        assert_eq!(front2.read_pixel(3, 3), Some(0u32));
    }

    #[test]
    fn painter_z_order_overlap() {
        let mut c = canvas(10, 10, 3);
        // bottom: red (0,0,8,8); top: blue (2,2,4,4).
        paint_scene(&mut c, &[
            Window { x: 0, y: 0, w: 8, h: 8, color: 0xFF0000 },
            Window { x: 2, y: 2, w: 4, h: 4, color: 0x0000FF },
        ]);
        assert_eq!(c.read_pixel(1, 1), Some(0xFF0000)); // only bottom
        assert_eq!(c.read_pixel(3, 3), Some(0x0000FF)); // overlap -> top
        assert_eq!(c.read_pixel(9, 9), Some(0)); // outside both -> clear
    }

    #[test]
    fn painter_clips_offscreen_window() {
        let mut c = canvas(6, 6, 3);
        paint_scene(&mut c, &[Window { x: 5, y: 0, w: 10, h: 10, color: 0x00FF00 }]);
        assert_eq!(c.read_pixel(5, 0), Some(0x00FF00)); // only column 5 in bounds
        assert_eq!(c.read_pixel(4, 0), Some(0));
    }

    #[test]
    fn focus_returns_topmost() {
        let wins = [
            Window { x: 0, y: 0, w: 6, h: 6, color: 0x010101 },
            Window { x: 2, y: 2, w: 6, h: 6, color: 0x020202 },
        ];
        assert_eq!(focus(&wins, 1, 1), Some(0)); // only first
        assert_eq!(focus(&wins, 3, 3), Some(1)); // topmost
        assert_eq!(focus(&wins, 20, 20), None);
    }

    #[test]
    fn gradient_advances_and_varies_by_row() {
        let mut a = canvas(16, 8, 4);
        let mut b = canvas(16, 8, 4);
        gradient_fill(&mut a, 0);
        gradient_fill(&mut b, 8);
        assert_ne!(a.read_pixel(0, 0), b.read_pixel(0, 0)); // tick animates
        assert_ne!(a.read_pixel(0, 0), a.read_pixel(0, 1)); // vertical gradient
    }

    #[test]
    fn wallpaper_drift_animates_with_tick() {
        let mut a = canvas(16, 8, 4);
        let mut b = canvas(16, 8, 4);
        wallpaper_drift(&mut a, 0);
        wallpaper_drift(&mut b, 7);
        assert_ne!(a.read_pixel(0, 0), b.read_pixel(0, 0)); // tick animates
    }

    #[test]
    fn wallpaper_drift_varies_by_column_diagonal() {
        // Horizontal phase means (0,0) differs from a same-row column (w-1,0).
        let mut a = canvas(24, 8, 4);
        wallpaper_drift(&mut a, 0);
        assert_ne!(a.read_pixel(0, 0), a.read_pixel(23, 0));
    }

    #[test]
    fn wallpaper_drift_stays_in_bounds() {
        // Every written pixel is readable back — nothing was written OOB.
        let mut a = canvas(20, 12, 4);
        wallpaper_drift(&mut a, 5);
        for y in 0..12 {
            for x in 0..20 {
                assert!(a.read_pixel(x, y).is_some());
            }
        }
        assert_eq!(a.read_pixel(20, 0), None); // still clipped
    }

    #[test]
    fn ease_out_back_is_bounded_and_anchored() {
        assert_eq!(ease_out_back(0.0), 0.0);
        assert_eq!(ease_out_back(1.0), 1.0);
        // Overshoot stays within the sane [0, 1.2] band for the whole range.
        let mut t = 0.0f32;
        while t <= 1.0 {
            let v = ease_out_back(t);
            assert!((0.0..=1.2).contains(&v), "ease_out_back({t}) = {v} out of band");
            t += 0.05;
        }
    }

    #[test]
    fn dock_pop_settles_at_base() {
        assert_eq!(dock_pop(1.0, 10, 5), 15); // settled -> base + mag
        assert_eq!(dock_pop(0.0, 10, 5), 10); // start -> base
        // Overshoot region nudges above base before settling (peak value).
        assert!(dock_pop(0.5, 10, 5) >= 10);
    }

    #[test]
    fn draw_text_renders_known_glyph_pixels() {
        // 'A' = [0x06, 0x09, 0x09, 0x0F, 0x09, 0x09, 0x09] row-major:
        // row 0 -> cols 1,2; row 1 -> cols 0,3; row 3 -> full bar cols 0..=4.
        let mut c = canvas(10, 8, 1);
        c.draw_text(0, 0, "A", 0xFF);
        assert_eq!(c.read_pixel(1, 0), Some(0xFF));
        assert_eq!(c.read_pixel(2, 0), Some(0xFF));
        assert_eq!(c.read_pixel(0, 1), Some(0xFF));
        assert_eq!(c.read_pixel(3, 1), Some(0xFF));
        assert_eq!(c.read_pixel(1, 1), Some(0));
        for x in 0..5 {
            assert_eq!(c.read_pixel(x, 3), Some(0xFF));
        }
        assert_eq!(c.read_pixel(5, 3), Some(0)); // spacer column empty
    }

    #[test]
    fn draw_text_skips_character_that_does_not_fit() {
        // A 5px-wide canvas holds exactly one 5x7 glyph; the second 'A' would
        // start at x=6 and is dropped (no wrap).
        let mut one = canvas(5, 8, 1);
        one.draw_text(0, 0, "A", 0xFF);
        let mut two = canvas(5, 8, 1);
        two.draw_text(0, 0, "AA", 0xFF);
        for y in 0..8 {
            for x in 0..5 {
                assert_eq!(two.read_pixel(x, y), one.read_pixel(x, y));
            }
        }
    }

    #[test]
    fn draw_text_spaces_letters_by_glyph_w_plus_one() {
        // 'A' at x=0 and x=6; the spacer column (x=5) stays untouched.
        let mut c = canvas(12, 8, 1);
        c.draw_text(0, 0, "AA", 0xFF);
        assert_eq!(c.read_pixel(5, 3), Some(0)); // spacer between letters
        assert_eq!(c.read_pixel(6, 3), Some(0xFF)); // second letter's row 3
        assert_eq!(c.read_pixel(0, 3), Some(0xFF)); // first letter intact
    }

    #[test]
    fn draw_text_maps_non_printable_to_question() {
        let mut c = canvas(10, 8, 1);
        c.draw_text(0, 0, "\n", 0xFF);
        // '\n' has no glyph; the font falls back to '?' — identical output.
        let mut q = canvas(10, 8, 1);
        q.draw_text(0, 0, "?", 0xFF);
        for y in 0..8 {
            for x in 0..10 {
                assert_eq!(c.read_pixel(x, y), q.read_pixel(x, y));
            }
        }
    }

    #[test]
    fn decorate_window_paints_border_title_bar_and_text() {
        let mut c = canvas(40, 30, 3);
        let w = Window { x: 4, y: 4, w: 20, h: 16, color: 0x00FF00 };
        decorate_window(&mut c, &w, "Hi", 0xFFFFFF, 0x000000);
        // strip_h = min(18, 16) = 16; AA scale 2 -> title ty = 4 + (16-14)/2 = 5;
        // 'H' starts at (4+4, 5) = (8,5); 'H' row 0 col 0 is on -> (8,5) white.
        assert_eq!(c.read_pixel(8, 5), Some(0xFFFFFF));
        assert_eq!(c.read_pixel(5, 5), Some(0x000000)); // inside strip, no glyph
        // 1px border in the window color.
        assert_eq!(c.read_pixel(4, 4), Some(0x00FF00)); // top-left
        assert_eq!(c.read_pixel(23, 4), Some(0x00FF00)); // top-right
        assert_eq!(c.read_pixel(4, 19), Some(0x00FF00)); // bottom-left
        assert_eq!(c.read_pixel(23, 19), Some(0x00FF00)); // bottom-right
        // Inside the window, off-glyph: strip background untouched (0).
        assert_eq!(c.read_pixel(10, 12), Some(0));
        // Outside the window: untouched.
        assert_eq!(c.read_pixel(2, 2), Some(0));
    }

    #[test]
    fn blend_pixel_half_over_black_is_grey() {
        let mut c = canvas(4, 4, 4);
        c.clear(0x000000);
        assert!(c.blend_pixel(1, 1, 0xFFFFFF, 128));
        let p = c.read_pixel(1, 1).unwrap();
        // ~0x808080 with 1/255 rounding tolerance.
        assert!((p as i32 - 0x808080i32).abs() <= 0x010101, "got {:#x}", p);
    }

    #[test]
    fn blend_pixel_opaque_overwrites() {
        let mut c = canvas(4, 4, 4);
        c.clear(0x000000);
        assert!(c.blend_pixel(1, 1, 0x0000FF, 255));
        assert_eq!(c.read_pixel(1, 1), Some(0x0000FF));
    }

    #[test]
    fn blend_pixel_zero_alpha_is_noop() {
        let mut c = canvas(4, 4, 4);
        c.clear(0x000000);
        assert!(c.blend_pixel(1, 1, 0xFFFFFF, 0));
        assert_eq!(c.read_pixel(1, 1), Some(0x000000));
    }

    #[test]
    fn draw_text_aa_opaque_core_and_off_glyph() {
        let mut c = canvas(16, 16, 4);
        c.clear(0x000000);
        c.draw_text_aa(2, 2, "H", 0xFFFFFF, 2);
        // 'H' output (ox=0, oy=0) at fb (2,2): fully covered -> white.
        assert_eq!(c.read_pixel(2, 2), Some(0xFFFFFF));
        // Before the glyph origin: untouched.
        assert_eq!(c.read_pixel(0, 0), Some(0x000000));
    }
}
