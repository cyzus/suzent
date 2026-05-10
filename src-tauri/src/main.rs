// Prevents additional console window on Windows in release builds
// REMOVED: #![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;

use backend::BackendProcess;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use tauri::{Emitter, Manager, State};

struct AppState {
    backend: Mutex<Option<BackendProcess>>,
}

#[tauri::command]
fn get_backend_port(state: State<AppState>) -> Result<u16, String> {
    let backend_guard = state
        .backend
        .lock()
        .map_err(|e| format!("Lock error: {}", e))?;

    if let Some(backend) = &*backend_guard {
        Ok(backend.port)
    } else {
        Err("Backend not ready yet".to_string())
    }
}

#[tauri::command]
fn check_for_update() -> Result<String, String> {
    let repo_dir = backend::find_repo_dir();
    let uv_exe = backend::find_uv();

    let output = Command::new(&uv_exe)
        .args([
            "run",
            "--no-sync",
            "suzent",
            "check-update",
            "--json",
            "--cached",
        ])
        .current_dir(&repo_dir)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .map_err(|e| format!("Failed to check for updates: {}", e))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
        return Err(if stderr.is_empty() { stdout } else { stderr });
    }

    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

#[tauri::command]
fn start_update_and_restart(app_handle: tauri::AppHandle) -> Result<(), String> {
    let repo_dir = backend::find_repo_dir();
    let uv_exe = backend::find_uv();
    let ui_exe = find_relaunch_exe(&repo_dir).map_err(|e| e.to_string())?;
    let script = write_update_script(&repo_dir, &uv_exe, &ui_exe)?;

    spawn_update_script(&script)?;

    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(250));
        app_handle.exit(0);
    });

    Ok(())
}

fn find_relaunch_exe(repo_dir: &Path) -> Result<PathBuf, std::io::Error> {
    let bundled = if cfg!(windows) {
        repo_dir.join("bin").join("suzent-ui.exe")
    } else {
        repo_dir.join("bin").join("suzent-ui")
    };
    if bundled.exists() {
        return Ok(bundled);
    }
    std::env::current_exe()
}

fn write_update_script(repo_dir: &Path, uv_exe: &Path, ui_exe: &Path) -> Result<PathBuf, String> {
    let runtime_dir = backend::find_data_dir().join("runtime");
    std::fs::create_dir_all(&runtime_dir)
        .map_err(|e| format!("Failed to create runtime dir: {}", e))?;

    if cfg!(windows) {
        let script = runtime_dir.join("suzent-update-and-restart.cmd");
        let contents = format!(
            "@echo off\r\n\
title Suzent Update\r\n\
timeout /t 1 /nobreak >nul\r\n\
cd /d \"{}\"\r\n\
\"{}\" run --no-sync suzent update\r\n\
if errorlevel 1 (\r\n\
  echo.\r\n\
  echo Suzent update failed. Press any key to close.\r\n\
  pause >nul\r\n\
  exit /b 1\r\n\
)\r\n\
start \"\" \"{}\"\r\n\
exit /b 0\r\n",
            repo_dir.display(),
            uv_exe.display(),
            ui_exe.display()
        );
        std::fs::File::create(&script)
            .and_then(|mut file| file.write_all(contents.as_bytes()))
            .map_err(|e| format!("Failed to write update script: {}", e))?;
        return Ok(script);
    }

    let script = runtime_dir.join("suzent-update-and-restart.sh");
    let contents = format!(
        "#!/bin/sh\n\
sleep 1\n\
cd \"{}\" || exit 1\n\
\"{}\" run --no-sync suzent update\n\
status=$?\n\
if [ \"$status\" -ne 0 ]; then\n\
  printf '\\nSuzent update failed. Press Enter to close.'\n\
  read _\n\
  exit \"$status\"\n\
fi\n\
\"{}\" >/dev/null 2>&1 &\n",
        repo_dir.display(),
        uv_exe.display(),
        ui_exe.display()
    );
    std::fs::File::create(&script)
        .and_then(|mut file| file.write_all(contents.as_bytes()))
        .map_err(|e| format!("Failed to write update script: {}", e))?;

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut perms = std::fs::metadata(&script)
            .map_err(|e| format!("Failed to read update script permissions: {}", e))?
            .permissions();
        perms.set_mode(0o755);
        std::fs::set_permissions(&script, perms)
            .map_err(|e| format!("Failed to set update script permissions: {}", e))?;
    }

    Ok(script)
}

