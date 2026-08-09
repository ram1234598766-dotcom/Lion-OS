//! Editor — Month 6, Path A.
//!
//! A minimal, allocation-light text buffer with a cursor-independent insert /
//! backspace API (the compositor cursor position is separate). Pure +
//! host-tested; the boot shell types a few bytes and logs the buffer length.

/// Hard capacity of the buffer (bytes).
pub const EDIT_CAP: usize = 256;

/// A growable byte buffer with cursor-less edit primitives.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TextBuffer {
    buf: alloc::vec::Vec<u8>,
}

impl TextBuffer {
    /// An empty buffer.
    pub fn new() -> Self {
        Self { buf: alloc::vec::Vec::new() }
    }

    /// Insert byte `c` at `at` if the capacity allows. `at` in `0..=len`,
    /// otherwise the byte is dropped. Returns whether it was inserted.
    pub fn insert(&mut self, at: usize, c: u8) -> bool {
        if at <= self.buf.len() && self.buf.len() < EDIT_CAP {
            self.buf.insert(at, c);
            true
        } else {
            false
        }
    }

    /// Delete the byte just before `at` (the backspace key). Returns it or None.
    pub fn backspace(&mut self, at: usize) -> Option<u8> {
        if at > 0 && at <= self.buf.len() {
            Some(self.buf.remove(at - 1))
        } else {
            None
        }
    }

    /// Append a whole byte string; returns bytes actually stored.
    pub fn put(&mut self, s: &[u8]) -> usize {
        let mut n = 0;
        for &c in s {
            if self.insert(self.buf.len(), c) {
                n += 1;
            } else {
                break;
            }
        }
        n
    }

    /// Current length.
    pub fn len(&self) -> usize {
        self.buf.len()
    }

    /// The stored bytes.
    pub fn bytes(&self) -> &[u8] {
        &self.buf
    }
}

impl Default for TextBuffer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn insert_and_read_back() {
        let mut e = TextBuffer::new();
        assert!(e.insert(0, b'h'));
        assert!(e.insert(1, b'i'));
        assert_eq!(e.bytes(), b"hi");
        assert_eq!(e.len(), 2);
    }

    #[test]
    fn put_appends_and_clamps_to_capacity() {
        let mut e = TextBuffer::new();
        assert_eq!(e.put(b"LionOS"), 6);
        assert_eq!(e.len(), 6);
        // Capacity clamp: fill past EDIT_CAP.
        let big = [b'x'; EDIT_CAP + 40];
        e.put(&big);
        assert!(e.len() <= EDIT_CAP);
    }

    #[test]
    fn backspace_removes_before_cursor() {
        let mut e = TextBuffer::new();
        e.put(b"abc");
        assert_eq!(e.backspace(3), Some(b'c'));
        assert_eq!(e.bytes(), b"ab");
        // at 0 -> nothing to delete.
        assert_eq!(e.backspace(0), None);
    }

    #[test]
    fn insert_at_end_is_append() {
        let mut e = TextBuffer::new();
        e.put(b"a");
        assert!(e.insert(e.len(), b'z'));
        assert_eq!(e.bytes(), b"az");
    }
}