//! `lionos update` — download a LionOS disk image and verify its SHA-256
//! checksum before it may be used.
//!
//! A source is either a local directory containing `lionos-disk.bin` +
//! `checksums.txt`, or an `http://` base URL. A disk whose checksum does not
//! match the published `checksums.txt` entry is REFUSED: it is never written to
//! the cache, so it cannot be booted.

use std::fs;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::Command;

use sha2::{Digest, Sha256};

const DISK_NAME: &str = "lionos-disk.bin";
const CHECKSUMS_NAME: &str = "checksums.txt";

/// Where verified downloads land (overridable in tests to avoid touching home).
fn cache_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("LIONOS_CACHE_DIR") {
        return PathBuf::from(dir);
    }
    let home = std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .unwrap_or_else(|_| ".".into());
    PathBuf::from(home).join(".lionos").join("cache")
}

/// SHA-256 of `data` as lowercase hex.
pub fn sha256_hex(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    hex::encode(hasher.finalize())
}

/// Check that `disk`'s SHA-256 matches the `checksums.txt` entry for `name`.
pub fn verify(disk: &[u8], checksums_text: &str, name: &str) -> Result<(), String> {
    let expected = checksums_text
        .lines()
        .filter_map(|line| {
            let mut it = line.split_whitespace();
            let hash = it.next()?.to_string();
            let file = it.next()?;
            Some((file.to_string(), hash))
        })
        .find(|(file, _)| file == name)
        .map(|(_, hash)| hash)
        .ok_or_else(|| format!("no SHA-256 entry for {name} in {CHECKSUMS_NAME}"))?;

    let actual = sha256_hex(disk);
    if actual.eq_ignore_ascii_case(expected.trim()) {
        Ok(())
    } else {
        Err(format!(
            "SHA-256 mismatch for {name}: expected {expected}, got {actual} — refusing to use the image"
        ))
    }
}

/// Download + verify + cache. Err means the image was refused.
pub fn run(source: &str) -> Result<(), String> {
    let disk = fetch_bytes(source, DISK_NAME)?;
    let checksums = fetch_bytes(source, CHECKSUMS_NAME)?;
    let checksums_text = std::str::from_utf8(&checksums)
        .map_err(|_| format!("{CHECKSUMS_NAME} is not valid UTF-8"))?;

    verify(&disk, checksums_text, DISK_NAME)?; // Err here = refused, nothing written

    let out_dir = cache_dir();
    fs::create_dir_all(&out_dir).map_err(|e| format!("cannot create cache {}: {e}", out_dir.display()))?;
    let out = out_dir.join(DISK_NAME);
    fs::write(&out, &disk).map_err(|e| format!("cannot write {}: {e}", out.display()))?;

    println!("OK  verified {DISK_NAME}: {} bytes, SHA-256 matches", disk.len());
    println!("    saved to {}", out.display());
    println!("    boot it with: lionos run --kernel {}", out.display());
    Ok(())
}

fn fetch_bytes(source: &str, rel: &str) -> Result<Vec<u8>, String> {
    let path = Path::new(source);
    if path.is_dir() {
        let file = path.join(rel);
        fs::read(&file).map_err(|e| format!("cannot read {}: {e}", file.display()))
    } else if let Some(rest) = source.strip_prefix("http://") {
        http_get(rest, rel)
    } else if source.starts_with("https://") {
        // curl handles TLS + redirects (GitHub release URLs 302 to objects).
        // The `-sS` shows errors but not progress; output to a temp file so
        // binary data is not mangled by any console.
        let url = format!("{}/{}", source.trim_end_matches('/'), rel);
        let tmp = std::env::temp_dir().join(format!("lionos-dl-{}-{}", std::process::id(), rel));
        let status = Command::new("curl")
            .args(["-L", "-sS", "-o"]).arg(&tmp).arg(&url)
            .status()
            .map_err(|e| format!("cannot spawn curl: {e}"))?;
        let body = fs::read(&tmp).map_err(|e| format!("cannot read download: {e}"))?;
        let _ = fs::remove_file(&tmp);
        if !status.success() {
            return Err(format!("GET {url} failed (curl exit {status})"));
        }
        Ok(body)
    } else {
        Err(format!(
            "unsupported source {source:?} — use a local directory path or an http(s):// URL"
        ))
    }
}

