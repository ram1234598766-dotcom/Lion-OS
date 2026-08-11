//! Kernel build orchestration.
//!
//! Two jobs:
//!  1. Rebuild whenever the boot marker env var changes, so CI's negative boot
//!     test (a deliberately wrong marker) actually recompiles. Without
//!     `rerun-if-env-changed`, cargo would reuse the cached artifact and the
//!     negative run would silently boot the original marker.
//!  2. Compile the freestanding C (`c/support.c`, `c/fb.c`, `c/string_utils.c`)
//!     and assembly (`asm/cpu.s` in GAS, `asm/port_io.asm` + `asm/cpu_utils.asm`
//!     in NASM) support objects for the kernel target and archive them into a
//!     static lib that rustc links into the kernel ELF (mixed-language
//!     integration). This is the master-plan Month-1 language lay in code:
//!     NASM for the low-level port-I/O + CPU-utils routines, C for the
//!     string/mem helpers, Rust for everything else.
//!
//! GAS and NASM both assemble into ELF64 objects; symbol names don't collide
//! (GAS uses `lion_*`, NASM uses the plan's bare `outb`/`inb`/`read_msr`/...).
//! The linker.ld `/DISCARD/` drops `.comment`/`.note.*`/`.eh_frame` so neither
//! syntax can create misaligned orphan LOAD segments.
//!
//! Host-side builds (`cargo test --target x86_64-unknown-linux-gnu`) skip the
//! C/asm step: the pure parsers in `lib.rs` are tested there and never call the
//! FFI bridge.

use std::path::PathBuf;

/// Compile one C or GAS-assembly source into an object for the freestanding kernel.
fn compile(cc: &str, src: &str, obj: &PathBuf) {
    // -mcmodel=kernel + -fno-pie + -mno-red-zone match the Rust kernel's static,
    // small-code-model, no-red-zone assumptions so the mixed objects agree on
    // addressing. -nostdinc/-nostdlib keep support.c fully freestanding. These
    // flag sets are x86_64-specific but the kernel target already is.
    let status = std::process::Command::new(cc)
        .args([
            "-m64",
            "-O2",
            "-fno-pie",
            "-ffreestanding",
            "-fno-builtin",
            "-fno-stack-protector",
            "-mno-red-zone",
            "-mcmodel=kernel",
            "-nostdlib",
            "-nostdinc",
            "-c",
            src,
            "-o",
            obj.to_str().unwrap(),
        ])
        .status()
        .expect("failed to spawn the C/asm compiler (CC/AR must be on PATH)");
    assert!(status.success(), "compiling {src} failed");
}

/// Compile one C++17 source into an object. Same flag contract as `compile`
/// (freestanding, kernel addressing, no PIE), with the C++ runtime cuts
/// (no exceptions/RTTI/threadsafe-statics) so the link stays freelibstdc++.
fn compile_cxx(cc: &str, src: &str, obj: &PathBuf) {
    let status = std::process::Command::new(cc)
        .args([
            "-m64",
            "-O2",
            "-std=c++17",
            "-fno-pie",
            "-ffreestanding",
            "-fno-exceptions",
            "-fno-rtti",
            "-fno-threadsafe-statics",
            "-fno-builtin",
            "-fno-stack-protector",
            "-mno-red-zone",
            "-mcmodel=kernel",
            "-nostdlib",
            "-nostdinc",
            "-c",
            src,
            "-o",
            obj.to_str().unwrap(),
        ])
        .status()
        .expect("failed to spawn the C++ compiler (CC must be g++ for a .cpp suffix)");
    assert!(status.success(), "compiling {src} (C++) failed");
}

/// Build one Zig source into a freestanding ELF64 object via `zig build-obj`.
/// `build-obj` emits a bare object (C-ABI `@export` symbols, no std OS deps),
/// the same object contract C/GAS/NASM produce for `link_ffi`.
fn build_zig(zig: &str, src: &str, obj: &PathBuf) {
    // `-femit-bin` must be `=`-attached (Zig does not accept a separate path
    // arg here), pointing at an absolute OUT_DIR object path.
    let emit = format!("-femit-bin={}", obj.to_str().unwrap());
    let status = std::process::Command::new(zig)
        .args(["build-obj", src, "-O", "ReleaseSafe", &emit])
        .status()
        .expect("failed to spawn Zig (is `zig` on PATH? set ZIG=<path>)");
    assert!(status.success(), "zig build-obj {src} failed");
}

