//! Global Descriptor Table — Month 2, kernel-core.
//!
//! bootloader 0.11 drops the kernel into long mode with a working flat segment
//! setup, but to own the CPU-core primitive explicitly (and to enable IST stack
//! switching later once a dedicated stack exists) we install our own minimal
//! GDT:
//!
//!   index  selector  meaning
//!      0       0x00  null
//!      1       0x08  kernel code (64-bit, ring 0)
//!      2       0x10  kernel data (ring 0)
//!
//! The 64-bit descriptors are base-0/flat — in long mode the upper bits of the
//! base and limit are ignored, so these descriptors are legal for any segment
//! currently in use. CS still points at the bootloader's selector (typically
//! 0x08), which is now *our* identical descriptor, so we reload only the data
//! segments and skip the fiddly far-jump needed to switch CS. A TSS+IST
//! descriptor is deferred to M2W2 (it needs a dedicated stack, which needs the
//! heap infra that lands in M2W3).
//!
//! The descriptor *layout* is host-testable (`cargo test`); the `lgdt`/segment
//! reload is gated to the freestanding kernel target via `target_os="none"`.

// `asm` is only used by `load()` (kernel target); `mem` is used by the pure
// helpers and host tests.
#[cfg(target_os = "none")]
use core::arch::asm;
use core::mem;

/// Raw 8-byte segment descriptor. `repr(C)`: the natural layout is already
/// exactly the SDM's (2+2+1+1+1+1 = 8, no padding), and un-packed lets tests
/// read fields without `E0793` (misaligned-reference) errors.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(C)]
pub struct SegmentDescriptor {
    limit_low: u16,
    base_low: u16,
    base_mid: u8,
    access: u8,
    granularity: u8,
    base_high: u8,
}

impl SegmentDescriptor {
    /// 64-bit code descriptor: flat base/limit, present, ring0.
    /// access = 0x9A (present | code/read); granularity byte = 0xA0 (L=1).
    pub const fn new_code64() -> Self {
        SegmentDescriptor {
            limit_low: 0,
            base_low: 0,
            base_mid: 0,
            access: 0x9A,
            granularity: 0xA0,
            base_high: 0,
        }
    }

    /// Data descriptor: present, ring0, writable. access = 0x92.
    pub const fn new_data64() -> Self {
        SegmentDescriptor {
            limit_low: 0,
            base_low: 0,
            base_mid: 0,
            access: 0x92,
            granularity: 0x00,
            base_high: 0,
        }
    }

    /// The all-zero null descriptor.
    pub const fn null() -> Self {
        SegmentDescriptor {
            limit_low: 0,
            base_low: 0,
            base_mid: 0,
            access: 0,
            granularity: 0,
            base_high: 0,
        }
    }
}

/// GDT selector values (index * 8).
pub const KERNEL_CODE: u16 = 0x08;
pub const KERNEL_DATA: u16 = 0x10;

/// Number of entries in the kernel GDT (null + code + data).
pub const GDT_ENTRIES: usize = 3;

/// Build the kernel GDT table. Pure, `const`, host-testable.
pub const fn build_gdt() -> [SegmentDescriptor; GDT_ENTRIES] {
    [
        SegmentDescriptor::null(),
        SegmentDescriptor::new_code64(),
        SegmentDescriptor::new_data64(),
    ]
}

/// GDTR pseudo-descriptor (limit + base) loaded by `lgdt`.
/// `packed`: `lgdt` reads limit at offset 0 (2 bytes) and base at offset 2
/// (8 bytes); `repr(C)` alone would pad base out to offset 8 and load garbage.
/// No `Debug` derive — `Debug` would borrow the packed u64 field (E0793).
#[derive(Clone, Copy)]
#[repr(C, packed)]
pub struct Gdtr {
    limit: u16,
    base: u64,
}

impl Gdtr {
    /// Unaligned-safe read of the limit field.
    pub fn limit(&self) -> u16 {
        unsafe { core::ptr::read_unaligned(core::ptr::addr_of!(self.limit)) }
    }

    /// Unaligned-safe read of the base field.
    pub fn base(&self) -> u64 {
        unsafe { core::ptr::read_unaligned(core::ptr::addr_of!(self.base)) }
    }
}

/// Build the GDTR for a table. `base` is the table's address.
pub fn gdtr_of(table: &[SegmentDescriptor; GDT_ENTRIES]) -> Gdtr {
    let limit = (mem::size_of::<[SegmentDescriptor; GDT_ENTRIES]>() - 1) as u16;
    Gdtr { limit, base: table.as_ptr() as u64 }
}

/// Install the kernel GDT (kernel target only). Safe to call once at boot.
#[cfg(target_os = "none")]
pub fn load() {
    // The GDT table MUST live in writable memory: loading a segment register
    // makes the CPU set the descriptor's *accessed* bit (a write to the table).
    // A `static mut` (zero-initialized) lands in `.bss`, not the read-only
    // `.rodata`, so that write is legal. `static mut` is fine here — boot-time,
    // single CPU, interrupts still disabled.
    static mut GTAB: [SegmentDescriptor; GDT_ENTRIES] = build_gdt();

    let base = core::ptr::addr_of!(GTAB) as u64;
    let limit = (core::mem::size_of::<[SegmentDescriptor; GDT_ENTRIES]>() - 1) as u16;

    // GDTR as an explicit 10-byte memory image: limit(2) then base(8).
    let mut gdtr = [0u8; 10];
    gdtr[0] = limit as u8;
    gdtr[1] = (limit >> 8) as u8;
    gdtr[2..10].copy_from_slice(&base.to_le_bytes());

    unsafe {
        // Load the new GDT.
        asm!("lgdt [{}]", in(reg) gdtr.as_ptr(), options(nostack, preserves_flags));
        // Reload data segments. CS/SS keep their bootloader selectors (now our
        // identical descriptors) — no far jump needed. KERNEL_DATA via a scratch
        // 16-bit register then the segment registers.
        let sel = u16::from(KERNEL_DATA);
        asm!(
            "mov {r:x}, {sel:x}",
            "mov ds, {r:x}",
            "mov es, {r:x}",
            "mov fs, {r:x}",
            "mov gs, {r:x}",
            r = out(reg) _,
            sel = in(reg) sel,
            options(nostack, preserves_flags)
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn descriptor_is_8_bytes() {
        assert_eq!(mem::size_of::<SegmentDescriptor>(), 8);
    }

    #[test]
    fn selectors_are_standard() {
        assert_eq!(KERNEL_CODE, 0x08);
        assert_eq!(KERNEL_DATA, 0x10);
    }

    #[test]
    fn null_descriptor_is_zero() {
        let g = build_gdt();
        let bytes = unsafe { &*(core::ptr::addr_of!(g[0]) as *const [u8; 8]) };
        assert_eq!(bytes, &[0; 8]);
    }

    #[test]
    fn code_descriptor_flags() {
        let g = build_gdt();
        assert_eq!(g[1].access, 0x9A);
        assert_eq!(g[1].granularity, 0xA0); // L bit set → 64-bit segment
    }

    #[test]
    fn data_descriptor_flags() {
        let g = build_gdt();
        assert_eq!(g[2].access, 0x92);
    }

    #[test]
    fn gdtr_limits_match_table() {
        let g = build_gdt();
        let gdtr = gdtr_of(&g);
        assert_eq!(gdtr.limit(), (8 * GDT_ENTRIES - 1) as u16);
        assert_eq!(gdtr.base(), g.as_ptr() as u64);
    }
}