//! Simulated AI assistant stub — Month 6, Path A.
//!
//! There is no real ML on a bare-metal QEMU kernel. This is the honest driver
//! boundary: a deterministic, keyword-driven classifier (same "mock, clearly
//! labeled" convention as the Month-3 face-id gate). A prompt string goes in, a
//! fixed canned reply comes out — allocation-free and host-tested, so the
//! Month-6 "AI" seam is exercised without pretending to be an LLM.

/// Does the lowercase-fold of `hay` contain the lowercase-fold of `needle`?
fn ci_contains(hay: &str, needle: &str) -> bool {
    let hb = hay.as_bytes();
    let nb = needle.as_bytes();
    if nb.is_empty() {
        return true;
    }
    if nb.len() > hb.len() {
        return false;
    }
    'outer: for i in 0..=(hb.len() - nb.len()) {
        for j in 0..nb.len() {
            if hb[i + j].to_ascii_lowercase() != nb[j].to_ascii_lowercase() {
                continue 'outer;
            }
        }
        return true;
    }
    false
}

/// A canned answer for a user `prompt`. Pure, deterministic, allocation-free.
pub fn answer(prompt: &str) -> &'static str {
    if prompt.trim().is_empty() {
        "LionOS AI: no input"
    } else if ci_contains(prompt, "hello") || ci_contains(prompt, "hi") {
        "LionOS AI ready"
    } else if ci_contains(prompt, "help") {
        "LionOS AI: explorer/editor/themes are on the dock"
    } else if ci_contains(prompt, "time") {
        "LionOS AI: ask the CMOS RTC via the drivers"
    } else if ci_contains(prompt, "weather") {
        "LionOS AI: (simulated) no network here"
    } else {
        "LionOS AI: (simulated) canned replies only"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn greeting_returns_ready() {
        assert_eq!(answer("Hello there"), "LionOS AI ready");
        assert_eq!(answer("hi!"), "LionOS AI ready");
    }

    #[test]
    fn help_and_time_are_distinguished() {
        assert_eq!(
            answer("what can you help with?"),
            "LionOS AI: explorer/editor/themes are on the dock"
        );
        assert_eq!(answer("Tell me the time"), "LionOS AI: ask the CMOS RTC via the drivers");
    }

    #[test]
    fn empty_and_unknown_are_handled() {
        assert_eq!(answer("   "), "LionOS AI: no input");
        assert_eq!(answer("plz make coffsZ"), "LionOS AI: (simulated) canned replies only");
        assert_eq!(answer("what is the weather"), "LionOS AI: (simulated) no network here");
    }

    #[test]
    fn matching_is_case_insensitive() {
        assert_eq!(answer("HELLO"), "LionOS AI ready");
        assert_eq!(answer("HeLp"), "LionOS AI: explorer/editor/themes are on the dock");
    }
}