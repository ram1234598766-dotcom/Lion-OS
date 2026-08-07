//! PC speaker (PIT channel 2) beeper — Month 3, drivers (extra).
//!
//! Drives the legacy speaker via the 8254 PIT channel 2 (port 0x42, mode word
//! 0xB6 on 0x43) + the speaker gate (port 0x61). QEMU models the speaker, so a
//! `beep` produces an actual tone in the audio (or at least the gate cycle runs
//! harmlessly). Pure, no global state.

use crate::ffi;

const PIT_CH2: u16 = 0x42;
const PIT_CTRL: u16 = 0x43;
const PIT_CLOCK: u32 = 1_193_182;
const SPEAKER_PORT: u16 = 0x61;

/// PIT channel-2 reload value for `hz`. Clamped to nonzero u16.
pub fn pit2_divisor(hz: u32) -> u16 {
    if hz == 0 {
        return u16::MAX;
    }
    (PIT_CLOCK / hz).clamp(1, u16::MAX as u32) as u16
}

/// Enable the speaker gate and program PIT channel 2 to `hz`. Kernel target.
///
/// # Safety
/// Port I/O on PC speaker + PIT.
#[cfg(target_os = "none")]
pub unsafe fn tone_on(hz: u32) {
    let div = pit2_divisor(hz);
    // SAFETY: program PIT channel 2 (mode 3 square wave), then set the speaker
    // gate bit (0x02) while keeping the existing byte.
    unsafe {
        ffi::outb(PIT_CTRL, 0xB6);
        ffi::outb(PIT_CH2, (div & 0xFF) as u8);
        ffi::outb(PIT_CH2, (div >> 8) as u8);
        let gate = ffi::inb(SPEAKER_PORT) | 0x03; // bits 0 (gate) + 1 (data)
        ffi::outb(SPEAKER_PORT, gate);
    }
}

/// Turn the speaker off (clear both gate bits). Kernel target.
///
/// # Safety
/// Port I/O on port 0x61.
#[cfg(target_os = "none")]
pub unsafe fn tone_off() {
    // SAFETY: clear gate (bit 0) + data (bit 1) on the speaker port.
    unsafe {
        let v = ffi::inb(SPEAKER_PORT) & !0x03;
        ffi::outb(SPEAKER_PORT, v);
    }
}

/// Beep at `hz` Hz for `ms` milliseconds (busy-wait; ~PIT-free delay loop).
/// Kernel target.
#[cfg(target_os = "none")]
pub fn beep(hz: u32, ms: u32) {
    // SAFETY: single CPU, boot path.
    unsafe { tone_on(hz) };
    // Approximate busy delay: a few PIT-pauseless iterations. Keep it short so
    // CI doesn't hang; ~1 ms per ~ K iterations of a volatile fence.
    let _anchor = ms;
    let spins = (ms * 80_000) as u64; // rough, tuned for QEMU TCG
    for _ in 0..spins {
        core::hint::spin_loop();
    }
    // SAFETY: turn the speaker back off.
    unsafe { tone_off() };
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn divisor_never_zero() {
        assert!(pit2_divisor(0) > 0);
        assert!(pit2_divisor(1000) > 0);
        assert_eq!(pit2_divisor(1000), 1193); // 1193182 / 1000
    }
}