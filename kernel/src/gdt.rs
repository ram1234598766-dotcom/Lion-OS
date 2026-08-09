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

    /// Ring-3 code descriptor: flat base/limit, present, DPL3, 64-bit.
    /// access = 0xFA (present | DPL3 | code/read); granularity = 0xA0 (L=1).
    pub const fn new_user_code() -> Self {
        SegmentDescriptor {
            limit_low: 0,
            base_low: 0,
            base_mid: 0,
            access: 0xFA,
            granularity: 0xA0,
            base_high: 0,
        }
    }

    /// Ring-3 data descriptor: present, DPL3, writable. access = 0xF2.
    pub const fn new_user_data() -> Self {
        SegmentDescriptor {
            limit_low: 0,
            base_low: 0,
            base_mid: 0,
            access: 0xF2,
            granularity: 0x00,
            base_high: 0,
        }
    }
}

/// GDT selector values (index * 8).
pub const KERNEL_CODE: u16 = 0x08;
pub const KERNEL_DATA: u16 = 0x10;

/// Selector for the 64-bit TSS (GDT index 3).
pub const KERNEL_TSS: u16 = 0x18;

/// Ring-3 (user) code selector (GDT index 5).
pub const USER_CODE: u16 = 0x28;
/// Ring-3 (user) data selector (GDT index 6).
pub const USER_DATA: u16 = 0x30;

/// Number of entries in the base kernel GDT (null + code + data).
pub const GDT_ENTRIES: usize = 3;

/// The 64-bit TSS structure the CPU uses for IST stack switching.
///
/// The important field for Month 2 is `ist` index 0, which the double-fault
/// gate routes through (the double-fault handler then runs on its own stack, so
/// a fault *inside* a handler no longer triple-faults into the same stack).
#[derive(Debug, Clone, Copy)]
#[repr(C)]
pub struct TaskStateSegment {
    reserved0: u32,
    rsp0: u64,
    rsp1: u64,
    rsp2: u64,
    reserved1: u64,
    /// Interrupt Stack Table — 7 entries; IST0 is used by the double-fault gate.
    ist: [u64; 7],
    reserved2: u64,
    reserved3: u16,
    io_map_base: u16,
}

impl TaskStateSegment {
    pub const fn new() -> Self {
        TaskStateSegment {
            reserved0: 0,
            rsp0: 0,
            rsp1: 0,
            rsp2: 0,
            reserved1: 0,
            ist: [0; 7],
            reserved2: 0,
            reserved3: 0,
            io_map_base: 0,
        }
    }

    /// Set RSP0 (stack used on a privilege transition INTO ring 0). For a
    /// single-ring kernel this is informational; the IST entry is the real use.
    pub fn set_rsp0(&mut self, addr: u64) {
        self.rsp0 = addr;
    }

    /// Set the IST0 stack top (used by the double-fault gate).
    pub fn set_ist0(&mut self, top: u64) {
        self.ist[0] = top;
    }
}

/// Build the 3-entry kernel GDT (null + code + data). Pure, `const`, host-tested
/// for the base descriptors. The kernel boot path uses a *superset* of this with
/// the TSS appended (see [`setup`]).
pub const fn build_gdt() -> [SegmentDescriptor; GDT_ENTRIES] {
    [
        SegmentDescriptor::null(),
        SegmentDescriptor::new_code64(),
        SegmentDescriptor::new_data64(),
    ]
}

/// A 64-bit TSS system descriptor (16 bytes = 2 GDT slots). Layout follows the
/// SDM's long-mode system descriptor: slots 0..2 hold the low 16 bytes (limit,
/// base[23:0], access, flags, base[31:24]); slots 3..5 hold base[63:32] +
/// reserved. Only used on the kernel target (built fresh into a writable page).
#[derive(Clone, Copy)]
#[repr(C)]
pub struct TssDescriptor {
    limit_low: u16,
    base_low: u16,
    base_mid: u8,
    access: u8,
    flags: u8,
    base_hi: u8,
    base_upper: u32,
    reserved: u32,
}
unsafe impl Sync for TssDescriptor {}

