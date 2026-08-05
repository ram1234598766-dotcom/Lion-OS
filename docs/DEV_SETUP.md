# DEV_SETUP.md — LionOS development environment

**Goal:** a new team member (or a fresh machine) can go from zero to a booting
LionOS kernel with no prior context. All commands are for the reference
environment: **Kali Linux on WSL2** (also works on any Debian/Ubuntu host).

## 1. Prerequisites

### 1.1 Rust (nightly) + freestanding target

```sh
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
rustup default nightly
rustup component add rust-src llvm-tools-preview    # rust-src + llvm-tools for bootloader 0.11 stage builds
rustup target add x86_64-unknown-none
```

`rust-toolchain.toml` in the repo pins the exact nightly, so `cargo` selects it
automatically once you `cd` into the repo.

### 1.2 Emulation + firmware

```sh
sudo apt-get update
sudo apt-get install -y qemu-system-x86 ovmf mtools gdb-multiarch strace binwalk
```

The OVMF (UEFI) firmware ships at `/usr/share/OVMF/OVMF_CODE_4M.fd`. It is used
once the real bootloader (UEFI) is running — Month 1 Week 3. Until then the
`bootloader` crate is the boot provider.

### 1.3 Boot-image tooling

```sh
```

The `os/` builder crate wraps the kernel ELF (a build **artifact** dependency,
`CARGO_BIN_FILE_LIONOS_KERNEL_lionos-kernel`) into a bootable disk image via
the `bootloader` crate's **0.11.17** `BiosBoot` DiskImageBuilder (a
build-dependency of `os/`). The image lands at the repo-root `target/bios.img`.

### 1.4 Secret scanning (Day 2)

```sh
# gitleaks (binary — no sudo):
curl -fsSL -o /tmp/g.tgz "https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz"
tar -xzf /tmp/g.tgz -C /tmp gitleaks && mv /tmp/gitleaks ~/.local/bin/ && chmod +x ~/.local/bin/gitleaks

# pre-commit hook runner (user venv — avoids polluting the managed system Python):
python3 -m venv ~/.venvs/prc && ~/.venvs/prc/bin/pip install pre-commit
ln -sf ~/.venvs/prc/bin/pre-commit ~/.local/bin/pre-commit

pre-commit install          # registers .pre-commit-config.yaml (gitleaks) into the repo
```

## 2. Building and running

The kernel and the host launcher are separate cargo crates with separate build
directories (the kernel's non-PIE linker flags are scoped to `kernel/.cargo` so
they never leak into the std launcher). Build each from its own directory:

```sh
# 1) Build the bootable kernel image (output: <repo>/target/x86_64-unknown-none/debug/)
cd kernel && cargo build && cd ../os && cargo build && cd ..

# 2) Build the `lionos` launcher (host binary)
cd launcher && cargo build && cd ..
```

### Via the launcher (recommended)

```sh
lionos run                 # boot the kernel in a window (serial on stdio)
lionos run --headless      # no window; marker goes to stdout (CI uses this)
lionos doctor              # check QEMU is installed; prints install help if not
lionos update --source <dir-or-http-url>   # checksum-verified disk download
```

### Direct QEMU (equivalent to `lionos run`)

```sh
qemu-system-x86_64 -drive format=raw,file=target/bios.img -serial stdio
```

The Week-1 stub prints `LIONOS_INIT_OK` on COM1 then halts. Use `Ctrl+A X` to
exit QEMU, or run headless with `-nographic`.

### Overriding the boot marker (for CI's negative test)

Compile-time marker, overridable via an env var:

```sh
LIONOS_BOOT_MARKER=LIONOS_NEGATIVE cargo build && (cd ../os && LIONOS_BOOT_MARKER=LIONOS_NEGATIVE cargo build)
```

## 3. Virtualization: KVM vs TCG in WSL2

Determine whether hardware acceleration is available:

