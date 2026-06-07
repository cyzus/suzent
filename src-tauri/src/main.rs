// Prevents an extra console window on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;

use backend::BackendProcess;
use serde::{Deserialize, Serialize};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use tauri::{Emitter, Manager, State};

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

struct AppState {
    backend: Mutex<Option<BackendProcess>>,
}

#[derive(Clone, Serialize)]
struct BootstrapStatus {
    required: bool,
    workspace_dir: String,
    installer_available: bool,
    installer_path: Option<String>,
}

#[derive(Deserialize)]
struct BootstrapStageRequest {
    stage: String,
    dir: Option<String>,
}

#[derive(Deserialize)]
struct InstallWorkspaceRequest {
    dir: String,
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
    let repo_dir = backend::find_install_workspace_dir();
    let uv_exe = backend::find_uv();

    let mut command = Command::new(&uv_exe);
    command
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
        .stderr(Stdio::piped());
    hide_command_window(&mut command);
    let output = command
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
    let repo_dir = backend::find_install_workspace_dir();
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

#[tauri::command]
fn bootstrap_status(app_handle: tauri::AppHandle) -> BootstrapStatus {
    build_bootstrap_status(Some(&app_handle))
}

fn build_bootstrap_status(app_handle: Option<&tauri::AppHandle>) -> BootstrapStatus {
    let repo_dir = backend::find_install_workspace_dir();
    let installer = find_bootstrap_installer(app_handle);
    let forced = std::env::var("SUZENT_FORCE_BOOTSTRAP")
        .map(|value| value == "1" || value.eq_ignore_ascii_case("true"))
        .unwrap_or(false);
    let dev_without_install_target = cfg!(debug_assertions)
        && std::env::var("SUZENT_DIR")
            .unwrap_or_default()
            .trim()
            .is_empty();
    BootstrapStatus {
        required: forced
            || (!dev_without_install_target && !backend::is_workspace_bootstrapped(&repo_dir)),
        workspace_dir: repo_dir.display().to_string(),
        installer_available: installer.is_some(),
        installer_path: installer.map(|path| path.display().to_string()),
    }
}

#[tauri::command]
fn bootstrap_manifest(app_handle: tauri::AppHandle) -> Result<String, String> {
    let installer = find_bootstrap_installer(Some(&app_handle))
        .ok_or_else(|| "Suzent installer helper was not found.".to_string())?;
    run_installer_json(&installer, &["--manifest"])
}

#[tauri::command]
fn run_bootstrap_stage(
    app_handle: tauri::AppHandle,
    request: BootstrapStageRequest,
) -> Result<String, String> {
    let installer = find_bootstrap_installer(Some(&app_handle))
        .ok_or_else(|| "Suzent installer helper was not found.".to_string())?;
    let workspace = request
        .dir
        .as_deref()
        .filter(|dir| !dir.trim().is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(backend::find_install_workspace_dir);
    let workspace_arg = workspace.display().to_string();
    run_installer_json(
        &installer,
        &[
            "--stage",
            request.stage.as_str(),
            "--json",
            "--non-interactive",
            "--dir",
            workspace_arg.as_str(),
        ],
    )
}

#[tauri::command]
fn set_install_workspace(
    app_handle: tauri::AppHandle,
    request: InstallWorkspaceRequest,
) -> Result<BootstrapStatus, String> {
    let dir = request.dir.trim();
    if dir.is_empty() {
        return Err("Install directory cannot be empty.".to_string());
    }
    backend::persist_install_workspace_dir(&PathBuf::from(dir))?;
    Ok(build_bootstrap_status(Some(&app_handle)))
}

#[tauri::command]
fn retry_backend_start(app_handle: tauri::AppHandle) -> Result<(), String> {
    spawn_backend_start(app_handle);
    Ok(())
}

#[tauri::command]
fn frontend_ready(app_handle: tauri::AppHandle) -> Result<(), String> {
    let window = app_handle
        .get_webview_window("main")
        .ok_or_else(|| "Main window not found".to_string())?;
    window
        .show()
        .map_err(|e| format!("Failed to show main window: {}", e))?;
    window
        .set_focus()
        .map_err(|e| format!("Failed to focus main window: {}", e))?;
    Ok(())
}

fn find_bootstrap_installer_name() -> &'static str {
    if cfg!(windows) {
        "suzent-installer.exe"
    } else {
        "suzent-installer"
    }
}

fn find_bootstrap_installer(app_handle: Option<&tauri::AppHandle>) -> Option<PathBuf> {
    if let Ok(path) = std::env::var("SUZENT_INSTALLER_EXE") {
        let candidate = PathBuf::from(path);
        if candidate.exists() {
            return Some(candidate);
        }
    }

    let name = find_bootstrap_installer_name();
    let mut candidates = Vec::new();

    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            candidates.push(dir.join(name));
            candidates.push(dir.join("bin").join(name));
        }
    }

    if let Some(app_handle) = app_handle {
        if let Ok(resource_dir) = app_handle.path().resource_dir() {
            candidates.push(resource_dir.join(name));
            candidates.push(resource_dir.join("bin").join(name));
            candidates.push(resource_dir.join("resources").join("bin").join(name));
        }
    }

    let repo_dir = backend::find_repo_dir();
    candidates.push(
        repo_dir
            .join("apps")
            .join("suzent-installer")
            .join("target")
            .join("debug")
            .join(name),
    );
    candidates.push(
        repo_dir
            .join("apps")
            .join("suzent-installer")
            .join("target")
            .join("release")
            .join(name),
    );

    candidates.into_iter().find(|path| path.exists())
}

