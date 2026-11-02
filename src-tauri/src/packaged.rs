//! Packaged (MSIX / Microsoft Store) mode.
//!
//! A packaged build ships its own Python runtime and read-only resources next
//! to the Tauri executable:
//!
//! ```text
//! <exe_dir>\
//!   suzent.exe                  this Tauri app (the manifest's Executable)
//!   AppxManifest.xml
//!   runtime\python\python.exe   relocatable CPython with Suzent installed
//!   app\config\                 tracked config (providers.json, ...)
//!   app\skills\                 bundled skills
//!   app\plugins\                bundled plugins
//! ```
//!
//! The presence of `runtime\python\python.exe` is what marks a packaged build
//! (`SUZENT_PACKAGED=1` forces it for testing). In packaged mode:
//!
//! - the backend is the bundled Python (`-m suzent.server`) with
//!   `SUZENT_PROJECT_DIR=<exe_dir>\app`; no repo checkout, `.venv` or uv;
//! - only backends reporting `source_root: null` (another packaged install)
//!   are attached to; a dev/source backend is never shared;
//! - the self-updater and installer are disabled (the Store updates the app);
//! - "start at login" uses the package's `StartupTask` instead of the Python
//!   service registration.
//!
//! The install directory is read-only and `%LOCALAPPDATA%` is virtualized per
//! package, so all writable state stays in the user data dir (`~/.suzent`).

use std::path::{Path, PathBuf};

/// Must match `<uap5:StartupTask TaskId="...">` in
/// `packaging/msix/AppxManifest.template.xml`.
pub const STARTUP_TASK_ID: &str = "SuzentStartup";

/// Error returned by update/installer commands in packaged builds.
pub const STORE_UPDATES: &str = "This Suzent build is updated through the Microsoft Store.";

fn exe_dir() -> Option<PathBuf> {
    std::env::current_exe()
        .ok()?
        .parent()
        .map(Path::to_path_buf)
}

fn python_in(exe_dir: &Path) -> Option<PathBuf> {
    let name = if cfg!(windows) {
        "python.exe"
    } else {
        "bin/python3"
    };
    let py = exe_dir.join("runtime").join("python").join(name);
    py.is_file().then_some(py)
}

fn resources_in(exe_dir: &Path) -> Option<PathBuf> {
    let dir = exe_dir.join("app");
    dir.is_dir().then_some(dir)
}

/// The bundled `runtime\python\python.exe` next to the running exe, if any.
pub fn packaged_python() -> Option<PathBuf> {
    python_in(&exe_dir()?)
}

/// The bundled read-only resources dir (`<exe_dir>\app`), if any. Passed to
/// the backend as `SUZENT_PROJECT_DIR`.
pub fn app_resources_dir() -> Option<PathBuf> {
    resources_in(&exe_dir()?)
}

/// A command for the bundled python with the packaged-mode environment:
/// bundled resources via `SUZENT_PROJECT_DIR`, no bytecode writes into the
/// read-only install dir, no user site-packages, and the shared caches kept
/// in `data_dir` because `%LOCALAPPDATA%` is virtualized per package. Used for
/// both the backend and CLI invocations through the execution alias.
pub fn python_command(python: &Path, data_dir: &Path) -> std::process::Command {
    let mut cmd = std::process::Command::new(python);
    // The same data dir as this app (honours the build-time name override).
    cmd.env("SUZENT_DATA_DIR", data_dir)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONNOUSERSITE", "1");
    if let Some(app_dir) = app_resources_dir() {
        cmd.env("SUZENT_PROJECT_DIR", app_dir);
    }
    for (key, sub) in [
        ("PLAYWRIGHT_BROWSERS_PATH", "ms-playwright"),
        ("UV_CACHE_DIR", "uv-cache"),
    ] {
        if std::env::var_os(key).is_none() {
            cmd.env(key, data_dir.join(sub));
        }
    }
    cmd
}

/// CLI commands that update or reinstall a workspace install. The Store owns
/// a packaged install, so these are refused instead of forwarded.
pub fn is_store_managed_command(command: &str) -> bool {
    matches!(command, "update" | "upgrade" | "repair")
}

/// True for packaged builds: a bundled runtime exists, or `SUZENT_PACKAGED=1`.
pub fn is_packaged() -> bool {
    std::env::var("SUZENT_PACKAGED").is_ok_and(|value| value.trim() == "1")
        || packaged_python().is_some()
}

/// Whether a packaged build may attach to the backend that sent this
/// `/health` payload: only another packaged (non-editable) install, which
/// reports `source_root: null`.
pub fn may_attach(payload: &serde_json::Value) -> bool {
    payload
        .get("source_root")
        .is_none_or(serde_json::Value::is_null)
}

/// Identity check for packaged mode. There is no source root to compare, so
/// only app, status and version are matched.
pub fn validate_backend_identity(payload: &serde_json::Value, port: u16) -> Result<(), String> {
    let field = |key: &str| payload.get(key).and_then(|value| value.as_str());
    let version = field("version");
    if field("app") == Some("suzent")
        && field("status") == Some("ok")
        && version == Some(env!("CARGO_PKG_VERSION"))
        && may_attach(payload)
    {
        return Ok(());
    }
    Err(format!(
        "Backend on port {port} (version {}) is not this packaged Suzent (version {}). Stop the other installation or choose a different SUZENT_PORT; no process was stopped.",
        version.unwrap_or("unknown"),
        env!("CARGO_PKG_VERSION"),
    ))
}

