// Prevents additional console window on Windows in release builds
// REMOVED: #![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;

use backend::BackendProcess;
use tauri::{Manager, State, Emitter};
use std::sync::Mutex;

struct AppState {
    backend: Mutex<Option<BackendProcess>>,
}

#[tauri::command]
fn get_backend_port(state: State<AppState>) -> Result<u16, String> {
    let backend_guard = state.backend.lock()
        .map_err(|e| format!("Lock error: {}", e))?;

    if let Some(backend) = &*backend_guard {
        Ok(backend.port)
    } else {
        Err("Backend not ready yet".to_string())
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();

    // GUI mode: hide the console window Windows creates for console-subsystem apps.
    if args.len() == 1 {
        #[cfg(windows)]
        unsafe {
            use windows_sys::Win32::System::Console::FreeConsole;
            FreeConsole();
        }
    }

    // CLI mode: delegate to `uv run suzent <args>` in the repo directory.
    if args.len() > 1 {
        let repo_dir = backend::find_repo_dir();
        let uv_exe   = backend::find_uv();

        let status = std::process::Command::new(&uv_exe)
            .arg("run")
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
            let window = app.get_webview_window("main")
                .ok_or("Failed to get main window")?;

            app.manage(AppState {
                backend: Mutex::new(None),
            });

            let app_handle = app.handle().clone();

            std::thread::spawn(move || {
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
                            let _ = window.emit("backend-error", format!("Failed to inject backend port: {}", e));
                        } else {
                            let _ = app_handle.emit("backend-ready", port);
                        }
                    }
                    Err(e) => {
                        eprintln!("Failed to start backend: {}", e);
                        let _ = window.emit("backend-error", e);
                    }
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![get_backend_port])
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

/// Read the port written by the Python backend to DATA_DIR/server.port.
fn read_port_file() -> Option<u16> {
    let data_dir = backend::find_repo_dir().join("data");
    let port_file = data_dir.join("server.port");
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
    let resolved = if port == 0 { read_port_file().unwrap_or(25314) } else { port };
    println!("Dev mode: connecting to backend on port {}", resolved);
    println!("If nothing shows up, start the backend first with: suzent serve");
    Ok((resolved, BackendProcess::new()))
}

/// Release mode: launch the backend via `uv run python -m suzent.server`.
#[cfg(not(debug_assertions))]
fn get_backend_config(app_handle: &tauri::AppHandle) -> Result<(u16, BackendProcess), String> {
    let _ = app_handle;
    let repo_dir = backend::find_repo_dir();
    let uv_exe   = backend::find_uv();

    let port = std::env::var("SUZENT_PORT")
        .unwrap_or_else(|_| "0".to_string())
        .parse::<u16>()
        .unwrap_or(0);

    let mut bp = BackendProcess::new();
    let actual_port = bp.start_with_uv(&uv_exe, &repo_dir, port)?;
    Ok((actual_port, bp))
}
