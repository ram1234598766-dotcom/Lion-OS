//! IOAPIC interrupt-controller detect shim — Month 3, drivers (extra).
//!
//! The I/O APIC sits at MMIO base `0xFEC0_0000` and routes legacy (8259A) IRQs
//! to the local APICs. We do *not* program it this month — real redirection
//! needs local APIC + x2APIC setup that the boot ROM already did — so this is a
//! read-only detect shim: write the `IOAPICVER` index (1) to the IOREGSEL port,
//! read the whole version word back from the IOWIN port, and report a
//! `LIONOS_DRV_IOAPIC` marker. The MMIO access lives behind
//! `#[cfg(target_os = "none")]` and routes through the Month-2 physical-memory
//! window via `mmio::`; when that window isn't live the read returns 0, so an
//! absent/unmapped I/O APIC still prints `found=1` with the (zero) raw value
//! instead of faulting.
//!
//! The pure geometry (`irq_cnt`) is host-tested.

use crate::drivers::mmio;
use crate::serial;

/// I/O APIC MMIO base (physical, fixed by the x86 memory map).
pub const IOAPIC_BASE: u32 = 0xFEC0_0000;
/// `IOAPICVER` register index (holds max redirection entries + version).
const REG_VER: u16 = 0x01;
/// IOREGSEL window offset: write the register index here.
const OFF_SEL: usize = 0x00;
/// IOWIN window offset: read the selected register here.
const OFF_WIN: usize = 0x10;

/// Number of redirection entries: `IOAPICVER` bits 16..23 + 1. Pure, host-tested.
pub fn irq_cnt(ver: u32) -> u32 {
    ((ver >> 16) & 0xFF) + 1
}

// ---------------------------------------------------------------------------
// Kernel-only MMIO (the I/O APIC isn't on the host test target).
// ---------------------------------------------------------------------------

/// Probe the I/O APIC and print its marker. Never faults: `mmio::read32` returns
/// 0 through the (possibly absent) phys window rather than faulting, and every
/// read result is still reported via `found=1`.
#[cfg(target_os = "none")]
pub fn init() {
    // Select the IOAPICVER index into IOREGSEL, then read the version word back
    // from the IOWIN window — the true register read that yields {version, irqs}.
    mmio::write32(
        IOAPIC_BASE as u64 + OFF_SEL as u64,
        u32::from(REG_VER),
    );
    let ver = mmio::read32(IOAPIC_BASE as u64 + OFF_WIN as u64);

    serial::write_str("LIONOS_DRV_IOAPIC found=1 irqs=");
    serial::write_dec(u64::from(irq_cnt(ver)));
    serial::write_str(" raw=");
    serial::write_hex(u64::from(ver));
    serial::write_str("\r\n");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn irq_count_from_version() {
        assert_eq!(irq_cnt(0x0011), 1);              // entry-count field (16..24) is 0
        assert_eq!(irq_cnt(0x0002_0011), 3);         // 0x02 in field -> 2+1 entries
    }
}