fn spawn_update_script(script: &Path) -> Result<(), String> {
    if cfg!(windows) {
        Command::new("cmd")
            .args(["/C", "start", "Suzent Update"])
            .arg(script)
            .current_dir(script.parent().unwrap_or_else(|| Path::new(".")))
            .spawn()
            .map_err(|e| format!("Failed to start update script: {}", e))?;
    } else {
        Command::new("sh")
            .arg(script)
            .current_dir(script.parent().unwrap_or_else(|| Path::new(".")))
            .spawn()
            .map_err(|e| format!("Failed to start update script: {}", e))?;
    }
    Ok(())
}

fn main() {
    let args: Vec<String> = std::env::args().collect();

    // CLI mode: delegate to `uv run suzent <args>` in the repo directory.
    if args.len() > 1 {
        let repo_dir = backend::find_repo_dir();
        let uv_exe = backend::find_uv();

        let status = std::process::Command::new(&uv_exe)
            .arg("run")
            .arg("--no-sync")
            .arg("suzent")
            .args(&args[1..])
            .current_dir(&repo_dir)
            .status();

        match status {
            Ok(s) => std::process::exit(s.code().unwrap_or(1)),
            Err(e) => {
                eprintln!("Failed to run 'uv run suzent': {}", e);
                eprintln!("Make sure uv is installed and SUZENT is set up correctly.");
                std::process::exit(1);
            }
        }
    }

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .setup(|app| {
            let window = app
                .get_webview_window("main")
                .ok_or("Failed to get main window")?;

            app.manage(AppState {
                backend: Mutex::new(None),
            });

            let app_handle = app.handle().clone();

            std::thread::spawn(move || match get_backend_config(&app_handle) {
                Ok((port, backend)) => {
                    println!("Backend configured on port {}", port);

                    if let Some(state) = app_handle.try_state::<AppState>() {
                        if let Ok(mut guard) = state.backend.lock() {
                            *guard = Some(backend);
                        }
                    }

                    let js = format!(
                        r#"
window.__SUZENT_BACKEND_PORT__ = {port};
try {{ sessionStorage.setItem('SUZENT_PORT', '{port}'); }} catch (e) {{}}
try {{ localStorage.setItem('SUZENT_PORT', '{port}'); }} catch (e) {{}}
"#
                    );
                    if let Err(e) = window.eval(&js) {
                        eprintln!("Failed to inject backend port: {}", e);
                        let _ = window.emit(
                            "backend-error",
                            format!("Failed to inject backend port: {}", e),
                        );
                    } else {
                        let _ = app_handle.emit("backend-ready", port);
                    }
                }
                Err(e) => {
                    eprintln!("Failed to start backend: {}", e);
                    let _ = window.emit("backend-error", e);
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_backend_port,
            check_for_update,
            start_update_and_restart
        ])
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(debug_assertions)]
fn read_port_file() -> Option<u16> {
    let port_file = backend::find_data_dir().join("runtime").join("server.port");
    let text = std::fs::read_to_string(&port_file).ok()?;
    text.trim().parse::<u16>().ok()
}

/// Dev mode: expect a manually-started backend; just read the port from SUZENT_PORT.
#[cfg(debug_assertions)]
fn get_backend_config(_app_handle: &tauri::AppHandle) -> Result<(u16, BackendProcess), String> {
    let port = std::env::var("SUZENT_PORT")
        .unwrap_or_else(|_| "0".to_string())
        .parse::<u16>()
        .unwrap_or(0);

    // 0 means "read from server.port file written by the backend at startup"
    let resolved = if port == 0 {
        read_port_file().unwrap_or(25314)
    } else {
        port
    };
    println!("Dev mode: connecting to backend on port {}", resolved);
    println!("If nothing shows up, start the backend first with: suzent serve");
    Ok((resolved, BackendProcess::new()))
}

/// Release mode: launch the backend via `uv run python -m suzent.server`.
#[cfg(not(debug_assertions))]
fn get_backend_config(app_handle: &tauri::AppHandle) -> Result<(u16, BackendProcess), String> {
    let _ = app_handle;
    let repo_dir = backend::find_repo_dir();
    let uv_exe = backend::find_uv();

    let port = std::env::var("SUZENT_PORT")
        .unwrap_or_else(|_| "0".to_string())
        .parse::<u16>()
        .unwrap_or(0);

    let mut bp = BackendProcess::new();
    let actual_port = bp.start_with_uv(&uv_exe, &repo_dir, port)?;
    Ok((actual_port, bp))
}
