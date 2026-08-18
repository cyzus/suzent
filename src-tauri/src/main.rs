// Prevents an extra console window on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;

use backend::BackendProcess;
use serde::{Deserialize, Serialize};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{Emitter, Manager, State};

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

struct AppState {
    backend: Mutex<Option<BackendProcess>>,
    backend_startup_error: Mutex<Option<String>>,
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
async fn check_for_update() -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(check_for_update_blocking)
        .await
        .map_err(|error| format!("Update check task failed: {}", error))?
}

#[tauri::command]
fn get_backend_startup_error(state: State<AppState>) -> Result<Option<String>, String> {
    let error_guard = state
        .backend_startup_error
        .lock()
        .map_err(|e| format!("Lock error: {}", e))?;
    Ok(error_guard.clone())
}

fn check_for_update_blocking() -> Result<String, String> {
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
    let mut child = command
        .spawn()
        .map_err(|e| format!("Failed to check for updates: {}", e))?;

    let started_at = Instant::now();
    let status = loop {
        if let Some(status) = child
            .try_wait()
            .map_err(|e| format!("Failed to wait for update check: {}", e))?
        {
            break status;
        }
        if started_at.elapsed() >= Duration::from_secs(15) {
            let _ = child.kill();
            let _ = child.wait();
            return Err("Update check timed out after 15 seconds".to_string());
        }
        std::thread::sleep(Duration::from_millis(50));
    };

    let mut stdout = Vec::new();
    if let Some(mut pipe) = child.stdout.take() {
        pipe.read_to_end(&mut stdout)
            .map_err(|e| format!("Failed to read update check output: {}", e))?;
    }
    let mut stderr = Vec::new();
    if let Some(mut pipe) = child.stderr.take() {
        pipe.read_to_end(&mut stderr)
            .map_err(|e| format!("Failed to read update check error: {}", e))?;
    }

    if !status.success() {
        let stderr = String::from_utf8_lossy(&stderr).trim().to_string();
        let stdout = String::from_utf8_lossy(&stdout).trim().to_string();
        return Err(if stderr.is_empty() { stdout } else { stderr });
    }

    Ok(String::from_utf8_lossy(&stdout).trim().to_string())
}

#[tauri::command]
fn start_update_and_restart(
    app_handle: tauri::AppHandle,
    state: State<AppState>,
) -> Result<(), String> {
    let repo_dir = backend::find_install_workspace_dir();
    let uv_exe = backend::find_uv();
    let ui_exe = find_relaunch_exe(&repo_dir).map_err(|e| e.to_string())?;
    let restart_service = get_service_status()
        .ok()
        .and_then(|payload| serde_json::from_str::<serde_json::Value>(&payload).ok())
        .and_then(|payload| payload.get("installed").and_then(|value| value.as_bool()))
        .unwrap_or(false);
    let script = write_update_script(&repo_dir, &uv_exe, &ui_exe, restart_service)?;

    {
        let mut backend_guard = state
            .backend
            .lock()
            .map_err(|_| "Failed to lock backend state".to_string())?;
        if let Some(mut backend) = backend_guard.take() {
            backend.stop();
        }
    }

    spawn_update_script(&script)?;

    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(250));
        app_handle.exit(0);
    });

    Ok(())
}

#[tauri::command]
fn restart_app(app_handle: tauri::AppHandle, state: State<AppState>) -> Result<(), String> {
    {
        let mut backend_guard = state
            .backend
            .lock()
            .map_err(|_| "Failed to lock backend state".to_string())?;
        if let Some(mut backend) = backend_guard.take() {
            backend.stop();
        }
    }

    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(250));
        app_handle.restart();
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

fn run_service_cli(args: &[&str]) -> Result<String, String> {
    let repo_dir = backend::find_install_workspace_dir();
    let python = backend::find_venv_python(&repo_dir)
        .ok_or_else(|| "Suzent Python environment is not installed.".to_string())?;
    let mut command = Command::new(python);
    command
        .args(["-m", "suzent.cli", "service"])
        .args(args)
        .current_dir(repo_dir)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    hide_command_window(&mut command);
    let output = command
        .output()
        .map_err(|error| format!("Failed to run Suzent service command: {}", error))?;
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    if output.status.success() {
        return Ok(stdout);
    }
    Err(if stderr.is_empty() { stdout } else { stderr })
}

fn extract_json_payload(output: &str) -> Result<String, String> {
    let start = output
        .find('{')
        .ok_or_else(|| "Service status did not contain JSON.".to_string())?;
    let payload = &output[start..];
    serde_json::from_str::<serde_json::Value>(payload)
        .map_err(|error| format!("Invalid service status response: {}", error))?;
    Ok(payload.to_string())
}

