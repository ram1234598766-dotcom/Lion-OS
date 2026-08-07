//! Kernel heap allocator — Month 2, kernel-core.
//!
//! A hand-rolled first-fit free-list allocator that backs `#[global_allocator]`,
//! giving the kernel `Vec`/`Box`/`String` from `alloc`. No external crates.
//!
//! Layout: every *free* block begins with a 16-byte `Node { next, size }`
//! header; `size` is the whole block (header + payload) in bytes, 8-aligned.
//! Allocation first-fits a block big enough, unlinks it, splits any large tail
//! back onto the list, and hands out `block + Node::SIZE`. Deallocation rebuilds
//! a header at `ptr - Node::SIZE` and re-inserts it (LIFO; no address-ordered
//! coalescing yet).
//!
//! Alignment ceiling is 8 bytes — covers every type the M2 kernel and
//! `Vec<u8>`/`Vec<u64>`/`String` need. `ponytail: align > 8 refused rather than
//! returning a mis-aligned pointer; add boundary-tag alignment when the kernel
//! needs super-aligned allocations. `ponytail: first-fit, no coalescing — the
//! arena can fragment; add an address-sorted merge pass when fragmentation is
//! measured to matter.`
//!
//! The allocator is pure and host-testable: tests run `alloc`/`dealloc` against
//! a byte buffer. The kernel `GlobalAlloc` glue uses a `.bss` static.

use core::alloc::{GlobalAlloc, Layout};
use core::cell::UnsafeCell;
use core::ptr;

/// Node stored at the start of each free block (`repr(C)`, 16 bytes).
#[derive(Debug, Clone, Copy)]
#[repr(C)]
struct Node {
    next: *mut Node,
    size: usize,
}

impl Node {
    const SIZE: usize = core::mem::size_of::<Node>();
}

/// Maximum supported alignment.
const ALIGN: usize = 8;

fn align_up(v: usize, a: usize) -> usize {
    (v + a - 1) & !(a - 1)
}

/// Mutable heap state (behind an `UnsafeCell` so `GlobalAlloc` can take
/// `&self`).
struct State {
    head: *mut Node,
    /// Allocated payload bytes (accounting), rounded to `ALIGN`.
    used: usize,
    base: usize,
    size: usize,
}

/// A heap over a caller-provided memory region.
///
/// `Sync` is sound only for the single-CPU boot path where ISRs never call the
/// allocator; documented at the `GlobalAlloc` impl.
pub struct KernelHeap {
    state: UnsafeCell<State>,
}

unsafe impl Sync for KernelHeap {}

impl KernelHeap {
    /// All-zero, uninitialized heap. Call [`Self::init`] before use.
    pub const fn empty() -> Self {
        KernelHeap {
            state: UnsafeCell::new(State { head: ptr::null_mut(), used: 0, base: 0, size: 0 }),
        }
    }

    /// Initialise over `[base, base + size)`. `base` must be `ALIGN`-aligned and
    /// `size` a nonzero multiple of `ALIGN`. Takes `&self` (writes through the
    /// internal `UnsafeCell`) so it can be called on a `static`.
    ///
    /// # Safety
    /// Call exactly once, before any allocation, with a writable region that
    /// outlives the heap.
    pub unsafe fn init(&self, base: usize, size: usize) {
        debug_assert!(base % ALIGN == 0, "heap base not aligned");
        debug_assert!(size % ALIGN == 0, "heap size not aligned");
        debug_assert!(size >= Node::SIZE);
        let state = &mut *self.state.get();
        state.base = base;
        state.size = size;
        state.used = 0;
        state.head = base as *mut Node;
        // One free block covering the whole arena.
        (*state.head) = Node { next: ptr::null_mut(), size };
    }

    /// Total heap capacity in bytes.
    pub fn capacity(&self) -> usize {
        unsafe { (*self.state.get()).size }
    }

    /// Allocated payload bytes (accounting).
    pub fn used(&self) -> usize {
        unsafe { (*self.state.get()).used }
    }

    /// Unused bytes (capacity less used; approximate after fragmentation).
    pub fn free(&self) -> usize {
        self.capacity().saturating_sub(self.used())
    }

