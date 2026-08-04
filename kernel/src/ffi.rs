//! Foreign-function (C + assembly) bridge — Month 1 refinement.
//!
//! The kernel is Rust-first, but a guarded slice of low-level support is
//! written in freestanding C (`kernel/c/support.c`) and assembly
//! (`kernel/asm/cpu.s`) and linked in by `build.rs`. This module declares those
//! symbols and wraps them in safe Rust functions so the rest of the kernel
//! never touches raw `extern "C"` pointers directly.
//!
//! All call sites today are single-CPU, interrupt-free boot context; the C/asm
//! objects are position-dependent small-code-model and deliberately avoid
//! libgcc. Revisit after Month 2 once the memory manager and scheduler
//! introduce real concurrency (each wrapper's safety argument changes there).

extern "C" {
    fn lion_memset(dst: *mut u8, val: i32, len: usize) -> *mut u8;
    fn lion_memcpy(dst: *mut u8, src: *const u8, len: usize) -> *mut u8;
    fn lion_memcmp(a: *const u8, b: *const u8, len: usize) -> i32;
    fn lion_hlt() -> !;
    fn lion_cli();
    fn lion_sti();
    fn lion_pause();
    fn lion_read_cr3() -> u64;
    fn lion_cpuid(leaf: u32, subleaf: u32, out: *mut u32);
}

/// Fill `dst[..len]` with `val` (C `memset`).
///
/// # Safety
/// `dst` must point to `len` writable bytes for the lifetime of the call.
pub unsafe fn memset(dst: *mut u8, val: u8, len: usize) {
    // SAFETY: the caller upholds the slice/buffer contract above.
    unsafe { lion_memset(dst, val as i32, len) };
}

/// Copy `src[..len]` to `dst[..len]` (C `memcpy`; regions must not overlap).
///
/// # Safety
/// `dst` must be `len` writable bytes; `src` must be `len` readable bytes;
/// they must not overlap.
pub unsafe fn memcpy(dst: *mut u8, src: *const u8, len: usize) {
    // SAFETY: per above.
    unsafe { lion_memcpy(dst, src, len) };
}

/// Compare `a[..len]` and `b[..len]` (C `memcmp`).
///
/// # Safety
/// Both regions must be `len` readable bytes for the duration of the call.
pub unsafe fn memcmp(a: *const u8, b: *const u8, len: usize) -> i32 {
    // SAFETY: per above.
    unsafe { lion_memcmp(a, b, len) }
}

/// Halt the CPU. Never returns.
pub fn hlt() -> ! {
    // SAFETY: hlt with IF=0 parks the CPU; always safe in boot context.
    unsafe { lion_hlt() }
}

/// Clear interrupts.
pub fn cli() {
    // SAFETY: cli is always safe.
    unsafe { lion_cli() }
}

/// Set interrupts.
pub fn sti() {
    // SAFETY: sti is always safe.
    unsafe { lion_sti() }
}

/// Pause hint for spin loops.
pub fn pause() {
    // SAFETY: pause is always safe.
    unsafe { lion_pause() }
}

/// Current page-table root (`CR3`), page-aligned.
pub fn read_cr3() -> u64 {
    // SAFETY: mov cr3, rax is always safe to read.
    unsafe { lion_read_cr3() }
}

/// Execute `CPUID(leaf, subleaf)`, returning `eax, ebx, ecx, edx`.
pub fn cpuid(leaf: u32, subleaf: u32) -> [u32; 4] {
    let mut out = [0u32; 4];
    // SAFETY: `out.as_mut_ptr()` points to a valid 4-word writable buffer of the
    // correct lifetime for the synchronous call.
    unsafe { lion_cpuid(leaf, subleaf, out.as_mut_ptr()) };
    out
}

/// CPU vendor string (leaf 0), 12 bytes packed in `ebx, edx, ecx` order.
pub fn cpuid_vendor() -> [u8; 12] {
    let r = cpuid(0, 0);
    let mut vendor = [0u8; 12];
    vendor[0..4].copy_from_slice(&r[1].to_le_bytes()); // ebx
    vendor[4..8].copy_from_slice(&r[3].to_le_bytes()); // edx
    vendor[8..12].copy_from_slice(&r[2].to_le_bytes()); // ecx
    vendor
}