#![no_std]
#![no_main]

//! LionOS kernel boot entry point — Month 1 / Week 3.
//!
//! The bootloader crate (our boot provider) enters long mode, sets up initial
//! paging, reads the BIOS/UEFI memory map, and hands a `BootInfo` to `_start`.
//! We re-validate that memory map (defense in depth — see `memory.rs`) and print
//! a summary over serial before parking the CPU. The Week-1 placeholder marker
//! `LIONOS_INIT_OK` is preserved (CI greps for it); `LIONOS_HANDOFF_OK` appears
//! only once the handoff is consumed and validated.

use core::panic::PanicInfo;

use bootloader::bootinfo::{BootInfo, MemoryRegionType};

use lionos_kernel::ffi;
use lionos_kernel::memory::{self, Region, RegionKind};
use lionos_kernel::serial;

/// Boot marker printed to COM1 on success. CI greps for this exact string.
///
/// Overridable at build time via the `LIONOS_BOOT_MARKER` env var so CI can
/// run a real negative test (boot with a wrong marker -> assert it is absent).
fn boot_marker() -> &'static str {
    option_env!("LIONOS_BOOT_MARKER").unwrap_or("LIONOS_INIT_OK")
}

/// Map a bootloader `MemoryRegionType` onto our validator's coarser `RegionKind`.
fn to_kind(t: MemoryRegionType) -> RegionKind {
    use MemoryRegionType::*;
    match t {
        Usable => RegionKind::Usable,
        Reserved | InUse | Kernel | KernelStack | PageTable | Bootloader | FrameZero
        | BootInfo | Package | Empty => RegionKind::Reserved,
        AcpiReclaimable | AcpiNvs | BadMemory | NonExhaustive => RegionKind::NonUsable,
    }
}

/// Entry point called by the bootloader with a validated `BootInfo` in RDI.
#[no_mangle]
pub extern "C" fn _start(boot_info: &'static BootInfo) -> ! {
    serial::init();

    // Adapt the bootloader's frame-number regions into the raw triples our
    // validator consumes. The map is capacity-capped by the bootloader crate
    // (64), so a stack array is safe — no heap needed yet.
    let mut raw = [(0u64, 0u64, RegionKind::Usable); memory::MAX_REGIONS];
    let mut n = 0;
    for region in boot_info.memory_map.iter() {
        raw[n] = (
            region.range.start_frame_number,
            region.range.end_frame_number,
            to_kind(region.region_type),
        );
        n += 1;
    }

    let mut regions = [Region::empty(); memory::MAX_REGIONS];
    match memory::validate_regions(&raw[..n], &mut regions) {
        Ok(count) => {
            let usable = regions[..count]
                .iter()
                .filter(|r| r.kind == RegionKind::Usable)
                .count();
            serial::write_str("LIONOS_MEM_MAP regions=");
            serial::write_dec(count as u64);
            serial::write_str(" usable=");
            serial::write_dec(usable as u64);
            serial::write_str("\r\n");

            // Print the first few usable regions so CI/`xxd`-style debugging
            // can eyeball the addresses without needing `core::fmt`.
            for r in regions[..count].iter().filter(|r| r.kind == RegionKind::Usable).take(4) {
                serial::write_str("  usable 0x");
                serial::write_hex(r.start);
                serial::write_str(" len=");
                serial::write_dec(r.len);
                serial::write_str("\r\n");
            }

            serial::write_raw(b"LIONOS_HANDOFF_OK\r\n");
        }
        Err(e) => {
            serial::write_raw(b"LIONOS_MEM_MAP_ERROR code=");
            serial::write_dec(e.code());
            serial::write_str("\r\n");
        }
    }

    // --- Mixed-language (C + assembly) support check (Month 1 refinement) ---
    // Exercise the FFI bridge so a silent regression in the C/asm objects fails
    // loudly at boot instead of surfacing weeks later. Every printed value is
    // deterministic for a given VM, so CI can assert on it cheaply. This is the
    // first real consumer of the C (`c/support.c`) and assembly (`asm/cpu.s`)
    // objects linked in by `build.rs`.
    serial::write_str("\r\n[ffi] cr3=");
    serial::write_hex(ffi::read_cr3());
    serial::write_str(" cpuid=");
    serial::write_hex(ffi::cpuid(1, 0)[0] as u64);

    // C `lion_memset`: all eight bytes -> 0xAB.
    let mut buf = [0u8; 8];
    // SAFETY: `buf` is 8 writable bytes with the call's lifetime.
    unsafe { ffi::memset(buf.as_mut_ptr(), 0xAB, buf.len()) };
    serial::write_str(" memset=");
    serial::write_hex(u64::from_le_bytes(buf)); // expect 0xabababababababab

    // C `lion_memcpy` + `lion_memcmp` round-trip.
    let src = b"LION-FFI";
    let mut buf2 = [0u8; 8];
    // SAFETY: `buf2` is 8 writable bytes, `src` 8 readable bytes, disjoint.
    unsafe { ffi::memcpy(buf2.as_mut_ptr(), src.as_ptr(), src.len()) };
    serial::write_str(" memcpy_ok=");
    // SAFETY: both sides are 8 readable bytes for the call.
    let memcpy_ok: bool =
        unsafe { ffi::memcmp(buf2.as_ptr(), src.as_ptr(), src.len()) } == 0;
    serial::write_dec(memcpy_ok as u64);

    serial::write_str(" vendor=");
    for b in ffi::cpuid_vendor() {
        serial::write_byte(b);
    }
    serial::write_str("\r\n");

    // Week-1 CI checkpoint preserved regardless of the handoff result.
    serial::write_raw(boot_marker().as_bytes());
    serial::write_raw(b"\r\n");

    // Boot success. Park the CPU (the real kernel brings up interrupts in M2).
    ffi::hlt();
}

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    serial::init();
    serial::write_raw(b"PANIC\r\n");
    ffi::hlt();
}