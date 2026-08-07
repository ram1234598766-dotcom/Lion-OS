//! Interrupt controllers, timer, keyboard, and the deferred work queue —
//! Month 2, kernel-core.
//!
//! Brings up the full IRQ path behind `sti`:
//!   1. Remap both 8259 PICs so IRQ0..IRQ15 become IDT vectors 0x20..0x2F
//!      (the first 32 vectors are reserved for CPU exceptions).
//!   2. Program the PIT on channel 0 to a configurable HZ.
//!   3. Install timer (0x20) and keyboard (0x21) gates into the IDT.
//!   4. Enable interrupts.
//!
//! ISRs only do tiny, non-reentrant-safe work (increment counters, read the
//! scancode) and push a *deferred work item* for the main loop to drain — the
//! kernel never runs user-visible logic inside an ISR.
//!
//! Host tests exercise the pure helpers (PIT divisor, deferred queue) with the
//! type-DPI-free pieces; the ISRs + `init` are gated to the kernel target.

use core::sync::atomic::{AtomicBool, AtomicU64, Ordering};

use crate::ffi;

// ------------------------------ 8259 PIC ------------------------------

const PIC1_CMD: u16 = 0x20;
const PIC1_DATA: u16 = 0x21;
const PIC2_CMD: u16 = 0xA0;
const PIC2_DATA: u16 = 0xA1;

/// Small I/O delay between PIC programming bytes (ports are slow to settle).
fn io_wait() {
    unsafe { ffi::outb(0x80, 0) };
}

/// Remap the PICs and unmask only IRQ0 (timer) and IRQ1 (keyboard).
///
/// # Safety
/// Boot-time, single CPU, interrupts disabled. Touches the 8259's init ICWs.
pub fn remap() {
    /* ICW1: 0x11 = edge-triggered, cascade, need ICW4. */
    unsafe {
        ffi::outb(PIC1_CMD, 0x11);
        io_wait();
        ffi::outb(PIC2_CMD, 0x11);
        io_wait();
        /* ICW2: vector bases — master 0x20, slave 0x28. */
        ffi::outb(PIC1_DATA, 0x20);
        io_wait();
        ffi::outb(PIC2_DATA, 0x28);
        io_wait();
        /* ICW3: cascade wiring — master IR2 has slave; slave slave-id 2. */
        ffi::outb(PIC1_DATA, 0x04);
        io_wait();
        ffi::outb(PIC2_DATA, 0x02);
        io_wait();
        /* ICW4: 8086/88 mode. */
        ffi::outb(PIC1_DATA, 0x01);
        io_wait();
        ffi::outb(PIC2_DATA, 0x01);
        io_wait();
    }
    /* OCW1 mask: allow only timer+keyboard on the master; none on the slave. */
    unsafe {
        ffi::outb(PIC1_DATA, 0b1111_1100);
        ffi::outb(PIC2_DATA, 0xFF);
    }
    INTERRUPT_READY.store(true, Ordering::SeqCst);
}

/// Send End-Of-Interrupt to the PIC(s). `irq` is 0..=15.
#[cfg(target_os = "none")]
fn eoi(irq: u8) {
    if irq >= 8 {
        unsafe { ffi::outb(PIC2_CMD, 0x20) };
    }
    unsafe { ffi::outb(PIC1_CMD, 0x20) };
}

#[allow(dead_code)]
static INTERRUPT_READY: AtomicBool = AtomicBool::new(false);
/// True once both PICs are remapped (guards the ISRs' EOI path).
pub fn pic_ready() -> bool {
    INTERRUPT_READY.load(Ordering::SeqCst)
}

// ------------------------------ 8254 PIT ----------------------------------

const PIT_CH0: u16 = 0x40;
const PIT_CTRL: u16 = 0x43;
/// Nominal 8254 input clock.
const PIT_CLOCK: u64 = 1_193_182;

