//! Foreign-function (C + assembly) bridge — Month 1 refinement.
//!
//! The kernel is Rust-first, but a guarded slice of low-level support is
//! written in freestanding C (`kernel/c/support.c`, `kernel/c/fb.c`,
//! `kernel/c/string_utils.c`) and assembly (`kernel/asm/cpu.s` in GAS,
//! `kernel/asm/port_io.asm` + `kernel/asm/cpu_utils.asm` in NASM) and linked in
//! by `build.rs`. This module declares those symbols and wraps them in safe Rust
//! functions so the rest of the kernel never touches raw `extern "C"` pointers.
//!
//! The call graph is deliberately layered so each half of the mixed-language
//! stack is exercised at boot: Rust calls C (`fb_*`, `memset`), C calls
//! assembly (`lion_cpu_leaf1_edx` → `lion_cpuid`), and Rust calls assembly
//! directly (`read_msr`, `read_rflags`, `xchg8`, and the NASM port-I/O layer).
//!
//! Both assembly syntaxes the plan calls for coexist here:
//!   · GAS  (`asm/cpu.s`) expose `lion_*` symbols;
//!   · NASM (`asm/port_io.asm`, `asm/cpu_utils.asm`) expose the bare
//!     `outb`/`inb`/…/`read_msr`/`cpuid_query` names, bound below via
//!     `#[link_name]` to Rust names suffixed `_nasm`.
//! The boot smoke calls both so a symbol-name or ABI regression in either
//! assembler's output fails loudly.
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
    fn lion_write_cr3(root: u64);
    fn lion_read_cr4() -> u64;
    fn lion_write_cr4(v: u64);
    fn lion_invlpg(addr: u64);
    fn lion_cpuid(leaf: u32, subleaf: u32, out: *mut u32);

    // Assembly: CPU / MSR / port I/O / atomics (kernel/asm/cpu.s).
    fn lion_read_msr(msr: u32) -> u64;
    fn lion_write_msr(msr: u32, value: u64);
    fn lion_read_rflags() -> u64;
    // Month 4: ring-3 descent (iretq to a {RIP,CS,RFLAGS,RSP,SS} frame).
    fn lion_usermode_go(rip: u64, rsp: u64, cs: u64, ss: u64, rflags: u64);
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

    // ── NASM layer (kernel/asm/port_io.asm, cpu_utils.asm) ───────────────
    // Month-1 plan language lay: NASM for low-level port-I/O + CPU utils.
    // Symbol names (outb/inb/…) come from the NASM files; Rust names are
    // suffixed `_nasm` (via #[link_name]) so they don't collide with the GAS
    // `lion_*`/`inb`/`outb` wrappers above.
    #[link_name = "outb"]
    fn outb_nasm(port: u16, value: u8);
    #[link_name = "inb"]
    fn inb_nasm(port: u16) -> u8;
    #[link_name = "outw"]
    fn outw_nasm(port: u16, value: u16);
    #[link_name = "inw"]
    fn inw_nasm(port: u16) -> u16;
    #[link_name = "io_wait"]
    fn io_wait_nasm();
    #[link_name = "cpu_pause"]
    fn cpu_pause_nasm();
    #[link_name = "cpu_halt"]
    fn cpu_halt_nasm();
    #[link_name = "enable_interrupts"]
    fn enable_interrupts_nasm();
    #[link_name = "disable_interrupts"]
    fn disable_interrupts_nasm();
    #[link_name = "read_msr"]
    fn read_msr_nasm(msr: u32) -> u64;
    #[link_name = "write_msr"]
    fn write_msr_nasm(msr: u32, value: u64);
    #[link_name = "cpuid_query"]
    fn cpuid_query_nasm(
        leaf: u32, subleaf: u32, eax: *mut u32, ebx: *mut u32, ecx: *mut u32, edx: *mut u32,
    );

    // ── C string helpers (kernel/c/string_utils.c) ───────────────────────
    fn lionos_strlen(s: *const u8) -> usize;
    fn lionos_strcmp(a: *const u8, b: *const u8) -> core::ffi::c_int;
    fn lionos_strcpy(dst: *mut u8, src: *const u8) -> *mut u8;
    fn lionos_itoa_hex(val: u64, buf: *mut u8);

    // C memmove (kernel/c/support.c) — rounds out memset/memcpy/memcmp.
    fn lion_memmove(dst: *mut u8, src: *const u8, len: usize) -> *mut u8;
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

/// Load a new page-table root into `CR3`. `root` is a PHYSICAL frame address
/// (CR3 takes physical, not virtual). Switching flushes the whole TLB.
///
/// # Safety
/// `root` must be the physical address of a valid, present PML4 (typically one
/// we just built and populated).
pub unsafe fn write_cr3(root: u64) {
    // SAFETY: caller upholds the physical-PML4 contract above.
    unsafe { lion_write_cr3(root) }
}

