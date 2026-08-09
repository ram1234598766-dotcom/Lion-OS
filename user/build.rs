// Pass the non-PIE linker script by ABSOLUTE path (cargo links from user/target/...).
fn main() {
    let ld = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("linker.ld");
    println!("cargo:rustc-link-arg=-T{}", ld.display());
    println!("cargo:rerun-if-changed=linker.ld");
    println!("cargo:rerun-if-changed=src/main.rs");
}