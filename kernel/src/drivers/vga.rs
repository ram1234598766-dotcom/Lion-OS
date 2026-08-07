//! VGA text-mode console (0xB8000) — Month 3, drivers (extra).
//!
//! A classic 80x25 text-mode framebuffer at physical 0xB8000. Bootloader 0.11
//! keeps VGA text mode active behind the framebuffer handoff (QEMU `-vga std`
//! provides both), so we can write a second, structured console here even when
//! the graphics framebuffer is being drawn to.
//!
//! Cell format: 2 bytes per cell — `(char, attr)`, attr = blink(7) bg(6..4)
//! fg(3..0). We write through a direct pointer (VGA text is always identity
//! mapped by the bootloader's page tables).

/// VGA text buffer base (the physical 0xB8000 reached through the physical-
/// memory window, since bootloader 0.11 does NOT identity-map low memory).
pub const VGA_PHYS: usize = 0xB8000;
/// Number of columns (cells per row).
pub const COLS: usize = 80;
/// Number of rows.
pub const ROWS: usize = 25;

/// The mapped virtual address of the VGA text buffer (physical 0xB8000 plus the
/// physical-memory window offset from the paging takeover).
#[cfg(target_os = "none")]
fn vga_base() -> *mut u16 {
    (VGA_PHYS + crate::paging::phys_offset() as usize) as *mut u16
}

/// Current cursor position (row, col) — 0-based.
static mut CURSOR_COL: usize = 0;
static mut CURSOR_ROW: usize = 0;

/// Write one cell at `(row, col)`. `attr` = (bg<<4)|fg.
///
/// # Safety
/// `row < ROWS`, `col < COLS`.
#[cfg(target_os = "none")]
pub unsafe fn put_cell(row: usize, col: usize, c: char, attr: u8) {
    if row >= ROWS || col >= COLS {
        return;
    }
    let idx = row * COLS + col;
    let cell = (c as u8 as u16) | ((attr as u16) << 8);
    // SAFETY: idx < 80*25; the VGA text buffer is mapped via the phys window.
    unsafe { core::ptr::write_volatile(vga_base().add(idx), cell) };
}

/// Clear the whole screen to `attr` (blank spaces).
#[cfg(target_os = "none")]
pub fn clear(attr: u8) {
    for row in 0..ROWS {
        for col in 0..COLS {
            // SAFETY: row/col within bounds.
            unsafe { put_cell(row, col, ' ', attr) };
        }
    }
    // SAFETY: reset cursor.
    unsafe { CURSOR_COL = 0; CURSOR_ROW = 0; }
}

/// Write a string at an absolute `(row, col)` (no cursor movement), clipping to
/// the right edge.
#[cfg(target_os = "none")]
pub fn write_str_at(row: usize, col: usize, s: &str, attr: u8) {
    let mut c = col;
    for ch in s.chars() {
        if c >= COLS {
            break;
        }
        // SAFETY: row < ROWS (checked), c < COLS (checked).
        unsafe { put_cell(row, c, ch, attr) };
        c += 1;
    }
}

/// Write a string at the cursor, advancing it; scrolls at the bottom edge.
#[cfg(target_os = "none")]
pub fn write(s: &str, attr: u8) {
    for ch in s.chars() {
        if ch == '\n' {
            // SAFETY: advance to next line.
            unsafe { CURSOR_ROW += 1; CURSOR_COL = 0; }
            continue;
        }
        // SAFETY: write at cursor, advance col.
        unsafe {
            put_cell(CURSOR_ROW, CURSOR_COL, ch, attr);
            CURSOR_COL += 1;
        }
        if unsafe { CURSOR_COL } >= COLS {
            // SAFETY: wrap to next line.
            unsafe { CURSOR_COL = 0; CURSOR_ROW += 1; }
        }
        if unsafe { CURSOR_ROW } >= ROWS {
            scroll();
            // SAFETY: cursor back to last row.
            unsafe { CURSOR_ROW = ROWS - 1; }
        }
    }
}

/// Scroll the whole screen up one row (row 0 discarded, blank row appended).
#[cfg(target_os = "none")]
pub fn scroll() {
    // SAFETY: move rows 1..25 up one cell-row; VGA text buffer is contiguous.
    unsafe {
        core::ptr::copy(
            vga_base().add(COLS),
            vga_base(),
            (ROWS - 1) * COLS,
        );
        // Clear the last row.
        for col in 0..COLS {
            put_cell(ROWS - 1, col, ' ', 0x07);
        }
    }
}

#[cfg(test)]
mod tests {
    // The VGA buffer is hardware memory; only pure constants are host-tested.
    #[test]
    fn dimensions_are_sane() {
        assert_eq!(super::COLS, 80);
        assert_eq!(super::ROWS, 25);
        // Cell encoding: low byte char, high byte attr.
        let cell = ('A' as u8 as u16) | ((0x0A as u16) << 8);
        assert_eq!(cell & 0x00FF, 'A' as u16);
        assert_eq!(cell >> 8, 0x0A);
    }
}
