//! PS/2 keyboard scancode → ASCII decoder — Month 3, drivers.
//!
//! The interrupt handler (`interrupts::keyboard_isr`) already latches the raw
//! scancode; this module turns a scancode into a character. It maps the
//! standard 8042 scancode set 1 (the QEMU default), with Shift handling for
//! letters/digits/punctuation.
//!
//! Pure and host-testable: `decode` takes a raw scancode and a Shift flag,
//! returning an optional printable char.

/// Decode one PS/2 scancode (set 1) into an ASCII char. Returns `None` for
/// non-printable keys (Enter, arrows, function keys, Space is handled here).
/// `shifted` selects the uppercase/secondary glyph.
pub fn decode(scancode: u8, shifted: bool) -> Option<char> {
    let c = match scancode {
        // Top digit/punctuation row.
        0x02 => if shifted { '!' } else { '1' },
        0x03 => if shifted { '@' } else { '2' },
        0x04 => if shifted { '#' } else { '3' },
        0x05 => if shifted { '$' } else { '4' },
        0x06 => if shifted { '%' } else { '5' },
        0x07 => if shifted { '^' } else { '6' },
        0x08 => if shifted { '&' } else { '7' },
        0x09 => if shifted { '*' } else { '8' },
        0x0A => if shifted { '(' } else { '9' },
        0x0B => if shifted { ')' } else { '0' },
        0x0C => if shifted { '_' } else { '-' },
        0x0D => if shifted { '+' } else { '=' },
        // Letters: the set-1 make codes (NOT alphabetically sequential).
        0x10 => if shifted { 'Q' } else { 'q' },
        0x11 => if shifted { 'W' } else { 'w' },
        0x12 => if shifted { 'E' } else { 'e' },
        0x13 => if shifted { 'R' } else { 'r' },
        0x14 => if shifted { 'T' } else { 't' },
        0x15 => if shifted { 'Y' } else { 'y' },
        0x16 => if shifted { 'U' } else { 'u' },
        0x17 => if shifted { 'I' } else { 'i' },
        0x18 => if shifted { 'O' } else { 'o' },
        0x19 => if shifted { 'P' } else { 'p' },
        0x1A => if shifted { '{' } else { '[' },
        0x1B => if shifted { '}' } else { ']' },
        0x1E => if shifted { 'A' } else { 'a' },
        0x1F => if shifted { 'S' } else { 's' },
        0x20 => if shifted { 'D' } else { 'd' },
        0x21 => if shifted { 'F' } else { 'f' },
        0x22 => if shifted { 'G' } else { 'g' },
        0x23 => if shifted { 'H' } else { 'h' },
        0x24 => if shifted { 'J' } else { 'j' },
        0x25 => if shifted { 'K' } else { 'k' },
        0x26 => if shifted { 'L' } else { 'l' },
        0x27 => if shifted { ':' } else { ';' },
        0x28 => if shifted { '"' } else { '\'' },
        0x29 => if shifted { '~' } else { '`' },
        0x2B => if shifted { '|' } else { '\\'},
        0x2C => if shifted { 'Z' } else { 'z' },
        0x2D => if shifted { 'X' } else { 'x' },
        0x2E => if shifted { 'C' } else { 'c' },
        0x2F => if shifted { 'V' } else { 'v' },
        0x30 => if shifted { 'B' } else { 'b' },
        0x31 => if shifted { 'N' } else { 'n' },
        0x32 => if shifted { 'M' } else { 'm' },
        0x33 => if shifted { '<' } else { ',' },
        0x34 => if shifted { '>' } else { '.' },
        0x35 => if shifted { '?' } else { '/' },
        0x39 => ' ',
        _ => return None,
    };
    Some(c)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lowercase_letters() {
        assert_eq!(decode(0x1E, false), Some('a')); // 0x1E is 'A' scancode
        assert_eq!(decode(0x32, false), Some('m'));
        assert_eq!(decode(0x15, false), Some('y'));
    }

    #[test]
    fn shifted_letters_are_upper() {
        assert_eq!(decode(0x1E, true), Some('A'));
        assert_eq!(decode(0x32, true), Some('M'));
    }

    #[test]
    fn digits_and_shifted_punctuation() {
        assert_eq!(decode(0x02, false), Some('1'));
        assert_eq!(decode(0x02, true), Some('!'));
        assert_eq!(decode(0x0B, false), Some('0'));
        assert_eq!(decode(0x0B, true), Some(')'));
        assert_eq!(decode(0x34, false), Some('.'));
    }

    #[test]
    fn non_printable_returns_none() {
        // Enter (0x1C), Left-Shift (0x2A) -> None.
        assert_eq!(decode(0x1C, false), None);
        assert_eq!(decode(0x2A, false), None);
        assert_eq!(decode(0x39, false), Some(' ')); // space
    }
}