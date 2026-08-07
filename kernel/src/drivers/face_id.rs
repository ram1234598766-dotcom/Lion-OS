//! Simulated "face ID" biometric gate — Month 3, drivers (extra).
//!
//! **Honest framing:** a bare-metal x86_64 kernel in QEMU has no camera and no
//! ML hardware, so a *sensor-level* face-recognition driver cannot exist here.
//! What this module provides is the real, host-tested **driver boundary + access
//! policy** a face-id system actually owns: store a registered identity
//! descriptor, then decide whether a probe matches and gate access on that. The
//! `FaceId` policy logic, and the matching function, are genuine code — only the
//! "sensor" input is a stand-in (a caller-supplied descriptor instead of pixels
//! from a camera). This uses the same honest mocked-stub convention the plan
//! applies to the Month-6 AI assistant.
//!
//! In a real system, `verify()`'s input would be a feature vector extracted from
//! an image; here it is the descriptor value itself. The lock-out/separation of
//! the matching logic makes the eventual real camera driver a drop-in.

/// An enrolled identity descriptor. In a real system this is a fixed-size
/// feature vector; here a 64-bit signature stands in for it.
pub type IdentityDescriptor = u64;

/// The current "enrolled" identity (whoever is allowed to pass the gate).
static STORED: core::sync::atomic::AtomicU64 = core::sync::atomic::AtomicU64::new(0);
/// Whether an identity has been enrolled yet (no enrollment = gate locked).
static ENROLLED: core::sync::atomic::AtomicBool = core::sync::atomic::AtomicBool::new(false);

/// Register the identity that is authorized to pass the gate (the "enrolled
/// face"). Overwrites any prior enrollment.
pub fn register_identity(desc: IdentityDescriptor) {
    STORED.store(desc, core::sync::atomic::Ordering::SeqCst);
    ENROLLED.store(true, core::sync::atomic::Ordering::SeqCst);
}

/// The enrolled descriptor, if any.
pub fn enrolled() -> Option<IdentityDescriptor> {
    if ENROLLED.load(core::sync::atomic::Ordering::SeqCst) {
        Some(STORED.load(core::sync::atomic::Ordering::SeqCst))
    } else {
        None
    }
}

/// True if a probe descriptor matches the enrolled identity (the gate opens).
///
/// Pure matching, host-tested. The security property worth testing: a non-
/// enrolled descriptor is always denied, and only an exact match opens.
pub fn verify(probe: IdentityDescriptor) -> bool {
    match enrolled() {
        Some(stored) => probe == stored,
        None => false,
    }
}

/// Gate helper: run some protected action only if the probe authenticates.
pub fn gate<F>(probe: IdentityDescriptor, allowed: F) -> bool
where
    F: FnOnce(),
{
    if verify(probe) {
        allowed();
        true
    } else {
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Reset module state between tests (the globals are shared across tests in
    /// the same module, so order must not leak).
    fn reset() {
        ENROLLED.store(false, core::sync::atomic::Ordering::SeqCst);
        STORED.store(0, core::sync::atomic::Ordering::SeqCst);
    }

    #[test]
    fn no_enrollment_is_locked() {
        reset();
        // Fresh module state: nothing enrolled -> nothing can pass.
        assert!(enrolled().is_none());
        assert!(!verify(0x1234_5678_9ABC_DEF0));
    }

    #[test]
    fn exact_match_opens() {
        let id = 0x4C49_4F4E_4F53_2026u64; // "LIONOS"|2026
        register_identity(id);
        assert_eq!(enrolled(), Some(id));
        assert!(verify(id));
        assert!(!verify(0xDEAD_BEEF_0000_DEAD));
    }

    #[test]
    fn gate_runs_only_on_match() {
        let id = 0xC0FFEE_0000_C0FFEEu64;
        register_identity(id);
        let mut ran = false;
        assert!(gate(id, || ran = true));
        assert!(ran);
        let mut denied = false;
        assert!(!gate(0x0000_0000_0000_0000, || denied = true));
        assert!(!denied);
    }
}