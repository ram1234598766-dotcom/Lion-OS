//! IPC mailbox — Month 4, userland.
//!
//! A small kernel-side message channel for ring-3 ↔ kernel IPC. The mailbox is
//! a fixed 64-byte buffer that `send` fills and `recv`/`drain` takes from. The
//! ring-3 "shell" drives it through `SYS_SEND` / `SYS_RECV` (see `syscall.rs`),
//! and the handlers print the carried bytes, so a message demonstrably passes
//! through the kernel.
//!
//! The pure `Mailbox` core is host-tested; the syscall wiring is
//! `#[cfg(target_os = "none")]`. User→kernel data passing is implemented in
//! the syscall layer (`SYS_PUTS` → `user_copy_in`, a bounds-checked
//! `copy_from_user` guarded with `stac`/`clac` under SMAP).

/// Capacity of the mailbox (bytes).
pub const MAILBOX_CAP: usize = 64;

/// The mailshallbox state: a bounded byte buffer + current length.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Mailbox {
    data: [u8; MAILBOX_CAP],
    len: usize,
}

impl Mailbox {
    /// An empty mailbox.
    pub const fn new() -> Self {
        Self { data: [0; MAILBOX_CAP], len: 0 }
    }

    /// Overwrite the mailbox with `msg` (clamped to capacity). Returns the
    /// number of bytes stored.
    pub fn send(&mut self, msg: &[u8]) -> usize {
        let n = msg.len().min(MAILBOX_CAP);
        self.data[..n].copy_from_slice(&msg[..n]);
        self.len = n;
        n
    }

    /// Copy the held bytes into `out` (clamped) without draining. Returns the
    /// number of bytes copied.
    pub fn peek(&self, out: &mut [u8]) -> usize {
        let n = self.len.min(out.len());
        out[..n].copy_from_slice(&self.data[..n]);
        n
    }

    /// Remove and return the held bytes (clamped to `out`).
    pub fn drain(&mut self, out: &mut [u8]) -> usize {
        let n = self.peek(out);
        self.len = 0;
        n
    }

    /// Current held-byte count.
    pub fn len(&self) -> usize {
        self.len
    }
}

impl Default for Mailbox {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn send_fills_and_clamps() {
        let mut m = Mailbox::new();
        assert_eq!(m.send(b"LiOS"), 4);
        assert_eq!(m.len(), 4);
        // Over-long message clamps to capacity.
        let big = [0x41u8; MAILBOX_CAP + 10];
        assert_eq!(m.send(&big), MAILBOX_CAP);
        assert_eq!(m.len(), MAILBOX_CAP);
    }

    #[test]
    fn peek_does_not_drain() {
        let mut m = Mailbox::new();
        m.send(b"abc");
        let mut a = [0u8; 8];
        assert_eq!(m.peek(&mut a), 3);
        assert_eq!(&a[..3], b"abc");
        assert_eq!(m.len(), 3); // still there
    }

    #[test]
    fn drain_clears() {
        let mut m = Mailbox::new();
        m.send(b"xy");
        let mut a = [0u8; 8];
        assert_eq!(m.drain(&mut a), 2);
        assert_eq!(m.len(), 0);
        // second drain gets nothing
        let mut b = [0u8; 8];
        assert_eq!(m.drain(&mut b), 0);
    }

    #[test]
    fn capacity_bound_respected() {
        let mut m = Mailbox::new();
        // A message longer than capacity clamps to CAP and records CAP.
        let msg = [0x8Bu8; MAILBOX_CAP + 20];
        assert_eq!(m.send(&msg), MAILBOX_CAP);
        assert_eq!(m.len(), MAILBOX_CAP);
    }
}