/// PIT reload value for `hz` cycles/sec (channel 0). Pure, host-testable.
/// Clamped to [1, u16::MAX] so 0/tiny HZ can't produce a 0 reload (which would
/// be a full-65536 the PIT reads as transparent-long reload).
pub fn pit_divisor(hz: u64) -> u16 {
    if hz == 0 {
        return u16::MAX;
    }
    let d = PIT_CLOCK / hz;
    d.clamp(1, u16::MAX as u64) as u16
}

/// Program the PIT channel 0 to `hz` in a square-wave (mode 3), LSB-first.
pub fn timer_init(hz: u64) {
    let div = pit_divisor(hz);
    unsafe {
        ffi::outb(PIT_CTRL, 0x36); // ch0, lobyte/hibyte, mode 3, binary
        ffi::outb(PIT_CH0, (div & 0xFF) as u8);
        ffi::outb(PIT_CH0, (div >> 8) as u8);
    }
    SER_HZ.store(hz, Ordering::Relaxed);
}

#[allow(dead_code)] // informational: records the programmed PIT rate
static SER_HZ: AtomicU64 = AtomicU64::new(0);

/// Total PIT ticks since boot.
pub fn ticks() -> u64 {
    TICKS.load(Ordering::SeqCst)
}

static TICKS: AtomicU64 = AtomicU64::new(0);

// --------------------------- PS/2 keyboard --------------------------------

/// Last raw scancode read from the 8042.
pub fn last_scancode() -> u8 {
    LAST_SCAN.load(Ordering::SeqCst) as u8
}

/// Number of keyboard IRQs received since boot.
pub fn key_count() -> u64 {
    KEY_COUNT.load(Ordering::SeqCst)
}

static LAST_SCAN: AtomicU64 = AtomicU64::new(0);
static KEY_COUNT: AtomicU64 = AtomicU64::new(0);

// ------------------------ deferred work queue -----------------------------

#[cfg(target_os = "none")]
const QUEUE_CAP: usize = 64;

#[cfg(target_os = "none")]
static Q_HEAD: core::sync::atomic::AtomicUsize = core::sync::atomic::AtomicUsize::new(0);
#[cfg(target_os = "none")]
static Q_TAIL: core::sync::atomic::AtomicUsize = core::sync::atomic::AtomicUsize::new(0);
#[cfg(target_os = "none")]
static Q_LOCK: AtomicBool = AtomicBool::new(false);
#[cfg(target_os = "none")]
static mut QUEUE: [Option<fn()>; QUEUE_CAP] = [None; QUEUE_CAP];

/// Try to enqueue work from an ISR context. Returns false if the queue is full
/// (work is dropped, not blocked — an ISR must never spin).
#[cfg(target_os = "none")]
pub fn enqueue(item: fn()) -> bool {
    // Short spinlock: single CPU, ISR-enqueue vs main-loop-drain handshake.
    while Q_LOCK.compare_exchange(false, true, Ordering::AcqRel, Ordering::Relaxed).is_err() {}
    let accepted = unsafe {
        let tail = Q_TAIL.load(Ordering::Relaxed);
        let head = Q_HEAD.load(Ordering::Relaxed);
        let len = (QUEUE_CAP + tail - head) % QUEUE_CAP;
        if len < QUEUE_CAP - 1 {
            QUEUE[tail] = Some(item);
            Q_TAIL.store((tail + 1) % QUEUE_CAP, Ordering::Relaxed);
            true
        } else {
            false
        }
    };
    Q_LOCK.store(false, Ordering::Release);
    accepted
}

/// Drain the whole queue from the main loop (never from an ISR).
#[cfg(target_os = "none")]
pub fn run_deferred() {
    loop {
        while Q_LOCK.compare_exchange(false, true, Ordering::AcqRel, Ordering::Relaxed).is_err() {}
        let item = unsafe {
            let head = Q_HEAD.load(Ordering::Relaxed);
            let tail = Q_TAIL.load(Ordering::Relaxed);
            if head != tail {
                let it = QUEUE[head].take();
                Q_HEAD.store((head + 1) % QUEUE_CAP, Ordering::Relaxed);
                it
            } else {
                None
            }
        };
        Q_LOCK.store(false, Ordering::Release);
        match item {
            Some(f) => f(),
            None => break,
        }
    }
}

