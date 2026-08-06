//! Physical frame allocator — Month 2, kernel-core.
//!
//! Manages 4 KiB physical frames handed out from the validated *usable* memory
//! regions (see `memory.rs`). It is **pure accounting**: it tracks frame numbers
//! only and never dereferences them, so it is safe even though the bootloader
//! has not mapped free frames into the page tables. (Actually *using* a frame —
//! e.g. as heap backing — needs the M2W3+ page-table mapper to identity-map it
//! first.)
//!
//! Internally a free-list of frame *runs* (contiguous frame ranges). `allocate`
//! takes the first frame of the first non-empty run; `deallocate` re-inserts a
//! one-frame run and merges adjacent runs so the arena stays defragmented.
//! `MAX_RUNS` bounds the list; `init` refuses more than that.
//!
//! `ponytail: first-run (bump-like) allocation; the free list is O(n) and not
//! coalesced across non-adjacent runs. Fine for boot-time framing; revisit
//! locality/robustness when the scheduler and user memory arrive.`

/// Size of one physical frame.
pub const FRAME_SIZE: u64 = 4096;

/// Hard cap on free-run entries (mirrors the memory map's region cap).
pub const MAX_RUNS: usize = 64;

/// A run of contiguous free frames `[start, start + count)` (frame numbers).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FrameRun {
    pub start: u64,
    pub count: u64,
}

/// Why `init` rejected the region set.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FrameError {
    /// More distinct runs than [`MAX_RUNS`] after merging.
    TooManyRuns,
}

/// Physical frame allocator over a caller-chosen set of usable regions.
pub struct FrameAllocator {
    runs: [FrameRun; MAX_RUNS],
    run_count: usize,
    total: u64,
    allocated: u64,
}

impl FrameAllocator {
    /// All-zero, uninitialized allocator. Call [`Self::init`] first.
    pub const fn empty() -> Self {
        FrameAllocator {
            runs: [FrameRun { start: 0, count: 0 }; MAX_RUNS],
            run_count: 0,
            total: 0,
            allocated: 0,
        }
    }

    /// Initialise over `regions` (byte `(start, end)` pairs, end-exclusive),
    /// clipping to `floor` so anything below it — the kernel image, the
    /// bootloader's structures — is never handed out. Every region above the
    /// floor is converted to an aligned frame run. Returns an error if the
    /// region count would overflow `MAX_RUNS`.
    ///
    /// # Safety
    /// `regions` must come from the validated memory map (no overlaps).
    pub fn init(&mut self, regions: &[(u64, u64)], floor: u64) -> Result<(), FrameError> {
        let mut collected: [FrameRun; MAX_RUNS] = [FrameRun { start: 0, count: 0 }; MAX_RUNS];
        let mut n = 0usize;
        for &(start, end) in regions {
            if end <= floor {
                continue;
            }
            let s = start.max(floor);
            if s >= end {
                continue;
            }
            // Frame-align the start (round up) and end (round down).
            let start_frame = (s + FRAME_SIZE - 1) / FRAME_SIZE;
            let end_frame = end / FRAME_SIZE;
            if start_frame >= end_frame {
                continue;
            }
            if n >= MAX_RUNS {
                return Err(FrameError::TooManyRuns);
            }
            collected[n] = FrameRun { start: start_frame, count: end_frame - start_frame };
            n += 1;
        }
        // Merge adjacent runs so `run_count` stays minimal.
        collected[..n].sort_unstable_by(|a, b| a.start.cmp(&b.start));
        let mut merged: [FrameRun; MAX_RUNS] = [FrameRun { start: 0, count: 0 }; MAX_RUNS];
        let mut m = 0usize;
        for i in 0..n {
            if m > 0 && merged[m - 1].start + merged[m - 1].count == collected[i].start {
                merged[m - 1].count += collected[i].count;
            } else {
                if m >= MAX_RUNS {
                    return Err(FrameError::TooManyRuns);
                }
                merged[m] = collected[i];
                m += 1;
            }
        }
        self.runs[..m].copy_from_slice(&merged[..m]);
        self.run_count = m;
        self.total = merged[..m].iter().map(|r| r.count).sum();
        self.allocated = 0;
        Ok(())
    }

    /// Total frames made available at `init`.
    pub fn total_frames(&self) -> u64 {
        self.total
    }

    /// Frames still free (sum of all runs).
    pub fn free_frames(&self) -> u64 {
        self.runs[..self.run_count].iter().map(|r| r.count).sum()
    }

    /// Frames currently allocated.
    pub fn allocated_frames(&self) -> u64 {
        self.allocated
    }

    /// Allocate one frame, returning its physical frame number. `None` when
    /// exhausted.
    pub fn allocate(&mut self) -> Option<u64> {
        for i in 0..self.run_count {
            if self.runs[i].count > 0 {
                let frame = self.runs[i].start;
                self.runs[i].start += 1;
                self.runs[i].count -= 1;
                self.allocated += 1;
                return Some(frame);
            }
        }
        None
    }

    /// Free a frame, merging adjacent runs so holes re-coalesce.
    pub fn deallocate(&mut self, frame: u64) {
        if self.run_count >= MAX_RUNS {
            // Run out of list slots: drop the frame (accounting-only best effort).
            // ponytail: a full run list silently loses a free frame; a real
            // allocator grows a frame for the list itself.
            return;
        }
        self.runs[self.run_count] = FrameRun { start: frame, count: 1 };
        self.run_count += 1;
        // Sort by start and merge adjacent runs.
        self.runs[..self.run_count].sort_unstable_by(|a, b| a.start.cmp(&b.start));
        let mut m = 0usize;
        for i in 0..self.run_count {
            if m > 0 && self.runs[m - 1].start + self.runs[m - 1].count == self.runs[i].start {
                self.runs[m - 1].count += self.runs[i].count;
            } else {
                self.runs[m] = self.runs[i];
                m += 1;
            }
        }
        self.run_count = m;
        self.allocated = self.allocated.saturating_sub(1);
    }
}