/// Current `CR4` (SMEP = bit 20, SMAP = bit 21, PAE/PGE/etc).
pub fn read_cr4() -> u64 {
    // SAFETY: mov cr4, rax is always safe to read.
    unsafe { lion_read_cr4() }
}

/// Load a new `CR4` value.
///
/// # Safety
/// The value must leave the CPU in a consistent state (e.g. keep PAE/PGE set);
/// enabling SMEP/SMAP changes the supervisor↔user page rules.
pub unsafe fn write_cr4(v: u64) {
    unsafe { lion_write_cr4(v) }
}

/// Invalidate the TLB entries for the single page at `addr` (after a map/unmap
/// while CR3 stays loaded).
///
/// # Safety
/// `addr` must be a canonical virtual address.
pub unsafe fn invlpg(addr: u64) {
    // SAFETY: invlpg accepts any canonical address.
    unsafe { lion_invlpg(addr) }
}

/// Execute `CPUID(leaf, subleaf)`, returning `[eax, ebx, ecx, edx]`.
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

/// Descend from ring 0 to ring 3: build a iretq frame with the given user
/// `rip`/`rsp` and RPL-3 `cs`/`ss`, and switch to user mode. Does not return
/// (control passes to the ring-3 `rip`).
///
/// # Safety
/// `rip`/`rsp` must point into user-accessible (U/S) mapped pages; `cs`/`ss`
/// must be the ring-3 user selectors (usually `USER_CODE | 3`). Called once
/// with interrupts disabled.
pub unsafe fn usermode_go(rip: u64, rsp: u64, cs: u64, ss: u64, rflags: u64) {
    unsafe { lion_usermode_go(rip, rsp, cs, ss, rflags) }
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
/// (`support.c::lion_cpu_edx` → `cpu.s::lion_cpuid`).
pub fn cpu_leaf1_edx() -> u32 {
    // SAFETY: lion_cpuid writes into a C-side stack buffer; the C wrapper owns
    // the whole interaction and returns a plain integer.
    unsafe { lion_cpu_leaf1_edx() }
}

// ---------------------------------------------------------------------------
// NASM-layer safe wrappers (Month-1 plan language lay).
//
// These call the NASM port_io/cpu_utils objects (kernel/asm/port_io.asm,
// cpu_utils.asm). They share the GAS `lion_*` wrappers above; the boot smoke
// calls both so a regression in either assembler's output fails loudly.
// ---------------------------------------------------------------------------

/// Write a byte to an I/O port (NASM `outb`).
///
/// # Safety
/// `port` must be a valid, currently-enabled port.
pub unsafe fn nasm_outb(port: u16, value: u8) {
    // SAFETY: forwarded from the caller's port contract.
    unsafe { outb_nasm(port, value) }
}

/// Read a byte from an I/O port (NASM `inb`).
///
/// # Safety
/// `port` must be a valid port.
pub unsafe fn nasm_inb(port: u16) -> u8 {
    // SAFETY: forwarded from the caller's port contract.
    unsafe { inb_nasm(port) }
}

/// Write a 16-bit word to an I/O port (NASM `outw`).
pub unsafe fn nasm_outw(port: u16, value: u16) {
    unsafe { outw_nasm(port, value) }
}

/// Read a 16-bit word from an I/O port (NASM `inw`).
pub unsafe fn nasm_inw(port: u16) -> u16 {
    unsafe { inw_nasm(port) }
}

/// I/O delay (~1-2 µs) by writing to the POST port 0x80 (NASM `io_wait`).
pub fn nasm_io_wait() {
    // SAFETY: writing to POST port 0x80 is always safe.
    unsafe { io_wait_nasm() }
}

/// x86 PAUSE hint for spin loops (NASM `cpu_pause`).
pub fn nasm_cpu_pause() {
    // SAFETY: pause is always safe.
    unsafe { cpu_pause_nasm() }
}

/// Halt until the next interrupt (NASM `cpu_halt`). Requires IF=1 + IDT.
pub fn nasm_cpu_halt() {
    // SAFETY: hlt parks the CPU until the next interrupt; needs a loaded IDT.
    unsafe { cpu_halt_nasm() }
}

/// Enable interrupts (NASM `enable_interrupts`, sti).
pub fn nasm_enable_interrupts() {
    // SAFETY: sti is always safe.
    unsafe { enable_interrupts_nasm() }
}

/// Disable interrupts (NASM `disable_interrupts`, cli).
pub fn nasm_disable_interrupts() {
    // SAFETY: cli is always safe.
    unsafe { disable_interrupts_nasm() }
}

/// Read a model-specific register (NASM `read_msr`, rdmsr).
pub fn nasm_read_msr(msr: u32) -> u64 {
    // SAFETY: rdmsr on a valid, readable MSR is safe; callers choose known MSRs.
    unsafe { read_msr_nasm(msr) }
}

/// Write a model-specific register (NASM `write_msr`, wrmsr).
///
/// # Safety
/// `msr` must be a writable, currently-allowed MSR; writing the wrong MSR can
/// crash the CPU.
pub unsafe fn nasm_write_msr(msr: u32, value: u64) {
    unsafe { write_msr_nasm(msr, value) }
}

/// Execute `CPUID(leaf, subleaf)` via the NASM `cpuid_query`, returning
/// `[eax, ebx, ecx, edx]`. The NASM routine parks pointer bases in r10/r11
/// before `cpuid` (the EDX/ECX-clobber fix), so it is safe from Rust.
pub fn nasm_cpuid_query(leaf: u32, subleaf: u32) -> [u32; 4] {
    let mut out = [0u32; 4];
    // SAFETY: out points to a valid 4-word writable buffer with the call's
    // lifetime; the NASM routine writes exactly out[0..4].
    unsafe {
        cpuid_query_nasm(
            leaf,
            subleaf,
            out.as_mut_ptr().add(0),
            out.as_mut_ptr().add(1),
            out.as_mut_ptr().add(2),
            out.as_mut_ptr().add(3),
        )
    };
    out
}

/// Length of a NUL-terminated C string (C `lionos_strlen`).
///
/// # Safety
/// `s` must point to a NUL-terminated readable byte string.
pub unsafe fn strlen_c(s: *const u8) -> usize {
    // SAFETY: forwarded from the caller's string contract.
    unsafe { lionos_strlen(s) }
}

/// Compare two NUL-terminated C strings (C `lionos_strcmp`): 0 if equal.
///
/// # Safety
/// `a`/`b` must point to NUL-terminated readable strings.
pub unsafe fn strcmp_c(a: *const u8, b: *const u8) -> i32 {
    // SAFETY: forwarded from the caller's string contract.
    unsafe { lionos_strcmp(a, b) }
}

/// Copy the NUL-terminated string `src` into `dst` (C `lionos_strcpy`).
/// `dst` must be large enough — no bounds check.
///
/// # Safety
/// `dst` must be writable for the length of `src` plus the NUL.
pub unsafe fn strcpy_c(dst: *mut u8, src: *const u8) -> *mut u8 {
    // SAFETY: forwarded from the caller's buffer contract.
    unsafe { lionos_strcpy(dst, src) }
}

/// Format `val` as a 19-byte `0x` hex string into `buf` (C `lionos_itoa_hex`).
///
/// # Safety
/// `buf` must point to at least 19 writable bytes.
pub unsafe fn itoa_hex(val: u64, buf: *mut u8) {
    // SAFETY: forwarded from the caller's buffer contract.
    unsafe { lionos_itoa_hex(val, buf) }
}

/// C `memmove` (overlap-safe) — completes the C helper set (memset/memcpy/memcmp/memmove).
///
/// # Safety
/// `dst` must be `len` writable bytes; `src` must be `len` readable bytes.
pub unsafe fn memmove(dst: *mut u8, src: *const u8, len: usize) -> *mut u8 {
    // SAFETY: forwarded from the caller's buffer contract.
    unsafe { lion_memmove(dst, src, len) }
}

// =============================================================================
// C++17 + Zig (Month-3 language lay ILLUSTRATIONS). These are the two added
// language families in the kernel, linked by `build.rs` into `liblionos_ffi.a`
// for the kernel target. They return deterministic magic constants so a boot-
// smoke marker proves both objects actually linked and ran.
// =============================================================================

extern "C" {
    fn lionos_cpp_magic() -> u32;
    fn lionos_zig_magic() -> u32;
    fn lionos_zig_table_magic() -> u32;
}

/// C++17 `lionos_cpp_magic` (kernel/cpp/lionos_cpp.cpp) → 0xC0FFEE0C.
pub fn cpp_magic() -> u32 {
    // SAFETY: pure register-return extern; no state, no arguments.
    unsafe { lionos_cpp_magic() }
}

/// Zig `lionos_zig_magic` (kernel/zig/lionos_zig.zig) → 0x00000944.
pub fn zig_magic() -> u32 {
    // SAFETY: pure register-return extern call; no state.
    unsafe { lionos_zig_magic() }
}

/// Zig `lionos_zig_table_magic` — the comptime-validated hardware table's magic.
pub fn zig_table_magic() -> u32 {
    // SAFETY: pure register-return extern call; no state.
    unsafe { lionos_zig_table_magic() }
}