/// Assemble one NASM source into an ELF64 object for the freestanding kernel.
fn assemble_nasm(nasm: &str, src: &str, obj: &PathBuf) {
    let status = std::process::Command::new(nasm)
        .args(["-f", "elf64", "-o", obj.to_str().unwrap(), src])
        .status()
        .expect("failed to spawn NASM (is `nasm` on PATH? apt install nasm)");
    assert!(status.success(), "assembling {src} failed");
}

/// Roll objects into a static archive and emit the link directives.
fn link_ffi(objects: &[PathBuf], out: &PathBuf) {
    let ar = std::env::var("AR").unwrap_or_else(|_| "ar".to_string());
    let lib = out.join("liblionos_ffi.a");
    let mut cmd = std::process::Command::new(&ar);
    cmd.arg("crus").arg(&lib);
    for o in objects {
        cmd.arg(o);
    }
    let status = cmd.status().expect("failed to spawn the archiver (AR)");
    assert!(status.success(), "archiving the FFI objects failed");

    // Search path first, then the lib, so `static=lionos_ffi` ("-llionos_ffi")
    // resolves against our archive. Directives only apply to this kernel build.
    println!("cargo:rustc-link-search=native={}", out.display());
    println!("cargo:rustc-link-lib=static=lionos_ffi");
}

/// The LionOS components that are always present regardless of the user's
/// picker (the compulsory "kernel core" — must match `Selection::is_required`).
const REQUIRED_COMPONENTS: &[&str] = &["core", "sched", "syscall", "ipc", "serial"];

/// Generate `OUT_DIR/component_manifest.rs` from the `LIONOS_COMPONENTS` env
/// (the `lionos setup` selection) merged with the required core. Emitted before
/// the FFI early-return so host test builds get it too. Returns the CSV used to
/// verify the embedded value.
fn generate_manifest(out_dir: &std::path::Path) -> String {
    // A comma CSV of user-selected components.
    let raw = std::env::var("LIONOS_COMPONENTS").unwrap_or_default();
    let user: Vec<&str> = raw.split(',').filter(|s| !s.is_empty()).collect();
    // Merge required + user, de-duped, preserving required-then-user order.
    let mut keys: Vec<&str> = Vec::new();
    for k in REQUIRED_COMPONENTS.iter().chain(user.iter()) {
        if !keys.contains(k) {
            keys.push(k);
        }
    }
    let csv = keys.join(",");

    let list = keys
        .iter()
        .map(|k| format!("\"{k}\""))
        .collect::<Vec<_>>()
        .join(", ");
    let src = format!(
        "// generated by build.rs from LIONOS_COMPONENTS; do not edit\n\
         pub const REQUIRED: &[&str] = &[{required}];\n\
         pub const ENABLED: &[&str] = &[{list}];\n\
         pub const CSV: &str = \"{csv}\";\n",
        required = REQUIRED_COMPONENTS
            .iter()
            .map(|k| format!("\"{k}\""))
            .collect::<Vec<_>>()
            .join(", "),
    );
    let path = out_dir.join("component_manifest.rs");
    std::fs::write(&path, src).expect("write component_manifest.rs");
    println!("cargo:rerun-if-env-changed=LIONOS_COMPONENTS");
    csv
}