/// The kernel's frame allocator, populated at boot from the validated memory
/// map. `static mut` + `#[cfg(test)]`-free: only the boot path touches it.
#[cfg(target_os = "none")]
static mut FRAMES: FrameAllocator = FrameAllocator::empty();

// -------- boot-facing wrappers over the static allocator (kernel target) --------

/// Access the static `FRAMES` by raw pointer (not a direct `&mut static`, which
/// trips the `static_mut_refs` lint). Single-CPU boot context — never re-entered.
#[cfg(target_os = "none")]
fn frames_mut() -> &'static mut FrameAllocator {
    // SAFETY: single-CPU boot path; the mutable alias lives only for the call.
    unsafe { &mut *core::ptr::addr_of_mut!(FRAMES) }
}

/// Initialize `FRAMES` from usable byte-regions `regions` (end-exclusive),
/// clipped to `floor` (>= the kernel image end + bootloader margin).
#[cfg(target_os = "none")]
pub unsafe fn init_frames(regions: &[(u64, u64)], floor: u64) -> Result<(), FrameError> {
    frames_mut().init(regions, floor)
}

/// Allocate one physical frame number.
#[cfg(target_os = "none")]
pub fn allocate_frame() -> Option<u64> {
    frames_mut().allocate()
}

/// Free one physical frame number.
#[cfg(target_os = "none")]
pub fn deallocate_frame(frame: u64) {
    frames_mut().deallocate(frame);
}

/// Total frames available after init (accounting).
#[cfg(target_os = "none")]
pub fn total_frames() -> u64 {
    frames_mut().total_frames()
}

/// Frames still free (accounting).
#[cfg(target_os = "none")]
pub fn free_frames() -> u64 {
    frames_mut().free_frames()
}

/// Frames allocated (accounting).
#[cfg(target_os = "none")]
pub fn used_frames() -> u64 {
    frames_mut().allocated_frames()
}

#[cfg(test)]
mod tests {
    use super::*;
    use alloc::vec;
    use alloc::vec::Vec;

    fn run_allocs(a: &mut FrameAllocator, count: u64) -> Vec<u64> {
        (0..count).map(|_| a.allocate().expect("frame available")).collect()
    }

    #[test]
    fn init_counts_frames() {
        let mut a = FrameAllocator::empty();
        // Region [0x1000, 0x5000) = 4 frames.
        a.init(&[(0x1000, 0x5000)], 0).unwrap();
        assert_eq!(a.total_frames(), 4);
        assert_eq!(a.free_frames(), 4);
        assert_eq!(a.allocated_frames(), 0);
    }

    #[test]
    fn floor_clips_low_regions() {
        let mut a = FrameAllocator::empty();
        // Region below floor is entirely skipped; region above is clipped.
        a.init(&[(0x1000, 0x2000), (0x5000, 0x9000)], 0x4800).unwrap();
        // [0x5000..0x9000) → frames 5..9 (floor 0x4800 rounds up to frame 5).
        assert_eq!(a.total_frames(), 4);
        assert_eq!(a.free_frames(), 4);
    }

    #[test]
    fn allocations_are_monotonic() {
        let mut a = FrameAllocator::empty();
        a.init(&[(0x1000, 0x4000)], 0).unwrap();
        let frames = run_allocs(&mut a, 3);
        assert_eq!(frames, vec![1, 2, 3]);
    }

    #[test]
    fn exhaustion_returns_none() {
        let mut a = FrameAllocator::empty();
        a.init(&[(0x1000, 0x2000)], 0).unwrap();
        assert!(a.allocate().is_some());
        assert!(a.allocate().is_none(), "only 1 frame in this region");
    }

    #[test]
    fn deallocate_reuses_frame() {
        let mut a = FrameAllocator::empty();
        a.init(&[(0x1000, 0x3000)], 0).unwrap();
        let f = a.allocate().unwrap();
        a.deallocate(f);
        assert_eq!(a.allocate().unwrap(), f, "freed frame is reused");
    }

    #[test]
    fn out_of_order_dealloc_merges() {
        let mut a = FrameAllocator::empty();
        a.init(&[(0x1000, 0x5000)], 0).unwrap();
        let frames = run_allocs(&mut a, 4); // frames 1,2,3,4
        a.deallocate(frames[1]); // 2
        a.deallocate(frames[3]); // 4
        a.deallocate(frames[2]); // 3 — 2,3,4 coalesce
        // Reallocate 3 more: the merged run [2,3,4] yields 2,3,4 again.
        let got = run_allocs(&mut a, 3);
        assert_eq!(got, vec![2, 3, 4]);
    }

    #[test]
    fn accounting_tracks() {
        let mut a = FrameAllocator::empty();
        a.init(&[(0x1000, 0x5000)], 0).unwrap();
        let f = a.allocate().unwrap();
        assert_eq!(a.allocated_frames(), 1);
        assert_eq!(a.free_frames(), 3);
        a.deallocate(f);
        assert_eq!(a.allocated_frames(), 0);
        assert_eq!(a.free_frames(), 4);
    }
}