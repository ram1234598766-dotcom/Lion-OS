//! File explorer — Month 6, Path A.
//!
//! Lists filenames as compositor lines. The pure render widget is host-tested;
//! the FAT scan lives in `fs.rs` (read-only). At boot we report how many files
//! the last mounted volume listed (0 when no disk → the honest `NO_DISK` path).

use alloc::string::String;
use alloc::vec;
use alloc::vec::Vec;

/// Render `names` as up to `max` display lines (each prefixed "  "). Pure.
pub fn dir_lines(names: &[String], max: usize) -> Vec<String> {
    names
        .iter()
        .take(max)
        .map(|n| {
            let mut line = String::from("  ");
            line.push_str(n);
            line
        })
        .collect()
}

/// The number of entries that fit in a `height`-tall view.
pub fn visible_count(files: usize, height: usize) -> usize {
    files.min(height)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dir_lines_indents_and_truncates() {
        let names: Vec<String> = vec!["a.txt".into(), "docs/".into(), "b.bin".into(), "c".into()];
        let lines = dir_lines(&names, 3);
        assert_eq!(lines.len(), 3);
        assert_eq!(lines[0], "  a.txt");
        assert_eq!(lines[2], "  b.bin");
        assert!(lines.iter().all(|l| l.starts_with("  ")));
    }

    #[test]
    fn dir_lines_empty() {
        let out = dir_lines(&[], 10);
        assert!(out.is_empty());
    }

    #[test]
    fn visible_count_clamped_to_height() {
        assert_eq!(visible_count(10, 4), 4);
        assert_eq!(visible_count(3, 8), 3);
        assert_eq!(visible_count(0, 5), 0);
    }
}