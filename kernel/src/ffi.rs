//! Foreign-function (C + assembly) bridge — Month 1 refinement.
//!
//! The kernel is Rust-first, but a guarded slice of low-level support is
//! written in freestanding C (`kernel/c/support.c`, `kernel/c/fb.c`) and
//! assembly (`kernel/asm/cpu.s`) and linked in by `build.rs`. This module
//! declares those symbols and wraps them in safe Rust functions so the rest of
//! the kernel never touches raw `extern "C"` pointers directly.
//!
//! The call graph is deliberately layered so each half of the mixed-language
//! stack is exercised at boot: Rust calls C (`fb_*`, `memset`), C calls
//! assembly (`lion_cpu_leaf1_edx` → `lion_cpuid`), and Rust calls assembly
//! directly (`read_msr`, `read_rflags`, `xchg8`).
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

    // Assembly: CPU / MSR / port I/O / atomics (kernel/asm/cpu.s).
    fn lion_read_msr(msr: u32) -> u64;
    fn lion_write_msr(msr: u32, value: u64);
    fn lion_read_rflags() -> u64;
    fn lion_inb(port: u16) -> u8;
    fn lion_outb(port: u16, value: u8);
    fn lion_xchg8(ptr: *mut u8, value: u8) -> u8;

    // C: framebuffer drawing (kernel/c/fb.c).
    fn lion_fb_clear(
        base: *mut u8, width: u32, height: u32, pitch: u32, bpp: u32, rgb: u32,
    );
    fn lion_fb_fill_rect(
        base: *mut u8, width: u32, height: u32, pitch: u32, bpp: u32,
        x: u32, y: u32, rw: u32, rh: u32, rgb: u32,
    );
    fn lion_fb_hline(
        base: *mut u8, width: u32, height: u32, pitch: u32, bpp: u32,
        y: u32, x0: u32, x1: u32, rgb: u32,
    );
    fn lion_fb_pixel(
        base: *mut u8, width: u32, height: u32, pitch: u32, bpp: u32,
        x: u32, y: u32, rgb: u32,
    );

    // C calling assembly: kernel/c/support.c → asm/cpu.s `lion_cpuid`.
    fn lion_cpu_leaf1_edx() -> u32;
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

/// Read a model-specific register (asm `rdmsr`).
pub fn read_msr(msr: u32) -> u64 {
    // SAFETY: rdmsr on a valid, currently-readable MSR is safe; callers choose
    // well-known MSRs.
    unsafe { lion_read_msr(msr) }
}

/// Write a model-specific register (asm `wrmsr`).
///
/// # Safety
/// `msr` must be a writable, currently-allowed MSR; writing the wrong MSR can
/// crash the CPU.
pub unsafe fn write_msr(msr: u32, value: u64) {
    unsafe { lion_write_msr(msr, value) }
}

/// Snapshot of `RFLAGS` (bit 9 = interrupt flag).
pub fn read_rflags() -> u64 {
    // SAFETY: pushfq/popfq is always safe.
    unsafe { lion_read_rflags() }
}

/// Read one byte from an I/O port (asm `inb`).
///
/// # Safety
/// `port` must be a valid, currently-enabled I/O port.
pub unsafe fn inb(port: u16) -> u8 {
    unsafe { lion_inb(port) }
}

/// Write one byte to an I/O port (asm `outb`).
///
/// # Safety
/// `port` must be a valid I/O port.
pub unsafe fn outb(port: u16, value: u8) {
    unsafe { lion_outb(port, value) }
}

/// Atomic byte exchange (asm `xchg8`). Returns the previous byte at `ptr`.
/// A spinlock acquire is `prev = xchg8(&lock, 1)` — held iff `prev == 0`.
///
/// # Safety
/// `ptr` must point to one writable byte for the duration of the call.
pub unsafe fn xchg8(ptr: *mut u8, value: u8) -> u8 {
    unsafe { lion_xchg8(ptr, value) }
}

/// Clear the whole framebuffer to `rgb` (C `lion_fb_clear`).
///
/// # Safety
/// `base` must be the mapped framebuffer base; `width`/`height`/`pitch`/`bpp`
/// must describe it as validated by [`crate::framebuffer::validate`].
pub unsafe fn fb_clear(base: *mut u8, w: u32, h: u32, pitch: u32, bpp: u32, rgb: u32) {
    unsafe { lion_fb_clear(base, w, h, pitch, bpp, rgb) }
}

/// Fill a rectangle (C `lion_fb_fill_rect`). Bounds-clipped by the C code.
///
/// # Safety
/// Same contract as [`fb_clear`].
pub unsafe fn fb_fill_rect(
    base: *mut u8, w: u32, h: u32, pitch: u32, bpp: u32,
    x: u32, y: u32, rw: u32, rh: u32, rgb: u32,
) {
    unsafe { lion_fb_fill_rect(base, w, h, pitch, bpp, x, y, rw, rh, rgb) }
}

/// Draw a horizontal line (C `lion_fb_hline`). Bounds-clipped by the C code.
///
/// # Safety
/// Same contract as [`fb_clear`].
pub unsafe fn fb_hline(
    base: *mut u8, w: u32, h: u32, pitch: u32, bpp: u32,
    y: u32, x0: u32, x1: u32, rgb: u32,
) {
    unsafe { lion_fb_hline(base, w, h, pitch, bpp, y, x0, x1, rgb) }
}

/// Draw a single pixel (C `lion_fb_pixel`). Bounds-clipped by the C code.
///
/// # Safety
/// Same contract as [`fb_clear`].
pub unsafe fn fb_pixel(base: *mut u8, w: u32, h: u32, pitch: u32, bpp: u32, x: u32, y: u32, rgb: u32) {
    unsafe { lion_fb_pixel(base, w, h, pitch, bpp, x, y, rgb) }
}

/// CPUID leaf-1 feature bits (`edx`), computed by **C calling assembly**
/// (`support.c::lion_cpu_leaf1_edx` → `cpu.s::lion_cpuid`).
pub fn cpu_leaf1_edx() -> u32 {
    // SAFETY: lion_cpuid writes into a C-side stack buffer; the C wrapper owns
    // the whole interaction and returns a plain integer.
    unsafe { lion_cpu_leaf1_edx() }
}