/// "Start at login" through the package's `Windows.ApplicationModel.StartupTask`.
#[cfg(windows)]
pub mod startup_task {
    use super::STARTUP_TASK_ID;
    use windows::core::HSTRING;
    use windows::ApplicationModel::{StartupTask, StartupTaskState};

    /// Simplified task state reported to the UI.
    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum State {
        Enabled,
        Disabled,
        DisabledByUser,
        DisabledByPolicy,
        EnabledByPolicy,
    }

    impl State {
        pub fn is_enabled(self) -> bool {
            matches!(self, State::Enabled | State::EnabledByPolicy)
        }

        /// A message for states the app cannot change itself.
        pub fn error(self) -> Option<String> {
            match self {
                State::DisabledByUser => Some(
                    "Start at login was turned off in Windows Settings > Apps > Startup (or Task Manager). Turn Suzent back on there."
                        .to_string(),
                ),
                State::DisabledByPolicy => {
                    Some("Start at login is disabled by your organization's policy.".to_string())
                }
                _ => None,
            }
        }
    }

    fn convert(state: StartupTaskState) -> State {
        match state {
            StartupTaskState::Enabled => State::Enabled,
            StartupTaskState::DisabledByUser => State::DisabledByUser,
            StartupTaskState::DisabledByPolicy => State::DisabledByPolicy,
            StartupTaskState::EnabledByPolicy => State::EnabledByPolicy,
            _ => State::Disabled,
        }
    }

    fn task() -> Result<StartupTask, String> {
        StartupTask::GetAsync(&HSTRING::from(STARTUP_TASK_ID))
            .and_then(|op| op.get())
            .map_err(|error| format!("Startup task '{STARTUP_TASK_ID}' is unavailable: {error}"))
    }

    pub fn state() -> Result<State, String> {
        let state = task()?
            .State()
            .map_err(|error| format!("Cannot read startup task state: {error}"))?;
        Ok(convert(state))
    }

    /// Enable or disable the task and return the resulting state. Windows may
    /// refuse to enable it (user or policy); the caller reports that.
    pub fn set_enabled(enabled: bool) -> Result<State, String> {
        let task = task()?;
        if enabled {
            let state = task
                .RequestEnableAsync()
                .and_then(|op| op.get())
                .map_err(|error| format!("Cannot enable startup task: {error}"))?;
            Ok(convert(state))
        } else {
            task.Disable()
                .map_err(|error| format!("Cannot disable startup task: {error}"))?;
            state()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::fs;

    #[test]
    fn detects_bundled_layout() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path();
        assert_eq!(python_in(root), None);
        assert_eq!(resources_in(root), None);

        let rel = if cfg!(windows) {
            "runtime/python/python.exe"
        } else {
            "runtime/python/bin/python3"
        };
        let py = root.join(rel);
        fs::create_dir_all(py.parent().unwrap()).unwrap();
        fs::write(&py, b"").unwrap();
        fs::create_dir_all(root.join("app").join("config")).unwrap();

        assert_eq!(python_in(root), Some(py));
        assert_eq!(resources_in(root), Some(root.join("app")));
    }

    #[test]
    fn python_dir_alone_is_not_packaged() {
        let temp = tempfile::tempdir().unwrap();
        fs::create_dir_all(temp.path().join("runtime").join("python")).unwrap();
        assert_eq!(python_in(temp.path()), None);
    }

    #[test]
    fn attaches_only_to_packaged_backends() {
        let base = |root: serde_json::Value| {
            json!({
                "app": "suzent",
                "status": "ok",
                "version": env!("CARGO_PKG_VERSION"),
                "source_root": root,
            })
        };
        let packaged = base(serde_json::Value::Null);
        let dev = base(json!("D:\\workspace\\suzent"));

        assert!(may_attach(&packaged));
        assert!(may_attach(&json!({"app": "suzent"})));
        assert!(!may_attach(&dev));

        assert!(validate_backend_identity(&packaged, 25314).is_ok());
        assert!(validate_backend_identity(&dev, 25314).is_err());
        let mut old = packaged.clone();
        old["version"] = json!("0.0.0");
        assert!(validate_backend_identity(&old, 25314)
            .unwrap_err()
            .contains("0.0.0"));
    }

    #[test]
    fn store_owns_update_commands() {
        for command in ["update", "upgrade", "repair"] {
            assert!(is_store_managed_command(command));
        }
        for command in ["start", "logs", "--help", "service"] {
            assert!(!is_store_managed_command(command));
        }
    }

    #[test]
    fn startup_task_id_matches_manifest_template() {
        let template = include_str!("../../packaging/msix/AppxManifest.template.xml");
        assert!(template.contains(&format!("TaskId=\"{STARTUP_TASK_ID}\"")));
    }
}