// ---------------------------------------------------------------------------
// ISR handlers (kernel target only): record state, then defer/sign. They must
// never run unbounded logic. The `extern "x86-interrupt"` ABI does the
// save/restore + iretq.
// ---------------------------------------------------------------------------

#[cfg(target_os = "none")]
extern "x86-interrupt" fn timer_isr(_: crate::idt::InterruptStackFrame) {
    TICKS.fetch_add(1, Ordering::SeqCst);
    eoi(0);
}

#[cfg(target_os = "none")]
extern "x86-interrupt" fn keyboard_isr(_frame: crate::idt::InterruptStackFrame) {
    // 8042 data register (raw scancode). Read clears the "data ready" bit.
    let sc = unsafe { ffi::inb(0x60) };
    LAST_SCAN.store(u64::from(sc), Ordering::SeqCst);
    KEY_COUNT.fetch_add(1, Ordering::SeqCst);
    eoi(1);
}

#[cfg(target_os = "none")]
extern "x86-interrupt" fn mouse_isr(_frame: crate::idt::InterruptStackFrame) {
    // 8042 data port holds the next PS/2 mouse byte; feed the packet decoder.
    let raw = unsafe { ffi::inb(0x60) };
    crate::drivers::mouse::handle_byte(raw);
    eoi(12);
}

/// Full interrupt bring-up: GDT → IDT → IRQ gates → PIC remap → PIT → `sti`.
/// Must be called from boot context, once, before using the deferred queue.
#[cfg(target_os = "none")]
pub fn init() {
    // Custom GDT + TSS/IST, now that the page-table takeover lets us map a
    // writable GDT page. `setup()` installs a 64-bit TSS with IST0 = a dedicated
    // double-fault stack (frames mapped writable via paging), then loads GDT +
    // ltr. Must run BEFORE `idt::init` so the double-fault gate can select IST1.
    // SAFETY: called once, single CPU, interrupts disabled, after takeover.
    unsafe { crate::gdt::setup() };

    crate::idt::init();

    // Wire the IRQ vectors (after `lidt`, so in-place gates go live).
    crate::idt::install(0x20, timer_isr as *const () as u64, 0);
    crate::idt::install(0x21, keyboard_isr as *const () as u64, 0);
    // PS/2 mouse IRQ12 → vector 0x2C (installed before sti; armed by mouse::init).
    crate::idt::install(0x2C, mouse_isr as *const () as u64, 0);

    remap();
    // Unmask the slave PIC's IRQ4 (which is IRQ12) so mouse packets arrive.
    // SAFETY: slave PIC data port (0xA1); OCW1 clear bit 4.
    unsafe { ffi::outb(0xA1, 0xEF) };
    timer_init(100);
    crate::ffi::sti();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pit_divisor_for_integer_using_this_many_hz() {
        // 1193182 / 100 = 11931 (integer). The PIT uses exactly this reload.
        assert_eq!(pit_divisor(100), 11931);
    }

    #[test]
    fn pit_divisor_never_returns_zero() {
        assert!(pit_divisor(0) > 0);
        assert!(pit_divisor(1_000_000_000) > 0);
    }

    #[test]
    fn pit_divisor_is_clamped_large_hz() {
        // A very high rate falls back to the minimum reload (1) rather than 0.
        assert!(pit_divisor(10_000_000) >= 1);
    }

    #[test]
    fn pit_divisor_clamps_below_one_hertz() {
        // 1 Hz needs a ~1.19M reload, beyond the 16-bit PIT counter — clamped.
        assert_eq!(pit_divisor(1), u16::MAX);
    }
}