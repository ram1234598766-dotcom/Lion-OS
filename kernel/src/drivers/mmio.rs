//! MMIO + port-I/O helpers shared by the MMIO-backed drivers (Month-3 follow-up).
//!
//! Everything routes through the physical-memory window the Month-2 paging
//! takeover recorded (`paging::phys_offset()`), exactly like `vga::vga_base()`.
//! Guarded so a driver whose device is absent can't fault: a window offset of 0
//! (takeover never ran) reads as 0 / no-ops a write.

use crate::paging;

/// Read one 32-bit MMIO register at physical address `phys` through the window.
/// Returns 0 when no physical window is live.
#[cfg(target_os = "none")]
pub fn read32(phys: u64) -> u32 {
    let off = paging::phys_offset();
    if off == 0 { return 0; }
    // SAFETY: the phys window maps all of physical memory; callers pass a known
    // device register/bar address.
    unsafe { core::ptr::read_volatile((phys + off) as *const u32) }
}

/// Write one 32-bit MMIO register at physical `phys` through the window.
#[cfg(target_os = "none")]
pub fn write32(phys: u64, value: u32) {
    let off = paging::phys_offset();
    if off == 0 { return; }
    // SAFETY: as above, for a writable device register.
    unsafe { core::ptr::write_volatile((phys + off) as *mut u32, value) }
}

/// Read an 8-bit I/O port (NASM `inb`).
#[cfg(target_os = "none")]
pub fn inb(port: u16) -> u8 {
    // SAFETY: caller picks a valid port.
    unsafe { crate::ffi::nasm_inb(port) }
}

/// Read a 16-bit I/O port (NASM `inw`).
#[cfg(target_os = "none")]
pub fn inw(port: u16) -> u16 {
    // SAFETY: caller picks a valid port.
    unsafe { crate::ffi::nasm_inw(port) }
}