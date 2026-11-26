//! The installer package rides at the end of this executable:
//!
//! `[setup exe][package][meta json][meta len u64][package len u64][MAGIC]`
//!
//! `scripts/build-setup.mjs` in apps/desktop appends it after the build, so
//! one file carries both the drawn setup and the electron-builder installer.

use std::fs::File;
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::path::Path;

use serde::{Deserialize, Serialize};

pub const MAGIC: &[u8; 8] = b"SZSETUP1";
const TRAILER_LEN: u64 = 8 + 8 + 8;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Meta {
    pub version: String,
    /// Size of the installed app, for the progress bar.
    pub unpacked_bytes: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Payload {
    pub offset: u64,
    pub len: u64,
    pub meta: Meta,
}

/// Finds the package appended to `exe`, or None when there is none.
pub fn locate(exe: &Path) -> io::Result<Option<Payload>> {
    let mut file = File::open(exe)?;
    let size = file.metadata()?.len();
    if size < TRAILER_LEN {
        return Ok(None);
    }
    file.seek(SeekFrom::Start(size - TRAILER_LEN))?;
    let mut trailer = [0u8; TRAILER_LEN as usize];
    file.read_exact(&mut trailer)?;
    if &trailer[16..24] != MAGIC {
        return Ok(None);
    }
    let meta_len = u64::from_le_bytes(trailer[0..8].try_into().unwrap());
    let len = u64::from_le_bytes(trailer[8..16].try_into().unwrap());
    let Some(offset) = size
        .checked_sub(TRAILER_LEN + meta_len)
        .and_then(|end| end.checked_sub(len))
    else {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "setup trailer is corrupt",
        ));
    };
    file.seek(SeekFrom::Start(offset + len))?;
    let mut raw = vec![0u8; meta_len as usize];
    file.read_exact(&mut raw)?;
    let meta: Meta = serde_json::from_slice(&raw)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
    Ok(Some(Payload { offset, len, meta }))
}

/// Copies the package out of `exe` into `dest`.
pub fn extract(exe: &Path, payload: &Payload, dest: &Path) -> io::Result<()> {
    let mut source = File::open(exe)?;
    source.seek(SeekFrom::Start(payload.offset))?;
    let mut out = File::create(dest)?;
    let copied = io::copy(&mut source.take(payload.len), &mut out)?;
    if copied != payload.len {
        return Err(io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "setup package is truncated",
        ));
    }
    out.flush()
}

/// Appends `package` and `meta` to `setup`; the build script's counterpart,
/// kept here so the tests pin the layout both sides use.
#[cfg(test)]
pub fn append(setup: &Path, package: &[u8], meta: &Meta) -> io::Result<()> {
    let mut file = std::fs::OpenOptions::new().append(true).open(setup)?;
    let raw = serde_json::to_vec(meta).unwrap();
    file.write_all(package)?;
    file.write_all(&raw)?;
    file.write_all(&(raw.len() as u64).to_le_bytes())?;
    file.write_all(&(package.len() as u64).to_le_bytes())?;
    file.write_all(MAGIC)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn meta() -> Meta {
        Meta {
            version: "1.2.3".into(),
            unpacked_bytes: 4096,
        }
    }

    #[test]
    fn finds_and_extracts_the_package() {
        let dir = tempfile::tempdir().unwrap();
        let exe = dir.path().join("setup.exe");
        std::fs::write(&exe, b"MZ fake setup body").unwrap();
        append(&exe, b"package bytes", &meta()).unwrap();

        let payload = locate(&exe).unwrap().unwrap();
        assert_eq!(payload.meta, meta());
        assert_eq!(payload.offset, b"MZ fake setup body".len() as u64);
        let out = dir.path().join("package.exe");
        extract(&exe, &payload, &out).unwrap();
        assert_eq!(std::fs::read(out).unwrap(), b"package bytes");
    }

    #[test]
    fn plain_executable_has_no_package() {
        let dir = tempfile::tempdir().unwrap();
        let exe = dir.path().join("setup.exe");
        std::fs::write(&exe, vec![7u8; 64]).unwrap();
        assert_eq!(locate(&exe).unwrap(), None);
    }

    #[test]
    fn corrupt_lengths_are_an_error() {
        let dir = tempfile::tempdir().unwrap();
        let exe = dir.path().join("setup.exe");
        let mut bytes = b"tiny".to_vec();
        bytes.extend_from_slice(&2u64.to_le_bytes());
        bytes.extend_from_slice(&u64::MAX.to_le_bytes());
        bytes.extend_from_slice(MAGIC);
        std::fs::write(&exe, bytes).unwrap();
        assert!(locate(&exe).is_err());
    }
}
