// Prevents additional console window on Windows in release builds
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

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
    tauri::Builder::default()
        .setup(|app| {
            let window = app.get_webview_window("main")
                .ok_or("Failed to get main window")?;

            // Initialize AppState with no backend yet
            app.manage(AppState {
                backend: Mutex::new(None),
            });

            // Clone handle for the thread
            let app_handle = app.handle().clone();

            // Start backend in a separate thread so we don't block the UI
            std::thread::spawn(move || {
                // Determine port and backend process based on build mode
                // This might block for up to 45 seconds (in release mode)
                match get_backend_config(&app_handle) {
                    Ok((port, backend)) => {
                        println!("Backend configured on port {}", port);
                        
                        // Update state
                        if let Some(state) = app_handle.try_state::<AppState>() {
                            if let Ok(mut guard) = state.backend.lock() {
                                *guard = Some(backend);
                            }
                        }


                        // Inject port for frontend runtime (prefer window variable; storage best-effort)
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
                        }
                    }
                    Err(e) => {
                        eprintln!("Failed to start backend: {}", e);
                        // Maybe show error in UI?
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

/// Returns (port, BackendProcess) based on build configuration.
/// - Release: Starts bundled backend and returns its dynamically allocated port
/// - Debug: Returns default port 8000 (expects manually-run backend)
#[cfg(not(debug_assertions))]
fn get_backend_config(app: &tauri::AppHandle) -> Result<(u16, BackendProcess), String> {
    let mut backend = BackendProcess::new();
    let port = backend.start(app)?;
    Ok((port, backend))
}

#[cfg(debug_assertions)]
fn get_backend_config(_app: &tauri::AppHandle) -> Result<(u16, BackendProcess), String> {
    println!("Development mode: Please start backend manually with:");
    println!("  python src/suzent/server.py");
    println!("Expected backend URL: http://localhost:8000");
    Ok((8000, BackendProcess::new()))
}
