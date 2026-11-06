//! Which Suzent extras `uv sync` installs.
//!
//! Chat apps and device hardware ship as built-in plugins whose packages live
//! in pyproject extras (`telegram`, `feishu`, `camera`, ...). Installs and
//! updates sync exactly the extras of the plugins the user has on, the same
//! set `suzent upgrade` computes. The rules live in one place,
//! `src/suzent/plugins/enablement.py`, which imports nothing from Suzent so it
//! runs on the environment's Python before that environment is synced.

use std::env;
use std::path::{Path, PathBuf};
use std::process::Command;

/// What every install synced before plugins existed; used when a checkout
/// predates `enablement.py` or the plugin state cannot be read.
const LEGACY_EXTRAS: &[&str] = &["social"];

const ENABLEMENT_SCRIPT: &str = "src/suzent/plugins/enablement.py";

pub fn venv_python(root: &Path) -> PathBuf {
    if cfg!(windows) {
        root.join(".venv/Scripts/python.exe")
    } else {
        root.join(".venv/bin/python")
    }
}

/// `plugins.json`, where the user's plugin choices are kept.
///
/// A relative `SUZENT_DATA_DIR` is resolved against `install_root`, where the
/// backend runs, not against wherever this helper's subprocess runs (a
/// temporary release worktree during prefetch).
pub fn plugin_state_file(install_root: &Path) -> PathBuf {
    let dir = data_dir(env::var("SUZENT_DATA_DIR").ok(), &crate::dirs_home());
    let dir = if dir.is_absolute() {
        dir
    } else {
        install_root.join(dir)
    };
    dir.join("config").join("plugins.json")
}

/// Suzent's data directory, resolved like `suzent.config.paths.get_data_dir`:
/// the `SUZENT_DATA_DIR` override with a leading `~` expanded, else `~/.suzent`.
fn data_dir(override_value: Option<String>, home: &Path) -> PathBuf {
    let Some(value) = override_value.filter(|value| !value.trim().is_empty()) else {
        return home.join(".suzent");
    };
    let value = value.trim();
    if value == "~" {
        return home.to_path_buf();
    }
    if let Some(rest) = value
        .strip_prefix("~/")
        .or_else(|| value.strip_prefix("~\\"))
    {
        return home.join(rest);
    }
    PathBuf::from(value)
}

/// The user's `social.json`: the data-dir copy beside `plugins.json`, else the
/// live installation's `config/social.json`, where older versions kept it.
pub fn social_config_file(install_root: &Path) -> PathBuf {
    let state = plugin_state_file(install_root);
    pick_social_file(&state, install_root)
}

fn pick_social_file(state_file: &Path, install_root: &Path) -> PathBuf {
    let user = state_file.with_file_name("social.json");
    if user.is_file() {
        return user;
    }
    let checkout = install_root.join("config").join("social.json");
    if checkout.is_file() {
        checkout
    } else {
        user
    }
}

fn legacy() -> Vec<String> {
    LEGACY_EXTRAS
        .iter()
        .map(|extra| extra.to_string())
        .collect()
}

/// The extras of the plugins enabled for `checkout`, computed with `python`.
///
/// `install_root` is the live installation, whose `config/social.json` holds
/// the user's chat apps. It differs from `checkout` when prefetching into a
/// clean checkout of the target release, which has no user configuration.
pub fn enabled_plugin_extras(checkout: &Path, install_root: &Path, python: &Path) -> Vec<String> {
    let script = checkout.join(ENABLEMENT_SCRIPT);
    if !script.is_file() {
        return legacy();
    }
    if !python.is_file() {
        eprintln!(
            "Python {} not found; installing the legacy extras {:?}.",
            python.display(),
            LEGACY_EXTRAS
        );
        return legacy();
    }
    let mut command = Command::new(python);
    crate::hide_command_window(&mut command);
    command
        .arg(&script)
        .arg(checkout)
        .arg(plugin_state_file(install_root))
        .arg(social_config_file(install_root))
        .current_dir(checkout)
        .env_remove("PYTHONPATH")
        .env_remove("PYTHONHOME");
    match command.output() {
        Ok(output) if output.status.success() => {
            parse_extras(&String::from_utf8_lossy(&output.stdout)).unwrap_or_else(|| {
                eprintln!("Unexpected plugin extras output; installing {LEGACY_EXTRAS:?}.");
                legacy()
            })
        }
        Ok(output) => {
            eprintln!(
                "Reading enabled plugins failed ({}); installing {LEGACY_EXTRAS:?}.",
                String::from_utf8_lossy(&output.stderr).trim()
            );
            legacy()
        }
        Err(error) => {
            eprintln!("Reading enabled plugins failed ({error}); installing {LEGACY_EXTRAS:?}.");
            legacy()
        }
    }
}

