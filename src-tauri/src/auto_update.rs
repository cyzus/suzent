//! Installs a release the backend already staged (`suzent update --prefetch`)
//! at a moment nobody is using Suzent: when the app exits, or when it starts
//! and the previous exit did not get to it. The updater only has to switch
//! versions, which takes seconds, and runs without a window.

use serde::Deserialize;
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};

use crate::backend;

/// A staged release that fails to install this many times is left for the
/// manual Update button, so a broken release cannot loop on every start.
const MAX_ATTEMPTS: u32 = 2;

/// Set when the app exits on purpose to restart or run the manual updater,
/// which must not race a silent update.
static SKIP_ON_EXIT: AtomicBool = AtomicBool::new(false);

#[derive(Deserialize)]
struct StagedUpdate {
    target_tag: String,
}

pub fn skip_on_exit() {
    SKIP_ON_EXIT.store(true, Ordering::SeqCst);
}

pub fn skipped_on_exit() -> bool {
    SKIP_ON_EXIT.load(Ordering::SeqCst)
}

fn state_dir(root: &Path) -> PathBuf {
    root.join(".suzent")
}

fn read_trimmed(path: &Path) -> Option<String> {
    fs::read_to_string(path)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn is_release_tag(value: &str) -> bool {
    let Some(rest) = value.strip_prefix('v') else {
        return false;
    };
    let parts: Vec<&str> = rest.split('.').collect();
    parts.len() == 3
        && parts
            .iter()
            .all(|part| !part.is_empty() && part.chars().all(|c| c.is_ascii_digit()))
}

fn updater_path() -> PathBuf {
    let name = if cfg!(windows) {
        "suzent-installer.exe"
    } else {
        "suzent-installer"
    };
    backend::find_data_dir().join("updater").join(name)
}

pub fn enabled(root: &Path) -> bool {
    let env_off = std::env::var("SUZENT_AUTO_UPDATE")
        .map(|value| {
            matches!(
                value.trim().to_ascii_lowercase().as_str(),
                "0" | "false" | "off"
            )
        })
        .unwrap_or(false);
    !env_off && read_trimmed(&state_dir(root).join("auto-update")).as_deref() != Some("off")
}

pub fn set_enabled(root: &Path, enabled: bool) -> Result<(), String> {
    let dir = state_dir(root);
    fs::create_dir_all(&dir).map_err(|error| error.to_string())?;
    fs::write(dir.join("auto-update"), if enabled { "on" } else { "off" })
        .map_err(|error| error.to_string())
}

fn attempts_path(root: &Path) -> PathBuf {
    state_dir(root).join("auto-update-attempts.json")
}

fn attempts(root: &Path, tag: &str) -> u32 {
    fs::read(attempts_path(root))
        .ok()
        .and_then(|bytes| serde_json::from_slice::<BTreeMap<String, u32>>(&bytes).ok())
        .and_then(|counts| counts.get(tag).copied())
        .unwrap_or(0)
}

fn record_attempt(root: &Path, tag: &str) {
    // Only the release being installed matters; older counts are dropped.
    let counts = BTreeMap::from([(tag.to_string(), attempts(root, tag) + 1)]);
    if let Ok(bytes) = serde_json::to_vec(&counts) {
        let _ = fs::write(attempts_path(root), bytes);
    }
}

/// Returns the staged release to install now, if any.
///
/// The backend only stages a release that passed the auto-update policy
/// (stable channel, clean checkout, same major version), so this re-checks
/// just what can change between staging and now.
pub fn pending(root: &Path) -> Option<String> {
    pending_with_updater(root, &updater_path())
}

fn pending_with_updater(root: &Path, updater: &Path) -> Option<String> {
    let state = state_dir(root);
    let staged: StagedUpdate =
        serde_json::from_slice(&fs::read(state.join("staged-update.json")).ok()?).ok()?;
    let tag = staged.target_tag;
    if !is_release_tag(&tag)
        || !enabled(root)
        || state.join("update-transaction.json").exists()
        || read_trimmed(&state.join("release-tag")).as_deref() == Some(tag.as_str())
        || attempts(root, &tag) >= MAX_ATTEMPTS
        || !updater.is_file()
        || read_trimmed(&updater.with_file_name("version.txt")).as_deref() != Some(tag.as_str())
    {
        return None;
    }
    Some(tag)
}

/// Starts the updater for `tag` once this process has exited.
pub fn spawn(root: &Path, tag: &str, relaunch: Option<&Path>) -> Result<(), String> {
    record_attempt(root, tag);
    let mut command = Command::new(updater_path());
    command
        .args(["--update", "--headless", "--silent"])
        .arg("--dir")
        .arg(root)
        .args(["--target", tag])
        .args(["--wait-pid", &std::process::id().to_string()])
        .current_dir(root);
    if let Some(relaunch) = relaunch {
        command.arg("--relaunch").arg(relaunch);
    }
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        command.process_group(0);
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const DETACHED_PROCESS: u32 = 0x00000008;
        const CREATE_NEW_PROCESS_GROUP: u32 = 0x00000200;
        command.creation_flags(DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP);
    }
    command
        .spawn()
        .map(|_| ())
        .map_err(|error| format!("failed to start the updater: {error}"))
}

