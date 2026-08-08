//! Scheduler — Month 3, kernel-core. Cooperative `yield` first (proven, tested),
//! then PIT-hooked preemptive round-robin reusing the same NASM context switch.
//!
//! Context switch primitives: `kernel/asm/switch.asm` exports `context_switch`,
//! a C-ABI callee-saved save/restore that stores the running task's rsp into
//! `*prev_sp` and loads `next_sp`, popping the callee-saved set. A *fresh* task's
//! saved rsp points at a synthetic frame: six zero qwords (the pops restore
//! r15..rbx = 0) followed by the return address `task_entry`, which springs the
//! task's closure.
//!
//! Ring model (single, coherent — this is the whole design):
//!   `tasks[0..real_tasks]` are real tasks; `tasks[real_tasks]` is the IDLE slot,
//!   which stands for the boot context. **The idle slot is identified by INDEX**
//!   (`idx >= real_tasks`), never by a sentinel id, so `run_pending_switch` maps
//!   it to the `IDLE_RSP` static on both sides. Because IDLE is a first-class ring
//!   member, rotation always returns control to the boot loop (it re-acquires).
//!
//! Kernel-host split: pure selection (`next_index`) is architecture-free and
//! host-tested; the register switch + stack setup + ISR handoff are
//! `#[cfg(target_os = "none")]`.

use alloc::boxed::Box;
use alloc::vec::Vec;

pub const TASKS_CAP: usize = 4;
/// Per-task stack size (bytes), allocated on the kernel heap (frame-backed and
/// writable), NOT a `.bss` static — see `alloc_task_stack` note.
pub const STACK_SIZE: usize = 8192;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum TaskState {
    Ready,
    Running,
    Blocked,
}

/// One schedulable unit. `saved_rsp` is valid only on the kernel target (set by
/// `context_switch`); the idle slot's live rsp lives in `IDLE_RSP` instead.
#[derive(Clone, Copy, Debug)]
pub struct Pcb {
    pub state: TaskState,
    pub saved_rsp: *mut u64,
}

impl Pcb {
    pub fn new() -> Self {
        Self { state: TaskState::Ready, saved_rsp: core::ptr::null_mut() }
    }
}

/// Pure, architecture-free scheduler state. Host-tested.
pub struct Scheduler {
    /// Real tasks + the trailing IDLE slot (index `real_tasks`).
    pub tasks: Vec<Pcb>,
    /// Ring index of the slot the scheduler would switch TO next (or is about
    /// to run next). Starts at `real_tasks` (the idle/boot slot).
    pub current: usize,
    pub switches: u64,
    pub started: bool,
    /// Ask the main loop to perform the register switch (set by tick/yield).
    pub switch_pending: bool,
    pub real_tasks: usize,
}

impl Scheduler {
    pub fn new() -> Self {
        Self {
            tasks: Vec::new(), current: 0, switches: 0, started: false,
            switch_pending: false, real_tasks: 0,
        }
    }

    /// True for the idle/boot ring slot (index >= real_tasks).
    pub fn is_idle(self: &Self, idx: usize) -> bool {
        idx >= self.real_tasks
    }

    /// Next ready ring slot != current. Pure and host-testable.
    pub fn next_index(tasks: &[Pcb], current: usize) -> Option<usize> {
        if tasks.is_empty() { return None; }
        for step in 1..=tasks.len() {
            let i = (current + step) % tasks.len();
            if tasks[i].state == TaskState::Ready || tasks[i].state == TaskState::Running {
                return Some(i);
            }
        }
        None
    }

    pub fn push_task(&mut self, pcb: Pcb) {
        self.tasks.push(pcb);
    }

    /// Cooperative yield / tick: advance RR selection + flag a switch. Pure and
    /// safe from ISR context (no register/stack surgery here).
    pub fn tick(&mut self) -> bool {
        if !self.started { return false; }
        match Self::next_index(&self.tasks, self.current) {
            Some(i) if i != self.current => { self.current = i; self.switch_pending = true; true }
            _ => false,
        }
    }
}

impl core::fmt::Debug for Scheduler {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        write!(f, "Scheduler{{ tasks={}, current={}, switches={}, started={}, real={} }}",
            self.tasks.len(), self.current, self.switches, self.started, self.real_tasks)
    }
}

// ============================================================
// Kernel target (register switch + stack setup + ISR handoff)
// ============================================================

extern "C" {
    fn context_switch(prev_rsp_slot: *mut *mut u64, next_rsp: *mut u64);
}

/// The single global scheduler, held on the kernel HEAP (frame-backed, mapped
/// read-write). Only a zero-init raw pointer is a static, so it lands in `.bss`
/// (writable) — no scheduler state lives in the read-only `.data` mapping.
#[cfg(target_os = "none")]
static mut SCHED_PTR: *mut Scheduler = core::ptr::null_mut();

