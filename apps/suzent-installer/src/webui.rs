//! The prebuilt web UI that `suzent web` serves.
//!
//! `src/suzent/webui/` is built from `frontend/` with Node, which a normal
//! install does not have. Release CI packs the bundle built from the same tag
//! as `suzent-webui.zip`, and both the installer and the updater unpack it.

use crate::{network, updater};
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

pub const ASSET: &str = "suzent-webui.zip";

fn bundle_dir(root: &Path) -> PathBuf {
    root.join("src").join("suzent").join("webui")
}

/// Downloads the release's web UI bundle, checked against its SHA256SUMS, and
/// installs it into `root`. Returns the number of files installed.
pub fn install(root: &Path, bases: &[String]) -> Result<usize, String> {
    install_prefetched(root, bases, None)
}

/// Like [`install`], but unpacks `prefetched` instead of downloading when that
/// archive still matches the release checksum.
pub fn install_prefetched(
    root: &Path,
    bases: &[String],
    prefetched: Option<&Path>,
) -> Result<usize, String> {
    let bytes = download(bases, prefetched)?;
    extract(&bytes, &bundle_dir(root))
}

/// Downloads the release's web UI bundle to `archive` without installing it,
/// so a later update can unpack it without waiting on the network.
pub fn prefetch(bases: &[String], archive: &Path) -> Result<(), String> {
    let bytes = download(bases, Some(archive))?;
    let partial = archive.with_extension("download");
    fs::write(&partial, &bytes)
        .and_then(|()| fs::rename(&partial, archive))
        .map_err(|error| format!("failed to save {}: {error}", archive.display()))
}

fn download(bases: &[String], prefetched: Option<&Path>) -> Result<Vec<u8>, String> {
    let sums = network::fetch_release_file(bases, "SHA256SUMS")
        .map_err(|error| format!("failed to download release checksums: {error}"))?;
    let expected = updater::parse_release_checksum(&String::from_utf8_lossy(&sums), ASSET)?;
    if let Some(bytes) = prefetched.and_then(|path| fs::read(path).ok()) {
        if network::sha256_hex(&bytes) == expected {
            return Ok(bytes);
        }
    }
    let mut errors = Vec::new();
    for base in bases {
        match network::fetch_release_file(std::slice::from_ref(base), ASSET) {
            Ok(bytes) if network::sha256_hex(&bytes) == expected => return Ok(bytes),
            Ok(_) => errors.push(format!("{base}/{ASSET}: checksum mismatch")),
            Err(error) => errors.push(error),
        }
    }
    Err(errors.join("; "))
}

/// Unpacks the archive beside `target` and swaps it in only once every file is
/// out, so a bad archive leaves the previous bundle serving.
pub fn extract(archive: &[u8], target: &Path) -> Result<usize, String> {
    let staging = target.with_file_name("webui.staging");
    let previous = target.with_file_name("webui.previous");
    for leftover in [&staging, &previous] {
        if leftover.exists() {
            fs::remove_dir_all(leftover)
                .map_err(|error| format!("failed to remove {}: {error}", leftover.display()))?;
        }
    }
    let result = unpack(archive, &staging);
    let count = match result {
        Ok(count) => count,
        Err(error) => {
            let _ = fs::remove_dir_all(&staging);
            return Err(error);
        }
    };
    if target.exists() {
        fs::rename(target, &previous)
            .map_err(|error| format!("failed to move aside {}: {error}", target.display()))?;
    }
    if let Err(error) = fs::rename(&staging, target) {
        let _ = fs::rename(&previous, target);
        return Err(format!("failed to install {}: {error}", target.display()));
    }
    let _ = fs::remove_dir_all(&previous);
    Ok(count)
}

fn unpack(archive: &[u8], staging: &Path) -> Result<usize, String> {
    let mut archive = zip::ZipArchive::new(io::Cursor::new(archive))
        .map_err(|error| format!("invalid web UI archive: {error}"))?;
    let mut count = 0;
    for index in 0..archive.len() {
        let mut entry = archive
            .by_index(index)
            .map_err(|error| format!("invalid web UI archive: {error}"))?;
        let Some(relative) = entry.enclosed_name() else {
            return Err(format!(
                "web UI archive entry escapes the bundle: {}",
                entry.name().unwrap_or_default()
            ));
        };
        let destination = staging.join(relative);
        if entry.is_dir() {
            fs::create_dir_all(&destination)
                .map_err(|error| format!("failed to create {}: {error}", destination.display()))?;
            continue;
        }
        if let Some(parent) = destination.parent() {
            fs::create_dir_all(parent)
                .map_err(|error| format!("failed to create {}: {error}", parent.display()))?;
        }
        fs::File::create(&destination)
            .and_then(|mut file| io::copy(&mut entry, &mut file))
            .map_err(|error| format!("failed to write {}: {error}", destination.display()))?;
        count += 1;
    }
    if !staging.join("index.html").is_file() {
        return Err("web UI archive has no index.html".into());
    }
    Ok(count)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn archive(entries: &[(&str, &str)]) -> Vec<u8> {
        let mut writer = zip::ZipWriter::new(io::Cursor::new(Vec::new()));
        for (name, contents) in entries {
            writer
                .start_file(*name, zip::write::SimpleFileOptions::default())
                .unwrap();
            writer.write_all(contents.as_bytes()).unwrap();
        }
        writer.finish().unwrap().into_inner()
    }

    #[test]
    fn replaces_the_previous_bundle() {
        let root = tempfile::tempdir().unwrap();
        let target = bundle_dir(root.path());
        fs::create_dir_all(&target).unwrap();
        fs::write(target.join("index.html"), "old").unwrap();
        fs::write(target.join("stale.js"), "").unwrap();

        let bytes = archive(&[("index.html", "new"), ("assets/app.js", "1")]);
        assert_eq!(extract(&bytes, &target).unwrap(), 2);

        assert_eq!(
            fs::read_to_string(target.join("index.html")).unwrap(),
            "new"
        );
        assert!(target.join("assets/app.js").is_file());
        assert!(!target.join("stale.js").exists());
        assert!(!target.with_file_name("webui.staging").exists());
        assert!(!target.with_file_name("webui.previous").exists());
    }

    #[test]
    fn keeps_the_previous_bundle_when_the_archive_is_not_one() {
        let root = tempfile::tempdir().unwrap();
        let target = bundle_dir(root.path());
        fs::create_dir_all(&target).unwrap();
        fs::write(target.join("index.html"), "old").unwrap();

        assert!(extract(&archive(&[("readme.txt", "")]), &target).is_err());
        assert!(extract(&archive(&[("index.html", ""), ("../x", "")]), &target).is_err());

        assert_eq!(
            fs::read_to_string(target.join("index.html")).unwrap(),
            "old"
        );
        assert!(!root.path().join("src/suzent/x").exists());
        assert!(!target.with_file_name("webui.staging").exists());
    }
}