impl TssDescriptor {
    /// 64-bit "available" TSS: present, type 9 (0x89), base = `tss_base`.
    pub fn available(tss_base: u64) -> Self {
        let limit = core::mem::size_of::<TaskStateSegment>() - 1; // 103
        TssDescriptor {
            limit_low: limit as u16,
            base_low: tss_base as u16,
            base_mid: (tss_base >> 16) as u8,
            access: 0x89, // present | available-64-bit-TSS
            flags: 0x00,
            base_hi: (tss_base >> 24) as u8,
            base_upper: (tss_base >> 32) as u32,
            reserved: 0,
        }
    }
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

/// Number of GDT slots after `setup()` with the TSS + ring-3 descriptors:
/// [null, code64, data64, TSS-lo, TSS-hi, user-code, user-data] = 7 slots.
pub const GDT_TSS_ENTRIES: usize = 7;

/// Virtual base of the TSS frame mapped by [`setup`] (kernel target). Set once
/// at setup so later code can write TSS fields (e.g. RSP0 for ring-3 IRQs).
#[cfg(target_os = "none")]
static mut TSS_VBASE: u64 = 0;

/// Point the TSS's `RSP0` at `rsp0` (the top of a kernel stack). On a
/// ring-3 → ring-0 privilege transfer (a hardware IRQ while a user process is
/// running) the CPU loads RSP from RSP0, so it must be a valid kernel stack.
///
/// # Safety
/// Must run after [`setup`] (TSS_VBASE live) and before entering ring 3.
#[cfg(target_os = "none")]
pub unsafe fn set_rsp0(rsp0: u64) {
    // TSS lives at TSS_VBASE + 0x1000; `rsp0` is the u64 at offset 8.
    let base = unsafe { core::ptr::addr_of!(TSS_VBASE).read() };
    unsafe { *((base + 0x1000 + 8) as *mut u64) = rsp0 };
}

/// Kernel-only: install a full GDT with a 64-bit TSS (IST0) for the
/// double-fault handler, on pages we own (mapped writable via `paging`).
///
/// This is the Month-2 W1 "writable GDT page" finish: the bootloader's kernel
/// pages may be read-only (loading a segment writes the descriptor's *accessed*
/// bit), so the GDT/TSS must live on frames we mapped writable ourselves.
///
/// Layout of the mapped region (3 contiguous 4 KiB frames at a fresh virtual
/// base):
///   [base + 0x0000]  GDT        — 5 slots (null, code, data, TSS lo, TSS hi)
///   [base + 0x1000]  TSS        — 104-byte 64-bit TSS, IST0 set
///   [base + 0x2000]  double-fault stack (top = base + 0x3000)
///
/// # Safety
/// Must run after `paging::takeover` (so `paging::phys_offset` is live) and
/// after `frames::init_frames`. Single CPU, interrupts disabled.
#[cfg(target_os = "none")]
pub unsafe fn setup() {
    use crate::paging;

    let offset = paging::phys_offset();
    let idx = paging::find_free_top_index(offset).expect("no free region for GDT/TSS");
    let mut base = (idx as u64) << 39;
    if idx >= 256 {
        base |= 0xFFFF_0000_0000_0000;
    }
    // 3 frames: GDT, TSS, double-fault stack.
    // SAFETY: `base` is page-aligned, currently-unmapped; allocator has frames.
    unsafe { core::ptr::addr_of_mut!(TSS_VBASE).write(base) }
    paging::map_range(offset, base, 3).expect("map GDT/TSS/stack frames");

    let gdt_v = base as *mut u8;
    let tss_v = (base + 0x1000) as *mut u64;
    let ist_top = base + 0x3000; // top of the double-fault stack

    // 1. TSS: zero it, set IST0 to the top of the double-fault stack.
    // SAFETY: `tss_v` points to a mapped, writable frame.
    core::ptr::write_bytes(tss_v as *mut u8, 0, 4096);
    let tss = &mut *(tss_v as *mut TaskStateSegment);
    tss.set_ist0(ist_top);

    // 2. GDT: null, code64, data64, then the 2-slot TSS descriptor.
    let gdt = build_gdt();
    // SAFETY: `gdt_v` is mapped writable; copy 3 descriptors then 2 TSS slots.
    core::ptr::copy_nonoverlapping(gdt.as_ptr() as *const u8, gdt_v, 3 * 8);
    let tss_desc = TssDescriptor::available(base + 0x1000);
    // TSS descriptor occupies GDT slots 3 and 4 (16 bytes).
    core::ptr::copy_nonoverlapping(
        (&tss_desc as *const TssDescriptor) as *const u8,
        gdt_v.add(3 * 8),
        core::mem::size_of::<TssDescriptor>(),
    );
    // Ring-3 segments at slots 5 and 6 (user code, user data).
    let user_code = SegmentDescriptor::new_user_code();
    let user_data = SegmentDescriptor::new_user_data();
    core::ptr::copy_nonoverlapping(
        (&user_code as *const SegmentDescriptor) as *const u8,
        gdt_v.add(5 * 8),
        8,
    );
    core::ptr::copy_nonoverlapping(
        (&user_data as *const SegmentDescriptor) as *const u8,
        gdt_v.add(6 * 8),
        8,
    );

    // 3. Load GDT, reload data segments, then load the TSS (ltr).
    let limit = (GDT_TSS_ENTRIES * 8 - 1) as u16;
    let mut gdtr = [0u8; 10];
    gdtr[0] = limit as u8;
    gdtr[1] = (limit >> 8) as u8;
    gdtr[2..10].copy_from_slice(&base.to_le_bytes());
    asm!("lgdt [{}]", in(reg) gdtr.as_ptr(), options(nostack, preserves_flags));

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

    // ltr to KERNEL_TSS — makes the CPU mark the TSS busy and enables IST.
    // SAFETY: the TSS descriptor at slot 3 is valid and available.
    asm!("ltr {0:x}", in(reg) u16::from(KERNEL_TSS), options(nostack, preserves_flags));

    // Boot marker: GDT + TSS/IST installed (CI greps). IST0 = double-fault stack
    // top; reaching this line means lgdt + ltr both succeeded.
    crate::serial::write_str("LIONOS_GDT_OK ist0=");
    crate::serial::write_hex(ist_top);
    crate::serial::write_str("\r\n");
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

    #[test]
    fn user_selectors_are_standard() {
        assert_eq!(USER_CODE, 0x28);
        assert_eq!(USER_DATA, 0x30);
    }

    #[test]
    fn user_code_descriptor_flags() {
        let d = SegmentDescriptor::new_user_code();
        assert_eq!(d.access, 0xFA); // present | DPL3 | code/read
        assert_eq!(d.granularity, 0xA0); // L bit -> 64-bit
    }

    #[test]
    fn user_data_descriptor_flags() {
        let d = SegmentDescriptor::new_user_data();
        assert_eq!(d.access, 0xF2); // present | DPL3 | data/rw
    }

    #[test]
    fn user_descriptors_are_dpl3() {
        // DPL lives in access bits 6..5; DPL3 = 0x30.
        assert_eq!(SegmentDescriptor::new_user_code().access & 0x60, 0x60);
        assert_eq!(SegmentDescriptor::new_user_data().access & 0x60, 0x60);
    }

    #[test]
    fn full_gdt_has_seven_slots() {
        assert_eq!(GDT_TSS_ENTRIES, 7);
        // kernel selectors stay unchanged (ring 0).
        assert_eq!(KERNEL_CODE, 0x08);
        assert_eq!(KERNEL_DATA, 0x10);
    }
}