    /// Allocate `layout.size()` bytes, `ALIGN`-aligned. Returns null for
    /// `layout.align() > ALIGN` or when the arena is exhausted.
    ///
    /// # Safety
    /// Same as [`GlobalAlloc::alloc`].
    pub unsafe fn alloc_layout(&self, layout: Layout) -> *mut u8 {
        if layout.align() > ALIGN {
            return ptr::null_mut();
        }
        let size = align_up(layout.size(), ALIGN);
        // Minimum bytes to carve out: the caller's payload + one Node header.
        let need = size + Node::SIZE;
        let state = &mut *self.state.get();

        let mut prev = &mut state.head as *mut *mut Node;
        loop {
            let node = *prev;
            if node.is_null() {
                return ptr::null_mut();
            }
            let block_size = unsafe { (*node).size };
            if block_size >= need {
                let addr = node as usize;
                let payload = addr + Node::SIZE;
                // Unlink this block.
                unsafe {
                    *prev = (*node).next;
                }
                state.used += size;
                // Split a tail large enough to host another node.
                let tail_bytes = block_size - need;
                if tail_bytes >= Node::SIZE {
                    unsafe {
                        let tail = (addr + need) as *mut Node;
                        (*tail) = Node { next: state.head, size: tail_bytes };
                        state.head = tail;
                    }
                }
                return payload as *mut u8;
            }
            prev = unsafe { &mut (*node).next } as *mut *mut Node;
        }
    }

    /// Free `layout.size()` bytes back onto the list.
    ///
    /// # Safety
    /// `ptr` must have come from [`Self::alloc_layout`] with the same `layout`.
    pub unsafe fn dealloc_layout(&self, ptr: *mut u8, layout: Layout) {
        let size = align_up(layout.size(), ALIGN);
        let block_addr = (ptr as usize) - Node::SIZE;
        let state = &mut *self.state.get();
        let node = block_addr as *mut Node;
        (*node) = Node { next: state.head, size: size + Node::SIZE };
        state.head = node;
        state.used = state.used.saturating_sub(size);
    }
}

// ---------------------------------------------------------------------------
// GlobalAlloc glue: a `static` heap in `.bss`.
// ---------------------------------------------------------------------------

/// Concrete `#[global_allocator]`.
pub struct KernelAlloc(KernelHeap);

// SAFETY: single CPU; ISRs never allocate during the boot path.
unsafe impl Sync for KernelAlloc {}

impl KernelAlloc {
    /// Heap capacity in bytes (for boot diagnostics).
    #[cfg(target_os = "none")]
    pub fn capacity(&self) -> usize {
        self.0.capacity()
    }

    /// Allocated payload bytes (for boot diagnostics / accounting).
    #[cfg(target_os = "none")]
    pub fn used(&self) -> usize {
        self.0.used()
    }
}

unsafe impl GlobalAlloc for KernelAlloc {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        self.0.alloc_layout(layout)
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        self.0.dealloc_layout(ptr, layout);
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let p = self.alloc(layout);
        if !p.is_null() {
            core::ptr::write_bytes(p, 0, layout.size());
        }
        p
    }
}

/// The kernel's global allocator; heap memory is mapped from physical frames by
/// [`init_heap`] at boot (post page-table takeover).
#[cfg(target_os = "none")]
#[global_allocator]
pub static KERNEL_ALLOC: KernelAlloc = KernelAlloc(KernelHeap::empty());

/// Heap capacity. Now frame-backed: the takeover (see `paging::takeover`)
/// unblocked mapping physical frames, so the heap no longer lives in the kernel
/// image's `.bss` — it is drawn from the physical frame allocator and mapped at
/// a free 512 GiB region. `ponytail: fixed 64 KiB arena; grow-on-demand (more
/// mapped frames, resized arena) is a later-month increment.
#[cfg(target_os = "none")]
pub const HEAP_SIZE: usize = 64 * 1024;

/// Initialize the global heap from mapped physical frames.
///
/// Post-`paging::takeover`, picks a free 512 GiB virtual region, maps
/// `HEAP_SIZE / 4096` frames into it, and inits the free-list allocator over
/// that virtual range. This is the Month-2 payoff of owning the page tables:
/// heap backing is real frame memory, not a baked-in `.bss` array.
///
/// # Safety
/// Call once at boot, after `paging::takeover` and after `frames::init_frames`
/// (so frames are available), before any heap allocation. Interrupts may be
/// enabled, but no ISR may allocate yet.
#[cfg(target_os = "none")]
pub unsafe fn init_heap() {
    let offset = crate::paging::phys_offset();
    // Pick a free 512 GiB region for the heap's virtual base.
    let idx = crate::paging::find_free_top_index(offset)
        .expect("no free PML4 region for the heap");
    // Make the address canonical: high-half region (idx >= 256) needs bits
    // 48..63 set; low-half stays as-is.
    let mut virt = (idx as u64) << 39;
    if idx >= 256 {
        virt |= 0xFFFF_0000_0000_0000;
    }
    let frames_needed = (HEAP_SIZE / 4096) as u64;
    // SAFETY: `virt` is page-aligned in a currently-unmapped 512 GiB region;
    // the allocator must have `frames_needed` spare frames (it does at boot).
    crate::paging::map_range(offset, virt, frames_needed).expect("map heap frames");
    // SAFETY: single-CPU boot, called once; `init(&self)` writes via the
    // internal `UnsafeCell`, so a shared borrow of the static is sufficient.
    KERNEL_ALLOC.0.init(virt as usize, HEAP_SIZE);
}

