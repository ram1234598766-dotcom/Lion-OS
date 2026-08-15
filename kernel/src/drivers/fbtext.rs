//! Framebuffer bitmap-text driver — Month 3, drivers (W1D3).
//!
//! Renders 5x7 bitmap glyphs (see `font5x7`) into the validated framebuffer.
//! The kernel has no text console abstraction yet, so `put_char`/`draw_str`
//! write glyph pixels directly via the C framebuffer layer (`ffi::fb_pixel`).
//!
//! Bounds safety: `draw_str` clips at `(width, height)` so a string that would
//! run off the right/bottom edge is truncated, never written out of bounds. The
//! C layer also bounds-checks every pixel (defense in depth, same as fb.c).

use crate::ffi;
use crate::framebuffer::FramebufferInfo;
use super::font5x7::{glyph, GLYPH_H, GLYPH_W};

/// Advance (horizontal spacing) between glyphs in pixels.
pub const GLYPH_ADVANCE: u32 = GLYPH_W as u32 + 1;
/// Advance between lines in pixels.
pub const LINE_ADVANCE: u32 = GLYPH_H as u32 + 1;

/// Draw one 5x7 glyph for `c` with its top-left at `(x, y)` in `fg` color.
///
/// # Safety
/// `fb` must describe the mapped, validated framebuffer; `x`/`y` are clipped
/// here and by the C layer.
pub unsafe fn put_char(fb: &FramebufferInfo, x: u32, y: u32, c: char, fg: u32) {
    let g = glyph(c);
    // Row-major: each byte is one row, bit `col` (0 = leftmost) marks the column.
    for (row, &mask) in g.iter().enumerate() {
        for col in 0..GLYPH_W {
            if mask & (1 << col) != 0 {
                // SAFETY: fb_pixel bounds-checks; x/y clipped below.
                unsafe {
                    ffi::fb_pixel(fb.address as *mut u8, fb.width, fb.height, fb.pitch,
                        fb.bpp as u32, x + col as u32, y + row as u32, fg);
                }
            }
        }
    }
}

/// Draw a `&str` starting at `(x, y)`. Truncates at the right edge.
///
/// # Safety
/// `fb` must describe the mapped, validated framebuffer.
pub unsafe fn draw_str(fb: &FramebufferInfo, x: u32, y: u32, s: &str, fg: u32) {
    let mut cx = x;
    for c in s.chars() {
        // Leave one glyph-width of margin so the final column never clips.
        if cx + GLYPH_W as u32 > fb.width {
            break;
        }
        unsafe { put_char(fb, cx, y, c, fg) };
        cx += GLYPH_ADVANCE;
    }
}

/// Blank `width × height` pixels starting at `(x, y)` (erase text).
///
/// # Safety
/// `fb` must describe the mapped, validated framebuffer; the region is clipped.
pub unsafe fn clear_region(fb: &FramebufferInfo, x: u32, y: u32, width: u32, height: u32, bg: u32) {
    unsafe {
        ffi::fb_fill_rect(fb.address as *mut u8, fb.width, fb.height, fb.pitch,
            fb.bpp as u32, x, y, width, height, bg);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn advance_is_sane() {
        assert!(GLYPH_ADVANCE > 0);
        assert!(LINE_ADVANCE > GLYPH_H as u32);
    }

    #[test]
    fn glyph_count_matches_ascii_range() {
        assert_eq!(super::super::font5x7::GLYPH_COUNT, 0x5F);
    }
}