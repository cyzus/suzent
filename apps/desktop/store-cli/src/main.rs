//! `resources\bin\suzent.exe` in the Microsoft Store package.
//!
//! The package's `suzent` execution alias points here, because an alias must
//! name an exe (the NSIS install puts `suzent.cmd` on PATH instead). It runs
//! the bundled runtime's CLI with the same environment the app gives its
//! backend. The app also calls `suzent.exe --startup-task <status|enable|disable>`
//! for Settings > Background service: a packaged app starts at login through
//! the manifest's StartupTask, which only a process inside the package can
//! switch, and this exe is one.

use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

mod startup_task;

/// Store-owned commands: the CLI must not try to update a package install.
const STORE_UPDATES: &str = "This Suzent is updated through the Microsoft Store.";

fn main() -> ExitCode {
    let args: Vec<OsString> = std::env::args_os().skip(1).collect();
    if args.first().is_some_and(|arg| arg == "--startup-task") {
        let action = args.get(1).and_then(|a| a.to_str()).unwrap_or("status");
        return report(startup_task::run(action));
    }
    if args
        .first()
        .and_then(|arg| arg.to_str())
        .is_some_and(is_store_managed_command)
    {
        eprintln!("{STORE_UPDATES}");
        return ExitCode::from(1);
    }
    let Some(resources) = resources_dir() else {
        eprintln!("Cannot find the Suzent resources next to this command.");
        return ExitCode::from(1);
    };
    ignore_ctrl_c();
    match cli_command(&resources, &data_dir(), &args).status() {
        Ok(status) => ExitCode::from(status.code().unwrap_or(1).clamp(0, 255) as u8),
        Err(error) => {
            eprintln!("Cannot start the bundled Python: {error}");
            ExitCode::from(1)
        }
    }
}

fn report(result: Result<serde_json::Value, String>) -> ExitCode {
    match result {
        Ok(value) => {
            println!("{value}");
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("{error}");
            ExitCode::from(1)
        }
    }
}

fn is_store_managed_command(command: &str) -> bool {
    matches!(command, "update" | "upgrade" | "repair")
}

/// `<package>\resources`, the parent of this exe's `bin` folder.
fn resources_dir() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let resources = exe.parent()?.parent()?.to_path_buf();
    python_in(&resources).is_file().then_some(resources)
}

fn python_in(resources: &Path) -> PathBuf {
    resources.join("runtime").join("python").join("python.exe")
}

/// Where the app keeps its data; `%LOCALAPPDATA%` is virtualized per package,
/// so caches go here too.
fn data_dir() -> PathBuf {
    if let Some(dir) = std::env::var_os("SUZENT_DATA_DIR").filter(|d| !d.is_empty()) {
        return PathBuf::from(dir);
    }
    let home = std::env::var_os("USERPROFILE")
        .or_else(|| std::env::var_os("HOME"))
        .map(PathBuf::from)
        .unwrap_or_default();
    home.join(".suzent")
}

/// The same environment `bundledPythonEnv` (apps/desktop/src/layout.ts) gives
/// the backend.
fn cli_command(resources: &Path, data_dir: &Path, args: &[OsString]) -> Command {
    let mut command = Command::new(python_in(resources));
    command
        .arg("-m")
        .arg("suzent.cli")
        .args(args)
        .env("PYTHONNOUSERSITE", "1")
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("SUZENT_PACKAGED", "1")
        .env("SUZENT_PROJECT_DIR", resources.join("suzent"));
    if let Some(package) = resources.parent() {
        command.env("SUZENT_PACKAGED_UI", package.join("SUZENT.exe"));
    }
    for (key, sub) in [
        ("PLAYWRIGHT_BROWSERS_PATH", "ms-playwright"),
        ("UV_CACHE_DIR", "uv-cache"),
    ] {
        if std::env::var_os(key).is_none() {
            command.env(key, data_dir.join(sub));
        }
    }
    command
}

/// Ctrl+C reaches the Python child through the shared console; this process
/// waits for it to exit instead of dying first and returning the prompt.
#[cfg(windows)]
fn ignore_ctrl_c() {
    use windows_sys::Win32::System::Console::SetConsoleCtrlHandler;
    unsafe {
        SetConsoleCtrlHandler(None, 1);
    }
}

#[cfg(not(windows))]
fn ignore_ctrl_c() {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn store_owns_update_commands() {
        assert!(is_store_managed_command("update"));
        assert!(is_store_managed_command("repair"));
        assert!(!is_store_managed_command("chat"));
    }

    #[test]
    fn cli_runs_the_bundled_runtime_with_the_app_environment() {
        let resources = Path::new("pkg").join("resources");
        let command = cli_command(&resources, Path::new("data"), &["status".into()]);
        assert_eq!(command.get_program(), python_in(&resources).as_os_str());
        let args: Vec<_> = command.get_args().collect();
        assert_eq!(args, ["-m", "suzent.cli", "status"]);
        let env: Vec<_> = command.get_envs().collect();
        let value = |key: &str| {
            env.iter()
                .find(|(k, _)| *k == key)
                .and_then(|(_, v)| *v)
                .map(PathBuf::from)
        };
        assert_eq!(value("SUZENT_PROJECT_DIR"), Some(resources.join("suzent")));
        assert_eq!(
            value("SUZENT_PACKAGED_UI"),
            Some(Path::new("pkg").join("SUZENT.exe"))
        );
    }
}
