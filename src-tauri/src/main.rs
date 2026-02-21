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

// Minimal logging helper for debugging CLI hangs




fn main() {
    // Force the working directory to the executable's directory.
    // This fixes issues where NSIS installers launch the app with an invalid CWD (like System32 or %TEMP%).
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            let _ = std::env::set_current_dir(exe_dir);
        }
    }

    // Check for CLI arguments
    let args: Vec<String> = std::env::args().collect();

    // If we have no arguments, we are likely running as a GUI.
    // Since we are now a Console app (to support blocking CLI), we must hide the console window
    // that Windows automatically created for us.
    if args.len() == 1 {
        #[cfg(windows)]
        unsafe {
            use windows_sys::Win32::System::Console::FreeConsole;
            FreeConsole();
        }
    }

    if args.len() > 1 {
        // We have arguments, run as CLI.
        // Since we are a Console subsystem app, we are ALREADY attached to the console.
        // No need to AttachConsole.


        // Try to locate the backend venv in AppData (Roaming)
        // backend.rs uses app.path().app_data_dir() which maps to Roaming/com.suzent.app on Windows
        if let Some(app_data) = std::env::var_os("APPDATA") {
            let app_data_root = std::path::PathBuf::from(app_data);
            // Default bundle identifier
            let suzent_app_data = app_data_root.join("com.suzent.app");
            let python_exe = suzent_app_data.join("backend-venv").join("Scripts").join("python.exe");

            // Always attempt to validate/setup the environment first
            // This ensures integrity checks (like missing entry points) are run
            if let Ok(exe_path) = std::env::current_exe() {
                 if let Some(exe_dir) = exe_path.parent() {
                    // suzent_app_data is already defined above as Local/com.suzent.app
                    
                    // We use the exe directory as the resource directory
                    if let Err(e) = backend::ensure_backend_setup(exe_dir, &suzent_app_data) {
                        eprintln!("Warning: Environment setup failed: {}", e);
                    }
                    
                    if let Err(e) = backend::sync_app_data(exe_dir, &suzent_app_data) {
                         eprintln!("Warning: Failed to sync app data: {}", e);
                    }
                 }
            }

            if python_exe.exists() {
                // Pass all arguments to python -m suzent.cli
                // Skip the first argument (executable name)
                let cli_args = &args[1..];
                
                let status = std::process::Command::new(python_exe)
                    .args(["-m", "suzent.cli"])
                    .env("SUZENT_APP_DATA", &suzent_app_data)
                    .stdin(std::process::Stdio::null())
                    .args(cli_args)
                    .status();

                match status {
                    Ok(exit_status) => {
                        std::process::exit(exit_status.code().unwrap_or(1));
                    }
                    Err(e) => {
                        eprintln!("Failed to execute CLI: {}", e);
                        std::process::exit(1);
                    }
                }
            } else {
                eprintln!("Error: Suzent environment not initialized and setup failed.");
                eprintln!("Please run the application from the Start Menu once to ensure environment is set up.");
                std::process::exit(1);
            }
        } else {
             // Non-Windows or weird environment, fall through to GUI? 
             // Or just print error. For now, let's assume if args > 1 we WANT cli.
             eprintln!("Error: Could not determine APPDATA location.");
             std::process::exit(1);
        }
    }

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
/// - Debug: Returns default port 25314 (expects manually-run backend)
#[cfg(not(debug_assertions))]
fn get_backend_config(app: &tauri::AppHandle) -> Result<(u16, BackendProcess), String> {
    let mut backend = BackendProcess::new();
    let port = backend.start(app)?;
    Ok((port, backend))
}

#[cfg(debug_assertions)]
fn get_backend_config(_app: &tauri::AppHandle) -> Result<(u16, BackendProcess), String> {
    let port = std::env::var("SUZENT_PORT")
        .unwrap_or_else(|_| "25314".to_string())
        .parse::<u16>()
        .unwrap_or(25314);

    println!("Development mode: Please start backend manually with:");
    println!("  set SUZENT_PORT={} && python src/suzent/server.py", port);
    println!("Expected backend URL: http://localhost:{}", port);
    Ok((port, BackendProcess::new()))
}