fn run_installer_json(installer: &Path, args: &[&str]) -> Result<String, String> {
    let mut command = Command::new(installer);
    command
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    hide_command_window(&mut command);
    let output = command
        .output()
        .map_err(|e| format!("Failed to run installer helper: {}", e))?;

    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();

    if output.status.success() {
        return Ok(stdout);
    }

    if !stdout.is_empty() {
        return Err(stdout);
    }
    if !stderr.is_empty() {
        return Err(stderr);
    }
    Err(format!(
        "Installer helper exited with code {}",
        output.status.code().unwrap_or(1)
    ))
}

fn spawn_backend_start(app_handle: tauri::AppHandle) {
    std::thread::spawn(move || {
        let Some(window) = app_handle.get_webview_window("main") else {
            return;
        };

        match get_backend_config(&app_handle) {
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
                if e == "bootstrap-required" {
                    let _ = app_handle.emit(
                        "bootstrap-required",
                        build_bootstrap_status(Some(&app_handle)),
                    );
                } else {
                    let _ = window.emit("backend-error", e);
                }
            }
        }
    });
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
        let mut command = Command::new("cmd");
        command
            .args(["/C", "start", "Suzent Update"])
            .arg(script)
            .current_dir(script.parent().unwrap_or_else(|| Path::new(".")));
        hide_command_window(&mut command);
        command
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

#[cfg(windows)]
fn hide_command_window(command: &mut Command) {
    use std::os::windows::process::CommandExt;
    command.creation_flags(CREATE_NO_WINDOW);
}

#[cfg(not(windows))]
fn hide_command_window(_command: &mut Command) {}

fn main() {
    let args: Vec<String> = std::env::args().collect();

    // CLI mode: delegate to `uv run suzent <args>` in the repo directory.
    if args.len() > 1 {
        let repo_dir = backend::find_repo_dir();
        let uv_exe = backend::find_uv();

        let mut command = std::process::Command::new(&uv_exe);
        command
            .arg("run")
            .arg("--no-sync")
            .arg("suzent")
            .args(&args[1..])
            .current_dir(&repo_dir);
        let status = command.status();

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
            app.manage(AppState {
                backend: Mutex::new(None),
            });

            let status = build_bootstrap_status(Some(app.handle()));
            if status.required {
                let app_handle = app.handle().clone();
                std::thread::spawn(move || {
                    let _ = app_handle.emit("bootstrap-required", status);
                });
            } else {
                spawn_backend_start(app.handle().clone());
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_backend_port,
            check_for_update,
            start_update_and_restart,
            bootstrap_status,
            bootstrap_manifest,
            run_bootstrap_stage,
            set_install_workspace,
            retry_backend_start,
            frontend_ready
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
fn get_backend_config(app_handle: &tauri::AppHandle) -> Result<(u16, BackendProcess), String> {
    let _ = app_handle;

    let install_test_mode = std::env::var("SUZENT_DIR")
        .map(|dir| !dir.trim().is_empty())
        .unwrap_or(false)
        || std::env::var("SUZENT_FORCE_BOOTSTRAP")
            .map(|value| value == "1" || value.eq_ignore_ascii_case("true"))
            .unwrap_or(false);

    if install_test_mode {
        let repo_dir = backend::find_install_workspace_dir();
        if !backend::is_workspace_bootstrapped(&repo_dir) {
            return Err("bootstrap-required".to_string());
        }

        let uv_exe = backend::find_uv();
        let port = std::env::var("SUZENT_PORT")
            .unwrap_or_else(|_| "0".to_string())
            .parse::<u16>()
            .unwrap_or(0);

        println!(
            "Dev install-test mode: starting backend from {}",
            repo_dir.display()
        );
        let mut bp = BackendProcess::new();
        let actual_port = bp.start_with_uv(&uv_exe, &repo_dir, port)?;
        return Ok((actual_port, bp));
    }

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
    let repo_dir = backend::find_install_workspace_dir();
    let uv_exe = backend::find_uv();

    if !backend::is_workspace_bootstrapped(&repo_dir) {
        return Err("bootstrap-required".to_string());
    }

    let port = std::env::var("SUZENT_PORT")
        .unwrap_or_else(|_| "0".to_string())
        .parse::<u16>()
        .unwrap_or(0);

    let mut bp = BackendProcess::new();
    let actual_port = bp.start_with_uv(&uv_exe, &repo_dir, port)?;
    Ok((actual_port, bp))
}
