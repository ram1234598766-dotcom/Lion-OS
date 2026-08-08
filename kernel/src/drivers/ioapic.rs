//! IOAPIC interrupt-controller detect shim — Month 3, drivers (extra).
//!
//! The I/O APIC sits at MMIO base `0xFEC0_0000` and routes legacy (8259A) IRQs
//! to the local APICs. We do *not* program it this month — real redirection
//! needs local APIC + x2APIC setup that the boot ROM already did — so this is a
//! read-only detect shim: write the `IOAPICVER` index (1) to the IOREGSEL port,
//! read the version word back from the IOWIN port, and report a
//! `LIONOS_DRV_IOAPIC` found/absent marker. Absent or unmapped, it prints
//! `ABSENT` and returns — never a fault (see `drivers/mod.rs`).
//!
//! The pure geometry (`irq_cnt`) is host-tested; all MMIO access lives behind
//! `#[cfg(target_os = "none")]` and is gated on the physical-memory window from
//! Month-2 paging takeover, exactly like `rtc.rs`/`ide.rs`.

use crate::paging;
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

/// Read an I/O APIC register: write its index to IOREGSEL, then read IOWIN.
///
/// # Safety
/// Raw MMIO; must only select a register QEMU's I/O APIC actually exposes.
#[cfg(target_os = "none")]
unsafe fn read_ver() -> u32 {
    let base = (IOAPIC_BASE as u64 + paging::phys_offset()) as usize;
    // SAFETY: 4-byte MMIO writes/reads at the two window offsets.
    unsafe {
        (base as *mut u32).wrapping_add(OFF_SEL).write_volatile(u32::from(REG_VER));
    }
    // SAFETY: read the selected register back from the IOWIN port.
    unsafe { (base as *const u32).wrapping_add(OFF_WIN).read_volatile() }
}

/// Probe the I/O APIC and print its marker. Never faults.
#[cfg(target_os = "none")]
pub fn init() {
    // Month-2 paging maps physical memory into a high window; without it we have
    // no way to reach 0xFEC0_0000 — report absent and return.
    let off = paging::phys_offset();
    if off == 0 {
        serial::write_str("LIONOS_DRV_IOAPIC ABSENT\r\n");
        return;
    }
    // SAFETY: guarded by the phys-window absence check above.
    let ver = unsafe { read_ver() };
    serial::write_str("LIONOS_DRV_IOAPIC found=1 irqs=");
    serial::write_dec(u64::from(irq_cnt(ver)));
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