#[tauri::command]
fn get_service_status() -> Result<String, String> {
    extract_json_payload(&run_service_cli(&["status", "--json"])?)
}

#[tauri::command]
fn set_service_enabled(
    app_handle: tauri::AppHandle,
    state: State<AppState>,
    enabled: bool,
) -> Result<String, String> {
    if enabled {
        run_service_cli(&["install"])?;
    } else {
        let was_attached = {
            let backend = state
                .backend
                .lock()
                .map_err(|_| "Failed to lock backend state".to_string())?;
            backend
                .as_ref()
                .map(|process| !process.is_owned())
                .unwrap_or(false)
        };
        run_service_cli(&["uninstall"])?;
        if was_attached {
            // The UI was using the service that was just disabled. Wait for the
            // fixed port to close, then restore the legacy owned-child mode so
            // disabling background operation does not strand the open window.
            for _ in 0..30 {
                if BackendProcess::attach_if_healthy(25314).is_none() {
                    break;
                }
                std::thread::sleep(Duration::from_millis(100));
            }
            let (port, backend) = get_backend_config(&app_handle)?;
            {
                let mut current = state
                    .backend
                    .lock()
                    .map_err(|_| "Failed to lock backend state".to_string())?;
                *current = Some(backend);
            }
            publish_backend_port(&app_handle, port)?;
        }
    }
    get_service_status()
}

#[tauri::command]
fn restart_background_service() -> Result<String, String> {
    run_service_cli(&["restart"])?;
    get_service_status()
}

#[tauri::command]
fn get_service_log_path() -> Result<String, String> {
    Ok(backend::find_data_dir()
        .join("runtime")
        .join("server.log")
        .display()
        .to_string())
}

