// Prevents additional console window on Windows in release builds
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;

use backend::BackendProcess;
use tauri::{Manager, State};
use std::sync::Mutex;

struct AppState {
    backend: Mutex<BackendProcess>,
}

#[tauri::command]
fn get_backend_port(state: State<AppState>) -> Result<u16, String> {
    let backend = state.backend.lock()
        .map_err(|e| format!("Lock error: {}", e))?;
    Ok(backend.port)
}

/// Inject the backend port into the frontend window via JavaScript global variable.
/// This allows the frontend to dynamically connect to the backend regardless of port.
fn inject_backend_port(window: &tauri::WebviewWindow, port: u16) -> Result<(), String> {
    window.eval(&format!("window.__SUZENT_BACKEND_PORT__ = {};", port))
        .map_err(|e| format!("Failed to inject port: {}", e))
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let window = app.get_webview_window("main")
                .ok_or("Failed to get main window")?;

            // Determine port and backend process based on build mode
            let (port, backend) = get_backend_config(app)?;

            inject_backend_port(&window, port)?;
            println!("Backend configured on port {}", port);

            app.manage(AppState {
                backend: Mutex::new(backend),
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![get_backend_port])
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

/// Returns (port, BackendProcess) based on build configuration.
/// - Release: Starts bundled backend and returns its dynamically allocated port
/// - Debug: Returns default port 8000 (expects manually-run backend)
#[cfg(not(debug_assertions))]
fn get_backend_config(app: &tauri::App) -> Result<(u16, BackendProcess), String> {
    let mut backend = BackendProcess::new();
    let port = backend.start(&app.handle())?;
    Ok((port, backend))
}

#[cfg(debug_assertions)]
fn get_backend_config(_app: &tauri::App) -> Result<(u16, BackendProcess), String> {
    println!("Development mode: Please start backend manually with:");
    println!("  python src/suzent/server.py");
    println!("Expected backend URL: http://localhost:8000");
    Ok((8000, BackendProcess::new()))
}