#[cfg(test)]
mod tests {
    use super::*;
    use alloc::vec::Vec;

    fn fresh(buf: &mut [u8]) -> KernelHeap {
        let mut h = KernelHeap::empty();
        unsafe { h.init(buf.as_mut_ptr() as usize, buf.len()) };
        h
    }

    #[test]
    fn init_sets_capacity_and_accounting() {
        let mut buf = [0u8; 4096];
        let h = fresh(&mut buf);
        assert_eq!(h.capacity(), 4096);
        assert_eq!(h.used(), 0);
    }

    #[test]
    fn allocations_are_distinct_and_8_aligned() {
        let mut buf = [0u8; 4096];
        let h = fresh(&mut buf);
        let a = unsafe { h.alloc_layout(Layout::new::<u64>()) };
        let b = unsafe { h.alloc_layout(Layout::new::<u32>()) };
        assert!(!a.is_null() && !b.is_null());
        assert_eq!(a as usize % 8, 0);
        let base = buf.as_ptr() as usize;
        for p in [a, b] {
            assert!((p as usize) >= base && (p as usize) < base + 4096);
        }
        let (l, r) = if a < b { (a, b) } else { (b, a) };
        assert!(l as usize + Node::SIZE <= r as usize, "payloads overlap");
    }

    #[test]
    fn too_large_alloc_returns_null() {
        let mut buf = [0u8; 256];
        let h = fresh(&mut buf);
        let p = unsafe { h.alloc_layout(Layout::from_size_align(1 << 20, 8).unwrap()) };
        assert!(p.is_null());
    }

    #[test]
    fn high_alignment_is_refused_not_misaligned() {
        let mut buf = [0u8; 512];
        let h = fresh(&mut buf);
        let layout = Layout::from_size_align(64, 64).unwrap();
        let p = unsafe { h.alloc_layout(layout) };
        assert!(p.is_null());
    }

    #[test]
    fn freed_memory_is_reused() {
        let mut buf = [0u8; 4096];
        let h = fresh(&mut buf);
        let l = Layout::from_size_align(128, 8).unwrap();
        let p1 = unsafe { h.alloc_layout(l) };
        unsafe { h.dealloc_layout(p1, l) };
        let p2 = unsafe { h.alloc_layout(l) };
        assert_eq!(p1, p2, "LIFO free should reuse the same block");
    }

    #[test]
    fn many_allocations_do_not_overlap() {
        // 64 KiB so sizes 16..256 (sum of payload + headers ~30 KiB) all fit.
        let mut buf = [0u8; 64 * 1024];
        let h = fresh(&mut buf);
        // Track (ptr, size) per allocation so the overlap check is exact.
        let mut allocs = Vec::new();
        for n in 16..256 {
            let layout = Layout::from_size_align(n, 8).unwrap();
            let p = unsafe { h.alloc_layout(layout) };
            assert!(!p.is_null(), "allocation {n} should fit");
            unsafe { core::ptr::write_bytes(p, 0x5A, n); }
            for &(q, qsize) in &allocs {
                let (l, lsize, r) = if (p as usize) < (q as usize) {
                    (p as usize, n, q as usize)
                } else {
                    (q as usize, qsize, p as usize)
                };
                assert!(l + lsize <= r, "overlap between allocations at {l}..{} and {r}",
                        l + lsize);
            }
            allocs.push((p, n));
        }
        assert!(!allocs.is_empty());
    }

    #[test]
    fn used_accounting_tracks_alloc_free() {
        let mut buf = [0u8; 4096];
        let h = fresh(&mut buf);
        let l = Layout::from_size_align(64, 8).unwrap();
        let p = unsafe { h.alloc_layout(l) };
        assert_eq!(h.used(), 64);
        unsafe { h.dealloc_layout(p, l) };
        assert_eq!(h.used(), 0);
    }
}