```sh
systemd-detect-virt        # -> wsl
ls -l /dev/kvm              # exists => KVM available (nested virtualization enabled)
```

- **KVM available** (`/dev/kvm` present, host BIOS + `.wslconfig` nested virt on):

  KVM access is gated by group membership on the WSL side. One-time setup:

  ```sh
  sudo usermod -aG kvm "$USER"      # then log out / back in (or `newgrp kvm`)
  ```

  ```sh
  qemu-system-x86_64 -enable-kvm -machine accel=kvm ...   # fast
  ```

- **KVM unavailable** (no `/dev/kvm`, or "Permission denied" from the `kvm`
  group) → pure software emulation (slow but correct):

  ```sh
  qemu-system-x86_64 -machine accel=tcg ...               # fallback, always boots
  ```

  The `lionos` launcher uses `-machine accel=tcg` by default and boots fine
  either way; KVM only makes it faster.

> **Watch out for:** enabling KVM inside WSL2 requires BOTH the host UEFI
> setting ("nested virtualization"/VT-x inside) AND in
> `C:\Users\<you>\.wslconfig`: `[wsl2]` + `nestedVirtualization=true`.
> Missing either silently disables KVM. **Even then**, `Permission denied` on
> `/dev/kvm` means your user is not in the `kvm` group (check `id`). Add it with
> the `usermod` line above and re-login. Use `-accel tcg` as the portable
> fallback and do not hard-depend on KVM.

## 4. CI

`.github/workflows/ci.yml` runs on GitHub-hosted `ubuntu-latest`: installs the
pinned nightly + build utilities + QEMU, builds the bootable image, boots it
headless with a timeout, and asserts `LIONOS_INIT_OK` appears on serial — plus
a negative run that deliberately breaks the marker to confirm the check fails
when it should.

## 5. Troubleshooting & known gotchas

- **Kernel builds but silently resets / double-faults at boot.** The kernel
  must be linked **non-PIE at 1 MiB**. `x86_64-unknown-none` alone emits a
  position-independent ELF (segments at VMA 0); the root `.cargo/config.toml`
  flags (`relocation-model=static`, `-no-pie`) plus the linker script (passed
  by absolute path from `kernel/build.rs`) are mandatory.
  Verify with `readelf -h` that the kernel ELF is `Type: EXEC`, entry ≈ `0x10xxxx`,
  and that `.bootloader-config` survives (the 0.11 loader panics without it).
- **`cd ../os && cargo build` fails with "no matching package named `kernel`".**
  The artifact-dependency key in `os/Cargo.toml` must be the kernel **package
  name**: `lionos-kernel = { path = "../kernel", artifact = "bin", ... }`. Its
  build.rs env var is `CARGO_BIN_FILE_LIONOS_KERNEL_lionos-kernel`. (The old
  reason to stay on 0.9.35 — "0.11 is incompatible with `bootimage`" — is moot:
  `bootimage` is removed; 0.11.17 ships the image through `BiosBoot`.)
- **`writeln!`/`core::fmt` from the kernel triple-faults.** Fixed by the
  bootloader 0.11.17 upgrade: `kernel/src/serial.rs` implements
  `core::fmt::Write` (`Serial`) and boot prints `LIONOS_FMT_OK`. The Week-1
  double-fault does not reproduce under the 0.11 loader.
- **`-nographic` plus `-serial stdio` errors out** ("cannot use stdio by
  multiple character devices"). With `-nographic`, serial is already stdio; use
  one or the other. For scripted checks prefer `-serial file:<path>`.
- **Changing `LIONOS_BOOT_MARKER` doesn't rebuild.** `kernel/build.rs` declares
  `rerun-if-env-changed` so the negative CI test recompiles; don't remove it.
  The env var must be set on BOTH the `kernel` and `os/` cargo invocations —
  the image is assembled from `os/`'s own artifact build of the kernel, a
  separate cargo process with a separate cache.