#[cfg(target_os = "none")]
fn sched_mut() -> &'static mut Scheduler {
    // SAFETY: single-CPU boot; allocated once, never freed, before first use.
    unsafe {
        let slot = core::ptr::addr_of_mut!(SCHED_PTR);
        if (*slot).is_null() { *slot = Box::into_raw(Box::new(Scheduler::new())); }
        &mut **slot
    }
}

/// Ring index of the currently running slot (a real task or the idle boot slot).
/// Zero-init (→ `.bss`); set at runtime so it never lands in the read-only
/// `.data` section (a non-zero static initializer would #PF e=3 on write).
#[cfg(target_os = "none")]
static mut CURRENT_ID: usize = 0;
/// The idle/boot context's live rsp; swapped to/from by `run_pending_switch`.
#[cfg(target_os = "none")]
static mut IDLE_RSP: *mut u64 = core::ptr::null_mut();

/// The one task closure slot, so `task_entry` knows what to run.
#[cfg(target_os = "none")]
static mut TASK_FN: Option<fn()> = None;

/// Started flag for the timer ISR (atomic; never touches the scheduler static).
#[cfg(target_os = "none")]
static SCHED_ON: core::sync::atomic::AtomicBool = core::sync::atomic::AtomicBool::new(false);
/// PIT ticks pending, to be consumed as switches (the ISR only bumps this).
#[cfg(target_os = "none")]
static PIT_KICKS: core::sync::atomic::AtomicU64 = core::sync::atomic::AtomicU64::new(0);

/// The task's initial entry (the synthetic frame's return address). Runs the one
/// registered closure, then parks: timer-driven rotation.
#[cfg(target_os = "none")]
#[no_mangle]
pub extern "C" fn task_entry() -> ! {
    let f = unsafe { *core::ptr::addr_of!(TASK_FN) };
    if let Some(f) = f { f(); }
    // Park: consume PIT kicks and perform deferred switches. A busy `pause`
    // loop here (not `hlt`) — under the deferred-switch model a task must keep
    // pumping the ring or it stalls with no way back to the idle slot.
    loop {
        pump_ticks();
        run_pending_switch();
        crate::ffi::pause();
    }
}

/// Spawn a real task: heap-alloc a stack + synthetic frame and push its Pcb.
#[cfg(target_os = "none")]
pub fn spawn(f: fn()) {
    let s = sched_mut();
    unsafe { *core::ptr::addr_of_mut!(TASK_FN) = Some(f); }
    if s.real_tasks >= TASKS_CAP - 1 { return; } // keep 1 slot for idle
    let mut pcb = Pcb::new();
    pcb.saved_rsp = alloc_task_stack();
    s.tasks.insert(s.real_tasks, pcb);
    s.real_tasks += 1;
    if s.real_tasks == 1 {
        s.started = true;
        SCHED_ON.store(true, core::sync::atomic::Ordering::Relaxed);
        // Boot context is the first to run; mark it as the idle slot.
        unsafe { *core::ptr::addr_of_mut!(CURRENT_ID) = s.real_tasks; }
    }
}

/// Close the ring: append the single IDLE slot and start the cursor at it so the
/// first switch visits a real task. Call once, AFTER the last `spawn`.
#[cfg(target_os = "none")]
pub fn finish() {
    let s = sched_mut();
    if s.real_tasks == 0 { return; }
    // Append the idle Pcb; its live rsp is tracked in IDLE_RSP.
    s.tasks.push(Pcb::new());
    // Ring = [task0..taskN, idle]. Boot runs as the idle slot (cursor points at
    // it), so next changes wrap to task0 on the first tick.
    s.current = s.real_tasks;
    unsafe { *core::ptr::addr_of_mut!(CURRENT_ID) = s.real_tasks; }
}

/// Heap-allocate a task stack and lay down the synthetic switch frame. Returns
/// the logical top that `context_switch` will `mov rsp, <this>`; the six pops
/// land on zero qwords, then `ret` jumps to `task_entry`.
//// `.bss`-arena avoided on purpose: a `static [u8; N]` stack would bump kernel
/// `.bss` into the bootloader 0.11 zone (read-only-#PF / PageAlreadyMapped
/// trap). Heap frames are guaranteed mapped read-write.
#[cfg(target_os = "none")]
fn alloc_task_stack() -> *mut u64 {
    let stack = Box::<[u64; STACK_SIZE / 8]>::new([0u64; STACK_SIZE / 8]);
    let base = Box::leak(stack).as_mut_ptr();
    let top = base as usize + STACK_SIZE;
    let mut p = top - 8;
    let entry_addr = task_entry as extern "C" fn() -> ! as usize;
    unsafe { *(p as *mut usize) = entry_addr; }
    p -= 8;
    for _ in 0..6 { unsafe { *(p as *mut usize) = 0; p -= 8; } }
    (p + 8) as *mut u64
}

