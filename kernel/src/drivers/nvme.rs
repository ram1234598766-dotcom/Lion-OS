//! NVMe (NVM Express) block-controller detection — Month 3, drivers (extra).
//!
//! NVMe is the modern PCIe SAN; on the PCI config-space class/prog-IF scale it is
//! mass-storage (class `0x01`) with programming interface "NVM Express" (subclass
//! `0x08`, formerly `NVMHCI`). QEMU typically has none attached, so this driver
//! is a detect-only PCI scan: if the config space yields a device of that
//! class/subclass we report it, otherwise we print `LIONOS_DRV_NVME ABSENT`.
//!
//! The classify helper is pure, host-tested, and the actual bus scan is
//! kernel-target only, behind `#[cfg(target_os = "none")]` — same rule as
//! `pci.rs`/`ide.rs`.

/// True if a PCI device's class/subclass identify an NVMe (NVM Express)
/// controller. Mass-storage controllers are class `0x01`; the non-volatile
/// memory ("NVM Express") programming interface is subclass `0x08`.
pub fn is_nvme(class: u8, subclass: u8) -> bool {
    class == 0x01 && subclass == 0x08
}

/// Probe PCI bus 0 for an NVMe controller and print the deterministic marker.
///
/// Boot-time, single CPU, after interrupts + heap are up. Never panics or
/// faults: an empty bus (no NVMe present) simply reports ABSENT.
#[cfg(target_os = "none")]
pub fn init() {
    // SAFETY: PCI config reads on present (bus, slot, func) are safe, and a
    // config read never faults even on absent devices (returns all-ones).
    let devs = crate::drivers::pci::probe_bus0();
    if let Some(d) = devs.into_iter().find(|d| is_nvme(d.class, d.subclass)) {
        crate::serial::write_str("LIONOS_DRV_NVME found=1 pci=");
        c_vendor_device(&d);
        crate::serial::write_str(" class=");
        crate::serial::write_hex(u64::from(d.class));
        crate::serial::write_str("/");
        crate::serial::write_hex(u64::from(d.subclass));
    } else {
        crate::serial::write_str("LIONOS_DRV_NVME ABSENT");
    }
    crate::serial::write_str("\r\n");
}

/// Print `vendor:device` as one 8-digit hex pair (`write_hex` has no `0x`).
#[cfg(target_os = "none")]
fn c_vendor_device(v: &crate::drivers::pci::PciDevice) {
    crate::serial::write_hex(u64::from(v.vendor) << 16 | u64::from(v.device));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn nvme_class_match() {
        assert!(is_nvme(1, 8));   // NVMe controller (NVMHCI)
        assert!(!is_nvme(1, 6));  // other mass-storage (SATA)
    }
}