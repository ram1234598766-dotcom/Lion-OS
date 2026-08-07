//! A minimal spinlock — Month 3, drivers foundation.
//!
//! The first real concurrency the kernel needs: the serial driver (and later
//! the framebuffer text driver) are written from two contexts — the deferred
//! main loop and ISRs. A spinlock keeps their output from interleaving.
//!
//! Backed by `AtomicBool::swap` (on x86_64 this is a `lock xchg` — atomic
//! test-and-set that returns the old value). `core::hint::spin_loop` pauses
//! while contended (test-and-test-and-set).
//!
//! Deliberately no fairness, no reentrancy, single-CPU boot path.
//! `ponytail: a plain test-and-set lock. Add ticket fairness / per-CPU
//! contention only if/when the M3W2 scheduler makes lock contention real.`

use core::cell::UnsafeCell;
use core::ops::{Deref, DerefMut};
use core::sync::atomic::{AtomicBool, Ordering};

/// A guard returned by [`SpinLock::lock`]; holds the lock until dropped.
pub struct SpinLockGuard<'a, T> {
    lock: &'a SpinLock<T>,
}

impl<T> Deref for SpinLockGuard<'_, T> {
    type Target = T;
    fn deref(&self) -> &T {
        // SAFETY: the guard holds the lock, so this is the sole reader/writer.
        unsafe { &*self.lock.value.get() }
    }
}

impl<T> DerefMut for SpinLockGuard<'_, T> {
    fn deref_mut(&mut self) -> &mut T {
        // SAFETY: the guard holds the lock exclusively.
        unsafe { &mut *self.lock.value.get() }
    }
}

impl<T> Drop for SpinLockGuard<'_, T> {
    fn drop(&mut self) {
        self.lock.unlock();
    }
}

/// A spinlock-wrapped value. `T` is reached through [`SpinLockGuard`].
pub struct SpinLock<T> {
    held: AtomicBool,
    value: UnsafeCell<T>,
}

// SAFETY: `T` is only handled while `held`; the flag serializes access.
unsafe impl<T: Send> Sync for SpinLock<T> {}

impl<T> SpinLock<T> {
    /// Create an unlocked lock.
    pub const fn new(value: T) -> Self {
        SpinLock { held: AtomicBool::new(false), value: UnsafeCell::new(value) }
    }

    /// Acquire the lock and hand out a guard. Spins until the lock is free.
    pub fn lock(&self) -> SpinLockGuard<'_, T> {
        // Atomic test-and-set: swap(true) returns the old value; 0 = was free,
        // we now hold it. Test-and-test-and-set: pause while contended.
        while self.held.swap(true, Ordering::Acquire) {
            core::hint::spin_loop();
        }
        SpinLockGuard { lock: self }
    }

    fn unlock(&self) {
        self.held.store(false, Ordering::Release);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lock_guard_grants_exclusive_access() {
        let lock = SpinLock::new(7u32);
        {
            let mut g = lock.lock();
            *g = 9;
        }
        assert_eq!(*lock.lock(), 9);
    }

    #[test]
    fn lock_releases_on_drop() {
        let lock = SpinLock::new(0u32);
        {
            let _g = lock.lock();
            // Held here; guard drops at end of scope.
        }
        // Reacquirable after the guard dropped.
        assert_eq!(*lock.lock(), 0);
    }
}