/// Perform the deferred switch (kernel main loop only, NEVER from an ISR).
/// Save the running slot's rsp and load the target's. The idle slot — `idx >=
/// real_tasks` — maps to `IDLE_RSP` on both sides.
#[cfg(target_os = "none")]
pub fn run_pending_switch() {
    let s = sched_mut();
    if !s.started || !s.switch_pending { return; }
    s.switch_pending = false;
    let target = s.current;
    s.switches += 1;
    let prev = unsafe { *core::ptr::addr_of!(CURRENT_ID) };

    let target_sp = if target >= s.real_tasks {
        unsafe { *core::ptr::addr_of!(IDLE_RSP) }
    } else {
        s.tasks[target].saved_rsp
    };
    let slot = if prev >= s.real_tasks {
        core::ptr::addr_of_mut!(IDLE_RSP)
    } else {
        &mut s.tasks[prev].saved_rsp
    };
    unsafe {
        *core::ptr::addr_of_mut!(CURRENT_ID) = target;
        context_switch(slot, target_sp);
    }
}

/// The boot/idle scheduler loop: consume PIT kicks, perform deferred switches,
/// park on `hlt`. Called from `kernel_main` once at the end.
#[cfg(target_os = "none")]
pub fn idle_loop() -> ! {
    loop {
        pump_ticks();
        run_pending_switch();
        crate::ffi::hlt();
    }
}

/// Total context switches performed (boot marker).
#[cfg(target_os = "none")]
pub fn switches() -> u64 { sched_mut().switches }

/// Number of real (non-idle) tasks (boot marker).
#[cfg(target_os = "none")]
pub fn task_count() -> usize { sched_mut().real_tasks }

/// Whether the scheduler has started (gates the ISR hook).
#[cfg(target_os = "none")]
pub fn started() -> bool { sched_mut().started }

/// Called from the PIT timer ISR. ISR-safe: only bumps an atomic; the actual
/// selection + switch happen in the main loop.
#[cfg(target_os = "none")]
pub fn on_timer_irq() {
    if SCHED_ON.load(core::sync::atomic::Ordering::Relaxed) {
        PIT_KICKS.fetch_add(1, core::sync::atomic::Ordering::Relaxed);
    }
}

/// Main-loop consumer of PIT kicks → advance RR selection.
#[cfg(target_os = "none")]
pub fn pump_ticks() {
    let kicks = PIT_KICKS.swap(0, core::sync::atomic::Ordering::Relaxed);
    if kicks == 0 { return; }
    let s = sched_mut();
    if s.started { s.tick(); }
}

// ------------------------------ host tests -----------------------------------
#[cfg(test)]
mod tests {
    use super::*;

    fn sched_with(n: usize) -> Scheduler {
        let mut s = Scheduler::new();
        for _ in 0..n { s.push_task(Pcb::new()); }
        s.real_tasks = n;
        s.started = n > 0;
        s
    }

    #[test]
    fn rr_visits_every_task() {
        let mut s = sched_with(3);
        let mut seen = [false; 3];
        for _ in 0..9 { s.tick(); if s.current < 3 { seen[s.current] = true; } }
        assert!(seen.iter().all(|x| *x));
    }

    #[test]
    fn single_task_never_yields() {
        let mut s = sched_with(1);
        assert!(!s.tick());
    }

    #[test]
    fn blocked_task_skipped() {
        let mut s = sched_with(3);
        s.tasks[1].state = TaskState::Blocked;
        s.current = 0;
        assert_eq!(Scheduler::next_index(&s.tasks, 0), Some(2));
    }

    #[test]
    fn rr_wraps_around() {
        let (mut s) = sched_with(4);
        s.current = 3;
        assert_eq!(Scheduler::next_index(&s.tasks, s.current), Some(0));
    }

    #[test]
    fn idle_is_skinnier_ring_member() {
        // Real tasks [0,1] + idle slot at index 2. next after 1 is 2 (idle),
        // then wraps to 0.
        let mut s = sched_with(2);
        s.tasks.push(Pcb::new()); // idle slot at index 2
        assert!(s.is_idle(2));
        assert!(!s.is_idle(0));
        assert_eq!(Scheduler::next_index(&s.tasks, 1), Some(2));
        assert_eq!(Scheduler::next_index(&s.tasks, 2), Some(0));
    }
}