/// Minimal HTTP/1.1 GET over TCP (no TLS). Placeholder-grade; the real
/// downloader (TLS, redirects, chunked) is future work.
fn http_get(authority_and_path: &str, rel: &str) -> Result<Vec<u8>, String> {
    let base = format!("http://{authority_and_path}");
    let url = format!("{}/{}", base.trim_end_matches('/'), rel);
    let rest = url.strip_prefix("http://").unwrap();
    let (authority, path) = match rest.find('/') {
        Some(i) => (&rest[..i], &rest[i..]),
        None => (rest, "/"),
    };
    let addr = format!("{authority}:80");
    let mut stream = TcpStream::connect(&addr).map_err(|e| format!("connect {addr}: {e}"))?;
    let req = format!("GET {path} HTTP/1.1\r\nHost: {authority}\r\nConnection: close\r\n\r\n");
    stream.write_all(req.as_bytes()).map_err(|e| format!("send: {e}"))?;
    let mut response = Vec::new();
    stream.read_to_end(&mut response).map_err(|e| format!("recv: {e}"))?;

    let header_end = response
        .windows(4)
        .position(|w| w == b"\r\n\r\n")
        .ok_or_else(|| format!("malformed HTTP response from {url}"))?;
    let head = String::from_utf8_lossy(&response[..header_end]);
    if !head.starts_with("HTTP/1.1 200") && !head.starts_with("HTTP/1.0 200") {
        return Err(format!(
            "GET {url} failed: {}",
            head.lines().next().unwrap_or("<no status line>")
        ));
    }
    Ok(response[header_end + 4..].to_vec())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    const ABC_SHA256: &str =
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

    #[test]
    fn sha256_hex_matches_known_vector() {
        assert_eq!(sha256_hex(b"abc"), ABC_SHA256);
    }

    #[test]
    fn verify_accepts_matching_checksum() {
        let ck = format!("{ABC_SHA256}  {DISK_NAME}\n");
        assert!(verify(b"abc", &ck, DISK_NAME).is_ok());
    }

    #[test]
    fn verify_refuses_mismatch() {
        let ck = format!("{:064}  {DISK_NAME}\n", "0");
        assert!(verify(b"abc", &ck, DISK_NAME).is_err());
    }

    #[test]
    fn verify_refuses_missing_entry() {
        assert!(verify(b"abc", "# no entries\n", DISK_NAME).is_err());
    }

    fn temp_dir() -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!("lionos-update-test-{}-{}", std::process::id(), stamp))
    }

    #[test]
    fn update_flow_refuses_a_corrupted_download() {
        let dir = temp_dir();
        fs::create_dir_all(&dir).unwrap();

        // Good download: correct checksums.txt, then verify.
        fs::write(dir.join(DISK_NAME), b"disk bytes").unwrap();
        fs::write(
            dir.join(CHECKSUMS_NAME),
            format!("{}  {DISK_NAME}\n", sha256_hex(b"disk bytes")),
        )
        .unwrap();
        let cache = dir.join("cache");
        std::env::set_var("LIONOS_CACHE_DIR", &cache);
        assert!(run(dir.to_str().unwrap()).is_ok());
        assert!(cache.join(DISK_NAME).is_file(), "verified image should be cached");

        // Corrupt the source after the fact, then refuse.
        fs::write(dir.join(DISK_NAME), b"tampered disk bytes").unwrap();
        assert!(run(dir.to_str().unwrap()).is_err(), "corrupted download must be refused");
        assert!(
            cache.join(DISK_NAME).is_file() && fs::read(cache.join(DISK_NAME)).unwrap() == b"disk bytes",
            "refusal must not overwrite the verified image with a bad one"
        );

        let _ = fs::remove_dir_all(&dir);
    }
}
