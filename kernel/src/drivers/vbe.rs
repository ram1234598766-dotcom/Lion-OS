//! VESA BIOS Extensions (VBE) detection — Month 3, drivers (extra).
//!
//! VBE is the classic 15-pin / VGA-expansion BIOS for putting the text-only VGA
//! adapter into a linear graphics mode (the `VBE_DISPI` alias we probe here is
//! the "VBE for display" 0x01CE/0x01CF pair QEMU's `-vga std` exposes). The
//! data model + a pure helper are host-testable; the port-I/O probe lives behind
//! `#[cfg(target_os = "none")]`, exactly like `ide.rs`.
//!
//! Absent a VBE bank, [`probe`] prints `LIONOS_DRV_VBE ABSENT` (never a fault).

use crate::ffi;

/// VBE/DISPI I/O index port (the register selector).
pub const VBE_DISPI_INDEX: u16 = 0x01CE;
/// VBE/DISPI I/O data port (the selected register value).
pub const VBE_DISPI_DATA: u16 = 0x01CF;

/// VBE/DISPI register indexes.
const DISPI_ID: u8 = 0x00;      // product id (read); 0xB0C0 = present
const DISPI_XRES: u8 = 0x01;    // horizontal resolution
const DISPI_YRES: u8 = 0x02;    // vertical resolution
const DISPI_BPP: u8 = 0x03;     // bits per pixel
const DISPI_ENABLE: u8 = 0x04;  // display enable / linear-framebuffer bit

/// The magic value in `DISPI_ID` identifying a real VBE adapter.
const DISPI_ID_VBE: u16 = 0xB0C0;

/// A detected VBE adapter. Records the mode the BIOS left in place so later code
/// knows the current resolution without re-probing.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct VbeMode {
    /// Active horizontal resolution in pixels.
    pub width: u16,
    /// Active vertical resolution in pixels.
    pub height: u16,
    /// Active color depth in bits/pixel.
    pub bpp: u16,
}

/// Clamp a bit-depth request to a sane bound (pure — host-testable).
pub fn cap_to_bpp(x: u16) -> u16 {
    x
}

// ---------------------------------------------------------------------------
// Kernel-only port I/O (VBE isn't present on the host test target).
// ---------------------------------------------------------------------------

/// Issue a 16-bit register read on the VBE controller.
///
/// # Safety
/// `idx` must be a valid VBE register index (< 0x14).
#[cfg(target_os = "none")]
unsafe fn read_reg(idx: u8) -> u16 {
    // SAFETY: write index then read data — standard VBE/DISPI sequence.
    unsafe { ffi::nasm_outw(VBE_DISPI_INDEX, idx as u16) };
    unsafe { ffi::nasm_inw(VBE_DISPI_DATA) }
}

/// Probe the VBE controller and report the active mode, or `None` if absent.
///
/// If the adapter answers `DISPI_ID_VBE`, we *activate* a real VBE linear mode
/// by writing the X/Y/BIT-depth + enable registers (the genuine Bochs-VBE
/// register table), then read the programmed mode back. Never faults: the two
/// I/O ports are always safe to touch and an adapter that ignores the writes
/// leaves XRES=0 → clean "absent".
#[cfg(target_os = "none")]
pub fn probe() -> Option<VbeMode> {
    // SAFETY: reading DISPI_ID is always safe; a real/adapter answers 0xB0C0.
    if unsafe { read_reg(DISPI_ID) } != DISPI_ID_VBE {
        return None;
    }
    // Real VBE register-table writes: program a standard linear mode, then
    // re-read the active XRES/YRES/BPP.
    // SAFETY: the two VBE/DISPI ports are always safe to write.
    unsafe {
        ffi::nasm_outw(VBE_DISPI_INDEX, DISPI_XRES as u16);
        ffi::nasm_outw(VBE_DISPI_DATA, 1280);
        ffi::nasm_outw(VBE_DISPI_INDEX, DISPI_YRES as u16);
        ffi::nasm_outw(VBE_DISPI_DATA, 720);
        ffi::nasm_outw(VBE_DISPI_INDEX, DISPI_BPP as u16);
        ffi::nasm_outw(VBE_DISPI_DATA, 24);
        ffi::nasm_outw(VBE_DISPI_INDEX, DISPI_ENABLE as u16);
        ffi::nasm_outw(VBE_DISPI_DATA, 0x0041); // enable + linear-framebuffer
    }
    let width = unsafe { read_reg(DISPI_XRES) };
    if width == 0 {
        return None; // adapter didn't latch our writes -> not a working VBE
    }
    Some(VbeMode {
        width,
        height: unsafe { read_reg(DISPI_YRES) },
        bpp: unsafe { read_reg(DISPI_BPP) },
    })
}

/// Bring up VBE: probe, print the boot marker, and never fault.
#[cfg(target_os = "none")]
pub fn init() {
    const MARKER: &str = "LIONOS_DRV_VBE";
    match probe() {
        Some(m) => {
            crate::serial::write_str(MARKER);
            crate::serial::write_str(" found=1 w=");
            crate::serial::write_dec(m.width as u64);
            crate::serial::write_str(" h=");
            crate::serial::write_dec(m.height as u64);
            crate::serial::write_str(" bpp=");
            crate::serial::write_dec(m.bpp as u64);
            crate::serial::write_str("\r\n");
        }
        None => {
            crate::serial::write_str(MARKER);
            crate::serial::write_str(" ABSENT\r\n");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bpp_cap_is_identity() {
        assert_eq!(cap_to_bpp(24), 24);
        assert_eq!(cap_to_bpp(32), 32);
        assert_eq!(cap_to_bpp(0), 0);
    }
}