#[cfg(test)]
mod tests {
    use super::{is_release_tag, pending_with_updater, record_attempt, MAX_ATTEMPTS};
    use std::fs;

    fn fixture() -> (tempfile::TempDir, std::path::PathBuf) {
        let temp = tempfile::tempdir().unwrap();
        let state = temp.path().join(".suzent");
        fs::create_dir_all(&state).unwrap();
        fs::write(state.join("release-tag"), "v1.2.0").unwrap();
        fs::write(
            state.join("staged-update.json"),
            r#"{"target_tag": "v1.3.0", "target_commit": "abc"}"#,
        )
        .unwrap();
        let updater = temp.path().join("updater").join("suzent-installer");
        fs::create_dir_all(updater.parent().unwrap()).unwrap();
        fs::write(&updater, "").unwrap();
        fs::write(updater.with_file_name("version.txt"), "v1.3.0").unwrap();
        (temp, updater)
    }

    #[test]
    fn a_staged_release_with_its_updater_is_pending() {
        let (temp, updater) = fixture();
        assert_eq!(
            pending_with_updater(temp.path(), &updater).as_deref(),
            Some("v1.3.0")
        );
    }

    #[test]
    fn nothing_is_pending_when_turned_off_installed_or_retried_out() {
        let (temp, updater) = fixture();
        let state = temp.path().join(".suzent");

        fs::write(state.join("auto-update"), "off").unwrap();
        assert!(pending_with_updater(temp.path(), &updater).is_none());
        fs::write(state.join("auto-update"), "on").unwrap();

        for _ in 0..MAX_ATTEMPTS {
            assert!(pending_with_updater(temp.path(), &updater).is_some());
            record_attempt(temp.path(), "v1.3.0");
        }
        assert!(pending_with_updater(temp.path(), &updater).is_none());
        fs::remove_file(state.join("auto-update-attempts.json")).unwrap();

        fs::write(updater.with_file_name("version.txt"), "v1.2.0").unwrap();
        assert!(pending_with_updater(temp.path(), &updater).is_none());
        fs::write(updater.with_file_name("version.txt"), "v1.3.0").unwrap();

        fs::write(state.join("release-tag"), "v1.3.0").unwrap();
        assert!(pending_with_updater(temp.path(), &updater).is_none());
    }

    #[test]
    fn release_tags_are_strict() {
        assert!(is_release_tag("v0.17.0"));
        assert!(!is_release_tag("0.17.0"));
        assert!(!is_release_tag("v0.17"));
        assert!(!is_release_tag("v0.17.0-rc1"));
    }
}