fn publish_backend_port(app_handle: &tauri::AppHandle, port: u16) -> Result<(), String> {
    let window = app_handle
        .get_webview_window("main")
        .ok_or_else(|| "Main window not found".to_string())?;
    let js = format!(
        r#"
window.__SUZENT_BACKEND_PORT__ = {port};
try {{ sessionStorage.setItem('SUZENT_PORT', '{port}'); }} catch (e) {{}}
try {{ localStorage.setItem('SUZENT_PORT', '{port}'); }} catch (e) {{}}
"#
    );
    window
        .eval(&js)
        .map_err(|error| format!("Failed to inject backend port: {}", error))?;
    app_handle
        .emit("backend-ready", port)
        .map_err(|error| format!("Failed to publish backend port: {}", error))
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

    candidates.push(backend::find_data_dir().join("updater").join(name));

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

        let update_journal = backend::find_install_workspace_dir()
            .join(".suzent")
            .join("update-transaction.json");
        if update_journal.exists() {
            let error =
                "A Suzent update was interrupted. Run 'suzent repair' before starting the backend."
                    .to_string();
            if let Some(state) = app_handle.try_state::<AppState>() {
                if let Ok(mut error_guard) = state.backend_startup_error.lock() {
                    *error_guard = Some(error.clone());
                }
            }
            let _ = window.emit("backend-error", error);
            return;
        }

        if let Some(state) = app_handle.try_state::<AppState>() {
            if let Ok(mut error_guard) = state.backend_startup_error.lock() {
                *error_guard = None;
            }
        }

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
                if let Some(state) = app_handle.try_state::<AppState>() {
                    if let Ok(mut error_guard) = state.backend_startup_error.lock() {
                        *error_guard = Some(e.clone());
                    }
                }
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

fn write_update_script(
    repo_dir: &Path,
    uv_exe: &Path,
    ui_exe: &Path,
    restart_service: bool,
) -> Result<PathBuf, String> {
    let runtime_dir = backend::find_data_dir().join("runtime");
    std::fs::create_dir_all(&runtime_dir)
        .map_err(|e| format!("Failed to create runtime dir: {}", e))?;

    if cfg!(windows) {
        let script = runtime_dir.join("suzent-update-and-restart.cmd");
        let python_exe = repo_dir.join(".venv").join("Scripts").join("python.exe");
        let service_stop = if restart_service {
            format!(
                "\"{}\" -m suzent.cli service stop >nul 2>&1\r\n",
                python_exe.display()
            )
        } else {
            String::new()
        };
        let service_start = if restart_service {
            format!(
                "\"{}\" -m suzent.cli service start >nul 2>&1\r\n",
                python_exe.display()
            )
        } else {
            String::new()
        };
        let contents = format!(
            "@echo off\r\n\
title Suzent Update\r\n\
timeout /t 1 /nobreak >nul\r\n\
cd /d \"{}\"\r\n\
{}\
\"{}\" -m suzent.cli update --relaunch \"{}\"\r\n\
set \"update_status=%errorlevel%\"\r\n\
{}\
if not \"%update_status%\"==\"0\" (\r\n\
  echo.\r\n\
  echo Suzent update failed. Press any key to close.\r\n\
  pause >nul\r\n\
  exit /b %update_status%\r\n\
)\r\n\
exit /b 0\r\n",
            repo_dir.display(),
            service_stop,
            python_exe.display(),
            ui_exe.display(),
            service_start,
        );
        std::fs::File::create(&script)
            .and_then(|mut file| file.write_all(contents.as_bytes()))
            .map_err(|e| format!("Failed to write update script: {}", e))?;
        return Ok(script);
    }

    let script = runtime_dir.join("suzent-update-and-restart.sh");
    let service_stop = if restart_service {
        format!(
            "\"{}\" run --no-sync suzent service stop >/dev/null 2>&1\n",
            uv_exe.display()
        )
    } else {
        String::new()
    };
    let service_start = if restart_service {
        format!(
            "\"{}\" run --no-sync suzent service start >/dev/null 2>&1\n",
            uv_exe.display()
        )
    } else {
        String::new()
    };
    let contents = format!(
        "#!/bin/sh\n\
sleep 1\n\
cd \"{}\" || exit 1\n\
{}\
\"{}\" run --no-sync suzent update --relaunch \"{}\"\n\
status=$?\n\
{}\
if [ \"$status\" -ne 0 ]; then\n\
  printf '\\nSuzent update failed. Press Enter to close.'\n\
  read _\n\
  exit \"$status\"\n\
fi\n\
exit 0\n",
        repo_dir.display(),
        service_stop,
        uv_exe.display(),
        ui_exe.display(),
        service_start,
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
        let repo_dir = backend::find_install_workspace_dir();
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
                backend_startup_error: Mutex::new(None),
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
            get_backend_startup_error,
            check_for_update,
            start_update_and_restart,
            restart_app,
            bootstrap_status,
            bootstrap_manifest,
            run_bootstrap_stage,
            set_install_workspace,
            retry_backend_start,
            frontend_ready,
            get_service_status,
            set_service_enabled,
            restart_background_service,
            get_service_log_path
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

    // 0 means "read from server.port file written by the backend at startup".
    // A running background service owns its own lifetime, so attaching here
    // must never cause it to be stopped when the desktop window exits.
    let resolved = if port == 0 {
        read_port_file().unwrap_or(25314)
    } else {
        port
    };
    if let Some(backend) = BackendProcess::attach_if_healthy(resolved) {
        println!(
            "Dev mode: attached to existing backend on port {}",
            resolved
        );
        return Ok((resolved, backend));
    }
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

    let configured_port = std::env::var("SUZENT_PORT")
        .unwrap_or_else(|_| "0".to_string())
        .parse::<u16>()
        .unwrap_or(0);

    // Prefer an already-running background service (fixed port 25314) or an
    // explicitly supplied backend. Attached backends are not child processes,
    // so BackendProcess::drop leaves them running when the UI closes.
    let attach_port = if configured_port == 0 {
        25314
    } else {
        configured_port
    };
    if let Some(backend) = BackendProcess::attach_if_healthy(attach_port) {
        println!(
            "Attached to existing Suzent service on port {}",
            attach_port
        );
        return Ok((attach_port, backend));
    }

    let mut bp = BackendProcess::new();
    let actual_port = bp.start_with_uv(&uv_exe, &repo_dir, configured_port)?;
    Ok((actual_port, bp))
}

#[cfg(test)]
mod tests {
    use super::write_update_script;
    use std::fs;
    use std::path::Path;

    #[test]
    fn update_script_restores_service_before_propagating_failure() {
        let temp = tempfile::tempdir().expect("temporary directory");
        std::env::set_var("SUZENT_DATA_DIR", temp.path());
        let script = write_update_script(
            Path::new("C:/Suzent Test"),
            Path::new("C:/Tools/uv"),
            Path::new("C:/Suzent Test/suzent-ui"),
            true,
        )
        .expect("update script");
        let contents = fs::read_to_string(script).expect("script contents");
        std::env::remove_var("SUZENT_DATA_DIR");

        let restart = contents.find("service start").expect("service restart");
        let failure = if cfg!(windows) {
            contents.find("if not").expect("failure branch")
        } else {
            contents.find("if [").expect("failure branch")
        };
        assert!(restart < failure);
    }
}
