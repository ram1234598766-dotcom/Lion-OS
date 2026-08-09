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
use alloc::vec::Vec;
use alloc::vec;

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
        // Off-screen dest clips to nothing (front stays clear).
        let mut front2 = canvas(4, 4, 3);
        front2.blit_from(&back, 8, 8, 4, 4);
        assert_eq!(front2.read_pixel(0, 0), Some(0u32));
        assert_eq!(front2.read_pixel(3, 3), Some(0u32));
    }
}
