//! Suzent for Windows setup: draws its own window, then runs the
//! electron-builder package it carries silently into the folder the user
//! picks. Updates later go through that package alone (electron-updater), so
//! this program only matters for the first install.
//!
//! `--silent [--dir PATH]` installs without a window, for scripts and CI.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod install;
mod payload;

use std::path::{Path, PathBuf};
use std::sync::Mutex;

use serde::Serialize;
use tauri::{Emitter, Manager, State};

struct Setup {
    exe: PathBuf,
    payload: Option<payload::Payload>,
    installed: Mutex<Option<PathBuf>>,
}

#[derive(Serialize)]
struct Info {
    version: String,
    default_dir: String,
    data_dir: String,
    ready: bool,
}

#[tauri::command]
fn info(setup: State<'_, Setup>) -> Info {
    Info {
        version: setup
            .payload
            .as_ref()
            .map(|p| p.meta.version.clone())
            .unwrap_or_default(),
        default_dir: install::default_dir().display().to_string(),
        data_dir: dirs::home_dir()
            .map(|home| home.join(".suzent").display().to_string())
            .unwrap_or_else(|| "~\\.suzent".into()),
        ready: setup.payload.is_some(),
    }
}

/// None when `dir` is fine, else a reason code the page words.
#[tauri::command]
fn check_dir(dir: String) -> Option<&'static str> {
    install::problem_with(Path::new(dir.trim()))
}

#[tauri::command]
async fn install(app: tauri::AppHandle, dir: String) -> Result<(), String> {
    let dir = PathBuf::from(dir.trim());
    if let Some(problem) = install::problem_with(&dir) {
        return Err(problem.into());
    }
    let setup = app.state::<Setup>();
    let Some(payload) = setup.payload.clone() else {
        return Err("no_package".into());
    };
    let exe = setup.exe.clone();
    let emitter = app.clone();
    tauri::async_runtime::spawn_blocking(move || {
        run_install(&exe, &payload, &dir, move |progress| {
            let _ = emitter.emit("setup://progress", progress);
        })
        .map(|()| dir)
    })
    .await
    .map_err(|error| error.to_string())?
    .map(|dir| {
        *setup.installed.lock().unwrap() = Some(dir);
    })
    .map_err(|error| error.to_string())
}

#[tauri::command]
fn finish(app: tauri::AppHandle, setup: State<'_, Setup>, launch: bool) -> Result<(), String> {
    if launch {
        if let Some(dir) = setup.installed.lock().unwrap().as_ref() {
            install::launch(dir).map_err(|error| error.to_string())?;
        }
    }
    app.exit(0);
    Ok(())
}

fn run_install(
    exe: &Path,
    payload: &payload::Payload,
    dir: &Path,
    report: impl Fn(install::Progress) + Send + Sync + 'static,
) -> std::io::Result<()> {
    let staging = std::env::temp_dir().join(format!("suzent-setup-{}", std::process::id()));
    std::fs::create_dir_all(&staging)?;
    let package = staging.join(if cfg!(windows) {
        "suzent-package.exe"
    } else {
        "suzent-package"
    });
    payload::extract(exe, payload, &package)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&package, std::fs::Permissions::from_mode(0o755))?;
    }
    let result = install::run(&package, dir, payload.meta.unpacked_bytes, report);
    let _ = std::fs::remove_dir_all(&staging);
    result
}

fn silent(exe: &Path, payload: Option<payload::Payload>, args: &[String]) -> i32 {
    let Some(payload) = payload else {
        eprintln!("This setup carries no Suzent package.");
        return 2;
    };
    let dir = args
        .iter()
        .position(|arg| arg == "--dir")
        .and_then(|at| args.get(at + 1))
        .map(PathBuf::from)
        .unwrap_or_else(install::default_dir);
    if let Some(problem) = install::problem_with(&dir) {
        eprintln!("Cannot install into {}: {problem}", dir.display());
        return 2;
    }
    println!(
        "Installing Suzent {} into {}",
        payload.meta.version,
        dir.display()
    );
    match run_install(exe, &payload, &dir, |p| {
        println!("{:?} {}%", p.phase, p.percent)
    }) {
        Ok(()) => {
            println!("Installed {}", dir.join(install::APP_EXE).display());
            0
        }
        Err(error) => {
            eprintln!("Install failed: {error}");
            1
        }
    }
}

fn main() {
    let exe = std::env::current_exe().expect("setup cannot find itself");
    let payload = match payload::locate(&exe) {
        Ok(found) => found,
        Err(error) => {
            eprintln!("This setup file is damaged ({error}); download it again.");
            None
        }
    };
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.iter().any(|arg| arg == "--silent") {
        std::process::exit(silent(&exe, payload, &args));
    }
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(Setup {
            exe,
            payload,
            installed: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![info, check_dir, install, finish])
        .setup(|app| {
            if let Some(window) = app.get_webview_window("main") {
                window.show()?;
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("setup window failed to open");
}