fn main() {
    let out_dir = std::path::PathBuf::from(std::env::var_os("OUT_DIR").expect("OUT_DIR"));
    generate_manifest(&out_dir);
    println!("cargo:rerun-if-env-changed=LIONOS_BOOT_MARKER");
    println!("cargo:rerun-if-changed=c/support.c");
    println!("cargo:rerun-if-changed=c/fb.c");
    println!("cargo:rerun-if-changed=c/string_utils.c");
    println!("cargo:rerun-if-changed=asm/cpu.s");
    println!("cargo:rerun-if-changed=asm/port_io.asm");
    println!("cargo:rerun-if-changed=asm/cpu_utils.asm");
    println!("cargo:rerun-if-changed=asm/switch.asm");
    println!("cargo:rerun-if-changed=cpp/lionos_cpp.cpp");
    println!("cargo:rerun-if-changed=zig/lionos_zig.zig");

    // The FFI objects exist only for the freestanding kernel target; host-side
    // test builds must not try to compile them (no kernel compiler contract).
    if std::env::var("TARGET").as_deref() != Ok("x86_64-unknown-none") {
        return;
    }

    // The non-PIE linker script must be passed by ABSOLUTE path: when `os/`
    // builds this crate as a build artifact, the linker's cwd is under
    // `os/target/...`, so a relative `-Tkernel/linker.ld` would not resolve.
    // `CARGO_MANIFEST_DIR` is always this package's directory.
    let linker_script = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("linker.ld");
    println!("cargo:rustc-link-arg=-T{}", linker_script.display());

    let cc = std::env::var("CC").unwrap_or_else(|_| "cc".to_string());
    let nasm = std::env::var("NASM").unwrap_or_else(|_| "nasm".to_string());
    let zig = std::env::var("ZIG").unwrap_or_else(|_| "zig".to_string());
    let out = PathBuf::from(std::env::var_os("OUT_DIR").expect("OUT_DIR"));

    let mut objects = Vec::new();
    // C + GAS (via the host C compiler, which handles `-c` of .c and .s).
    for (name, src) in [
        ("support", "c/support.c"),
        ("fb", "c/fb.c"),
        ("string_utils", "c/string_utils.c"),
        ("cpu", "asm/cpu.s"),
    ] {
        let obj = out.join(format!("{name}.o"));
        compile(&cc, src, &obj);
        objects.push(obj);
    }
    // NASM (via the nasm assembler, elf64 to match the kernel).
    for (name, src) in [
        ("port_io", "asm/port_io.asm"),
        ("cpu_utils", "asm/cpu_utils.asm"),
        ("context_switch", "asm/switch.asm"),
    ] {
        let obj = out.join(format!("{name}.o"));
        assemble_nasm(&nasm, src, &obj);
        objects.push(obj);
    }
    // C++17 + Zig (the Month-3 language lay extension).
    // NOTE: `compile_cxx` is invoked with the C compiler driver (gcc/g++); a
    // `.cpp` source makes gcc invoke the C++ frontend regardless of the binary's
    // basename. Zig is invoked via `zig build-obj` (C-ABI export, freestanding).
    let cpp_obj = out.join("cpp_lionos.o");
    compile_cxx(&cc, "cpp/lionos_cpp.cpp", &cpp_obj);
    objects.push(cpp_obj);

    let zig_obj = out.join("zig_lionos.o");
    build_zig(&zig, "zig/lionos_zig.zig", &zig_obj);
    objects.push(zig_obj);

    link_ffi(&objects, &out);

    // Build the ring-3 `user` program (a standalone non-PIE ELF) and expose its
    // path so the kernel can embed it. `user/` is its own workspace with its own
    // target dir, so invoking cargo here is safe (no shared target lock).
    let cargo = std::env::var("CARGO").unwrap_or_else(|_| "cargo".to_string());
    let kernel_dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let manifest = kernel_dir.join("../user/Cargo.toml");
    let status = std::process::Command::new(&cargo)
        .args(["build", "--release", "--manifest-path"]).arg(&manifest)
        .args(["--target", "x86_64-unknown-none"])
        .env("CARGO_TARGET_DIR", kernel_dir.join("../user/target"))
        .status()
        .expect("failed to spawn the user-crate build");
    assert!(status.success(), "building the user crate failed");
    let src = kernel_dir.join("../user/target/x86_64-unknown-none/release/user");
    let dst = out.join("user_elf.bin");
    std::fs::copy(&src, &dst).expect("copy the user ELF into OUT_DIR");
    println!("cargo:rustc-env=USER_ELF={}", dst.display());
    println!("cargo:rerun-if-changed={}", kernel_dir.join("../user/src/main.rs").display());
    println!("cargo:rerun-if-changed={}", kernel_dir.join("../user/linker.ld").display());
}