/// The JSON list `enablement.py` prints as its last line, if well formed.
pub fn parse_extras(stdout: &str) -> Option<Vec<String>> {
    let line = stdout.lines().rev().find(|line| !line.trim().is_empty())?;
    let extras: Vec<String> = serde_json::from_str(line.trim()).ok()?;
    extras
        .iter()
        .all(|extra| valid_extra(extra))
        .then_some(extras)
}

fn valid_extra(extra: &str) -> bool {
    !extra.is_empty()
        && extra
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-' || c == '_')
}

/// `--extra` arguments for `extras`, plus `dev` for development checkouts.
pub fn with_dev(mut extras: Vec<String>, development: bool) -> Vec<String> {
    if development && !extras.iter().any(|extra| extra == "dev") {
        extras.push("dev".to_string());
    }
    extras
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_the_last_json_line() {
        assert_eq!(
            parse_extras("warning: something\n[\"telegram\", \"camera\"]\n"),
            Some(vec!["telegram".to_string(), "camera".to_string()])
        );
        assert_eq!(parse_extras("[]\n"), Some(vec![]));
    }

    #[test]
    fn rejects_malformed_or_unsafe_output() {
        assert_eq!(parse_extras(""), None);
        assert_eq!(parse_extras("not json"), None);
        assert_eq!(parse_extras("[\"telegram; rm -rf\"]"), None);
        assert_eq!(parse_extras("[\"\"]"), None);
        assert_eq!(parse_extras("{\"extras\": []}"), None);
    }

    #[test]
    fn checkout_without_the_script_gets_the_legacy_extras() {
        let dir = env::temp_dir().join(format!("suzent-extras-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        assert_eq!(
            enabled_plugin_extras(&dir, &dir, &dir.join("missing-python")),
            vec!["social".to_string()]
        );
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn relative_data_dir_resolves_against_the_install_root() {
        // Run serially with any other test touching SUZENT_DATA_DIR: there is none.
        let previous = env::var("SUZENT_DATA_DIR").ok();
        env::set_var("SUZENT_DATA_DIR", "user-data");
        let root = env::temp_dir().join("suzent-live-install");
        let state = plugin_state_file(&root);
        match previous {
            Some(value) => env::set_var("SUZENT_DATA_DIR", value),
            None => env::remove_var("SUZENT_DATA_DIR"),
        }
        assert_eq!(
            state,
            root.join("user-data").join("config").join("plugins.json")
        );
    }

    #[test]
    fn data_dir_expands_a_leading_tilde_like_the_backend() {
        let home = Path::new("/home/suzy");
        assert_eq!(data_dir(None, home), home.join(".suzent"));
        assert_eq!(data_dir(Some("  ".into()), home), home.join(".suzent"));
        assert_eq!(data_dir(Some("~".into()), home), home.to_path_buf());
        assert_eq!(
            data_dir(Some("~/suzent-data".into()), home),
            home.join("suzent-data")
        );
        assert_eq!(
            data_dir(Some("~\\suzent-data".into()), home),
            home.join("suzent-data")
        );
        assert_eq!(
            data_dir(Some("/srv/suzent".into()), home),
            PathBuf::from("/srv/suzent")
        );
        // Only a leading "~/" is a home reference, as in os.path.expanduser.
        assert_eq!(
            data_dir(Some("data/~x".into()), home),
            PathBuf::from("data/~x")
        );
    }

    #[test]
    fn data_dir_social_config_wins_over_the_checkout_copy() {
        let base = env::temp_dir().join(format!("suzent-social-{}", std::process::id()));
        let root = base.join("install");
        let state = base.join("data").join("config").join("plugins.json");
        std::fs::create_dir_all(root.join("config")).unwrap();
        std::fs::create_dir_all(state.parent().unwrap()).unwrap();
        let user = state.with_file_name("social.json");
        let checkout = root.join("config").join("social.json");

        assert_eq!(pick_social_file(&state, &root), user);
        std::fs::write(&checkout, "{}").unwrap();
        assert_eq!(pick_social_file(&state, &root), checkout);
        std::fs::write(&user, "{}").unwrap();
        assert_eq!(pick_social_file(&state, &root), user);
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn dev_is_added_once_for_development_checkouts() {
        assert_eq!(with_dev(vec![], true), vec!["dev".to_string()]);
        assert_eq!(
            with_dev(vec!["dev".to_string()], true),
            vec!["dev".to_string()]
        );
        assert_eq!(
            with_dev(vec!["camera".to_string()], false),
            vec!["camera".to_string()]
        );
    }
}
