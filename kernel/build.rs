//! Rebuild the kernel whenever the boot marker env var changes, so CI's
//! negative boot test (a deliberately wrong marker) actually recompiles.
//! Without `rerun-if-env-changed`, cargo would reuse the cached artifact and
//! the negative run would silently boot the original marker.
fn main() {
    println!("cargo:rerun-if-env-changed=LIONOS_BOOT_MARKER");
}