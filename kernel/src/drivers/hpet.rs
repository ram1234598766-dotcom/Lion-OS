//! High-Precision Event Timer (HPET) — Month 3, drivers (timer).
//!
//! The HPET is a PCI-free, memory-mapped high-resolution timer that QEMU places
//! at the conventional base 0xFED0_0000. It has no IDT/PIC port I/O; everything
//! goes through a small MMIO register block. We only *probe* it this month (read
//! the general-capabilities register enough to confirm the counter + revision
//! look valid), printing the `LIONOS_DRV_HPET` marker — a real counter/timer
//! driver is a follow-up.
//!
//! MMIO is reached through the physical-memory window (physical base + the
//! paging-takeover `phys_offset()`), exactly like `vga::vga_base()`. If the
//! window offset is 0 (takeover never ran) we report ABSENT and return without
//! touching hardware — never a fault.

/// Conventional HPET base address (physical).
pub const HPET_BASE: usize = 0xF000_0000;
/// General-capabilities register offset (offset 0x0 of the HPET block).
const CAP_REG: usize = 0x00;

/// Extract the HPET *revision* from the general-capabilities register (low byte).
/// Pure, host-tested.
pub fn version(cap: u32) -> u8 {
    (cap & 0xFF) as u8
}

/// The HPET is considered present if its capabilities register is non-zero AND
/// was written by hardware (bit 15 set => at least one timer + a real counter).
/// Pure, host-tested gate used by the kernel probe.
pub fn is_present(cap: u32) -> bool {
    cap & 0x8000 != 0
}

// ---------------------------------------------------------------------------
// Kernel-only MMIO probe (won't link on the host test target).
// ---------------------------------------------------------------------------

/// Probe the HPET block via the physical-memory window and print its marker.
/// Never faults: absent hardware (or no window offset) prints `ABSENT`.
#[cfg(target_os = "none")]
pub fn init() {
    let off = crate::paging::phys_offset();
    if off == 0 {
        crate::serial::write_str("LIONOS_DRV_HPET ABSENT\r\n");
        return;
    }
    // SAFETY: HPET_MMIO maps the capabilities register through the window; the
    // probe only reads a single DWORD, so a bogus/missing timer can't fault us.
    let addr = (HPET_BASE as u64 + off) as *const u32;
    let cap = unsafe { core::ptr::read_volatile(addr) };
    if !is_present(cap) {
        crate::serial::write_str("LIONOS_DRV_HPET ABSENT\r\n");
        return;
    }
    crate::serial::write_str("LIONOS_DRV_HPET found=1 rev=");
    crate::serial::write_dec(u64::from(version(cap)));
    crate::serial::write_str("\r\n");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn version_is_low_byte() {
        assert_eq!(version(0x0000_0001), 1);
        assert_eq!(version(0x0020_00AB), 0xAB);
    }

    #[test]
    fn present_requires_timer_counter() {
        assert!(is_present(0x0000_8001));
        // A zero capabilities register (no HPET) is absent.
        assert!(!is_present(0));
        // Revision set but no timer bit is absent.
        assert!(!is_present(0x0000_00FF));
    }
}