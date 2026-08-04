//! Framebuffer descriptor validation.
//!
//! **Not yet wired at boot:** bootloader 0.9.35 does not hand the kernel a UEFI
//! GOP framebuffer descriptor, so nothing calls [`validate`] during a boot yet.
//! This parser is the kernel-side contract for the framebuffer handoff (planned
//! via a bootloader 0.10/0.11 upgrade; see `docs/ARCHITECTURE.md` §1) and is
//! kept pure so it can be unit-tested and fuzzed now. It is scaffold
//! (boilerplate) — the single consumer arrives with the framebuffer handoff.

/// A validated linear-framebuffer descriptor.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FramebufferInfo {
    /// Physical start address of the framebuffer.
    pub address: u64,
    /// Width in pixels.
    pub width: u32,
    /// Height in pixels.
    pub height: u32,
    /// Bits per pixel.
    pub bpp: u8,
    /// Bytes per scanline (pitch/stride).
    pub pitch: u32,
}

/// Why a framebuffer descriptor was rejected.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FbError {
    /// Address is not page-aligned.
    UnalignedAddress,
    /// Width or height is zero.
    ZeroDimension,
    /// `bpp` is not a supported value.
    UnsupportedBpp,
    /// `pitch` is smaller than `width * bytes_per_pixel`.
    PitchTooSmall,
    /// The framebuffer size or end address overflowed `u64`.
    SizeOverflow,
}

impl FbError {
    /// Stable numeric code for serial logging.
    pub const fn code(self) -> u64 {
        match self {
            FbError::UnalignedAddress => 1,
            FbError::ZeroDimension => 2,
            FbError::UnsupportedBpp => 3,
            FbError::PitchTooSmall => 4,
            FbError::SizeOverflow => 5,
        }
    }
}

/// BPP values accepted for a linear framebuffer.
pub fn is_supported_bpp(bpp: u8) -> bool {
    matches!(bpp, 1 | 4 | 8 | 15 | 16 | 24 | 32)
}

/// Validate a framebuffer descriptor. Returns it unchanged on success, or the
/// first error.
pub fn validate(fb: &FramebufferInfo) -> Result<FramebufferInfo, FbError> {
    if fb.address % 4096 != 0 {
        return Err(FbError::UnalignedAddress);
    }
    if fb.width == 0 || fb.height == 0 {
        return Err(FbError::ZeroDimension);
    }
    if !is_supported_bpp(fb.bpp) {
        return Err(FbError::UnsupportedBpp);
    }
    let bytes_per_pixel = (fb.bpp as u32 + 7) / 8;
    let min_pitch = fb.width.checked_mul(bytes_per_pixel).ok_or(FbError::SizeOverflow)?;
    if fb.pitch < min_pitch {
        return Err(FbError::PitchTooSmall);
    }
    let total = (fb.pitch as u64)
        .checked_mul(fb.height as u64)
        .ok_or(FbError::SizeOverflow)?;
    if fb.address.checked_add(total).is_none() {
        return Err(FbError::SizeOverflow);
    }
    Ok(*fb)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fb() -> FramebufferInfo {
        FramebufferInfo { address: 0xFD00_0000, width: 1024, height: 768, bpp: 32, pitch: 4096 }
    }

    #[test]
    fn valid_descriptor_passes() {
        assert_eq!(validate(&fb()), Ok(fb()));
    }

    #[test]
    fn unaligned_address_is_rejected() {
        let mut f = fb();
        f.address = 0xFD00_0001;
        assert_eq!(validate(&f), Err(FbError::UnalignedAddress));
    }

    #[test]
    fn zero_dimension_is_rejected() {
        for mut f in [fb(), fb()] {
            f.width = 0;
            assert_eq!(validate(&f), Err(FbError::ZeroDimension));
            break;
        }
        let mut f = fb();
        f.height = 0;
        assert_eq!(validate(&f), Err(FbError::ZeroDimension));
    }

    #[test]
    fn unsupported_bpp_is_rejected() {
        let mut f = fb();
        f.bpp = 24; // supported
        assert!(validate(&f).is_ok());
        f.bpp = 7; // not supported
        assert_eq!(validate(&f), Err(FbError::UnsupportedBpp));
    }

    #[test]
    fn pitch_too_small_is_rejected() {
        let mut f = fb();
        f.pitch = 1024; // needs 1024 * 4 = 4096
        assert_eq!(validate(&f), Err(FbError::PitchTooSmall));
    }

    #[test]
    fn tight_pitch_is_accepted() {
        let mut f = fb();
        f.pitch = 4096;
        assert!(validate(&f).is_ok());
    }
}