//! CMOS RTC real-time clock driver — Month 3, drivers (extra).
//!
//! Reads the current date/time from the PC's CMOS clock (ports 0x70/0x71) via
//! the "update in progress" bit + BCD decode. QEMU keeps a real wall-clock, so
//! this returns an actual timestamp at boot (used for the `LIONOS_DRV_RTC`
//! marker).
//!
//! Values are BCD-coded (two nibbles per byte) unless the RTC status register
//! says otherwise; QEMU defaults to BCD. The `0x80` bit on port 0x70 disables
//! NMI while we program it — standard practice.

use crate::ffi;

const CMOS_ADDR: u16 = 0x70;
const CMOS_DATA: u16 = 0x71;
/// RTC status register A: bit 7 = update-in-progress.
const RTC_STAT_A: u8 = 0x0A;
/// RTC status register B: bit 2 = data mode (0 = BCD).
const RTC_STAT_B: u8 = 0x0B;

/// Convert a BCD byte to binary. `bcd = 0x24` → 24. Pure, host-tested.
pub fn bcd_to_bin(bcd: u8) -> u8 {
    (bcd & 0x0F) + ((bcd >> 4) * 10)
}

/// Read one CMOS register. Kernel target (port I/O).
///
/// # Safety
/// Port I/O; CMOS is always present on x86.
#[cfg(target_os = "none")]
unsafe fn read_cmos(reg: u8) -> u8 {
    // SAFETY: disable NMI + select register, then read the data port.
    unsafe { ffi::outb(CMOS_ADDR, reg | 0x80) };
    unsafe { ffi::inb(CMOS_DATA) }
}

/// Wait for the RTC to finish any in-progress update (so we read a consistent
/// snapshot). Kernel target.
#[cfg(target_os = "none")]
fn wait_update() {
    for _ in 0..4 {
        // SAFETY: CMOS read is always safe.
        if unsafe { read_cmos(RTC_STAT_A) } & 0x80 == 0 {
            break;
        }
        // SAFETY: io_wait gives the RTC a moment.
        ffi::nasm_io_wait();
    }
}

/// Read the current date/time. Returns `(year, month, day, hour, minute, second)`
/// in binary (non-BCD). `year` is the 2-digit CMOS year; callers add 2000.
/// Kernel target (port I/O).
#[cfg(target_os = "none")]
pub fn read_datetime() -> (u8, u8, u8, u8, u8, u8) {
    wait_update();
    // Read the six RTC registers (0x00..0x05: sec, min, hour, day, month, year).
    // SAFETY: CMOS reads are always safe.
    let sec = unsafe { read_cmos(0x00) };
    let min = unsafe { read_cmos(0x02) };
    let hour = unsafe { read_cmos(0x04) };
    let day = unsafe { read_cmos(0x07) };
    let mon = unsafe { read_cmos(0x08) };
    let year = unsafe { read_cmos(0x09) };
    let bcd_mode = unsafe { read_cmos(RTC_STAT_B) } & 0x04 == 0;
    if bcd_mode {
        (
            bcd_to_bin(year),
            bcd_to_bin(mon),
            bcd_to_bin(day),
            bcd_to_bin(hour),
            bcd_to_bin(min),
            bcd_to_bin(sec),
        )
    } else {
        (year, mon, day, hour, min, sec)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bcd_conversion() {
        assert_eq!(bcd_to_bin(0x00), 0);
        assert_eq!(bcd_to_bin(0x09), 9);
        assert_eq!(bcd_to_bin(0x10), 10);
        assert_eq!(bcd_to_bin(0x24), 24);
        assert_eq!(bcd_to_bin(0x59), 59);
    }
}
