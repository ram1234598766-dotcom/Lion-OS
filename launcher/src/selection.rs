//! LionOS component selection — what the `lionos setup` picker gathers and
//! what gets baked into the boot manifest.
//!
//! Pure data + logic (no env, no IO, no terminal), so the whole model is
//! host-testable. A `Selection` is a set of enabled component keys. `required`
//! components can never be un-ticked; `recommended` ones are enabled by default
//! but optional. The enabled set round-trips through a comma CSV that the
//! installer passes to the kernel build as `LIONOS_COMPONENTS`.

/// A LionOS component the user can enable or disable at install time.
pub struct Component {
    pub key: &'static str,
    // Consumed by the setup TUI (setup.rs) — kept here until that task lands.
    #[allow(dead_code)]
    pub label: &'static str,
    /// Compulsory: enabled always, cannot be un-ticked. Read by the tests that
    /// pin the roster; provisioning itself treats every tool as required.
    #[cfg_attr(not(test), allow(dead_code))]
    pub required: bool,
    /// Pre-ticked but optional (the "recommended" set of the picker).
    pub recommended: bool,
}

/// The full component roster. `required` entries are the kernel core that must
/// always be present; `recommended` entries are pre-ticked by default.
pub const COMPONENTS: &[Component] = &[
    Component { key: "core", label: "kernel core", required: true, recommended: true },
    Component { key: "sched", label: "scheduler", required: true, recommended: true },
    Component { key: "syscall", label: "syscall / ring-3", required: true, recommended: true },
    Component { key: "ipc", label: "IPC", required: true, recommended: true },
    Component { key: "serial", label: "serial debug", required: true, recommended: true },
    Component { key: "seditor", label: "text editor", required: false, recommended: true },
    Component { key: "explorer", label: "file explorer", required: false, recommended: true },
    Component { key: "ai", label: "AI stub", required: false, recommended: true },
    Component { key: "theme", label: "theming", required: false, recommended: true },
    Component { key: "dock", label: "dock app bar", required: false, recommended: true },
    Component { key: "virtio_blk", label: "virtio-blk driver", required: false, recommended: true },
    Component { key: "ide", label: "ATA/IDE driver", required: false, recommended: true },
    Component { key: "pci", label: "PCI enumeration", required: false, recommended: true },
    Component { key: "gfx", label: "graphics / compositor", required: false, recommended: true },
];

/// A chosen set of enabled component keys.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Selection {
    pub enabled: Vec<&'static str>,
}

impl Selection {
    /// Is `key` in the required roster (i.e. cannot be un-ticked)?
    pub fn is_required(&self, key: &str) -> bool {
        COMPONENTS.iter().any(|c| c.key == key && c.required)
    }

    /// Is `key` currently enabled?
    pub fn is_enabled(&self, key: &str) -> bool {
        self.enabled.contains(&key)
    }

    /// Toggle `key`. Required components are a no-op (never disabled).
    pub fn toggle(&mut self, key: &'static str) {
        if self.is_required(key) {
            return;
        }
        if let Some(pos) = self.enabled.iter().position(|&k| k == key) {
            self.enabled.remove(pos);
        } else {
            self.enabled.push(key);
        }
    }

    /// Comma-joined CSV of the enabled component keys (the `LIONOS_COMPONENTS`
    /// env value for the kernel build).
    pub fn csv(&self) -> String {
        self.enabled.join(",")
    }

    /// Serialize as a minimal TOML config.
    pub fn to_toml(&self) -> String {
        let mut s = String::from("[components]\nenabled = [");
        for (i, key) in self.enabled.iter().enumerate() {
            if i > 0 {
                s.push_str(", ");
            }
            s.push('"');
            s.push_str(key);
            s.push('"');
        }
        s.push_str("]\n");
        s
    }

    /// Parse a `components.enabled = ["a", "b"]` TOML doc back into a
    /// `Selection`. Unknown keys are kept if they parse; the required set is
    /// always merged in (a config can't disable compulsory components).
    /// (Round-trip is exercised by the host tests.)
    #[cfg_attr(not(test), allow(dead_code))]
    pub fn from_toml(text: &str) -> Result<Self, String> {
        let mut enabled: Vec<&'static str> = Vec::new();
        // Find the enabled array. Minimal parser: locate the `[components]`
        // section and the `enabled = [ ... ]` line, split entries by `"`.
        let mut capture = false;
        for line in text.lines() {
            let line = line.trim();
            if line.starts_with('[') {
                capture = line.starts_with("[components]");
                continue;
            }
            if capture && line.starts_with("enabled") {
                for tok in line.split('"') {
                    if tok.is_empty() || tok.contains(&['[', ']', ',', '=', ' '][..]) {
                        continue;
                    }
                    // Match against the known roster so `&'static str` holds.
                    if let Some(c) = COMPONENTS.iter().find(|c| c.key == tok) {
                        enabled.push(c.key);
                    } else if !tok.is_empty() {
                        // Unknown key: keep it as a static (shouldn't happen,
                        // but stay lenient rather than error on foreign keys).
                        enabled.push(Box::leak(tok.to_string().into_boxed_str()));
                    }
                }
            }
        }
        // Required components are always present.
        for c in COMPONENTS {
            if c.required && !enabled.contains(&c.key) {
                enabled.push(c.key);
            }
        }
        Ok(Self { enabled })
    }
}

impl Default for Selection {
    /// All recommended components pre-ticked, plus every required one.
    fn default() -> Self {
        let mut enabled: Vec<&'static str> = COMPONENTS
            .iter()
            .filter(|c| c.required || c.recommended)
            .map(|c| c.key)
            .collect();
        // Stable, predictable order (required first, then roster order).
        enabled.sort_by_key(|k| COMPONENTS.iter().position(|c| c.key == *k).unwrap_or(usize::MAX));
        Self { enabled }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_has_all_recommended_and_required() {
        let s = Selection::default();
        for c in COMPONENTS {
            assert!(s.is_enabled(c.key), "{} should default on", c.key);
        }
    }

    #[test]
    fn toggle_removes_a_recommended_component() {
        let mut s = Selection::default();
        assert!(s.is_enabled("seditor"));
        s.toggle("seditor");
        assert!(!s.is_enabled("seditor"));
        assert!(!s.csv().contains("seditor"));
    }

    #[test]
    fn toggle_required_is_a_noop() {
        let mut s = Selection::default();
        s.toggle("sched");
        s.toggle("ipc");
        assert!(s.is_enabled("sched"));
        assert!(s.is_enabled("ipc"));
    }

    #[test]
    fn csv_round_trips_through_toml() {
        let s = Selection::default();
        let base = s.csv();
        let toml = s.to_toml();
        let back = Selection::from_toml(&toml).unwrap();
        assert_eq!(back.csv(), base);
    }

    #[test]
    fn from_toml_always_merges_required() {
        // Even a config that lists nothing re-enables the compulsory core.
        let s = Selection::from_toml("[components]\nenabled = []").unwrap();
        for c in COMPONENTS {
            if c.required {
                assert!(s.is_enabled(c.key));
            }
        }
    }

    #[test]
    fn is_required_flags_only_core() {
        let s = Selection::default();
        assert!(s.is_required("core"));
        assert!(s.is_required("serial"));
        assert!(!s.is_required("pci"));
        assert!(!s.is_required("dock"));
    }
}