use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::Duration;
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use std::thread;
use std::io::{BufRead, BufReader};
use std::net::TcpListener;

use tauri::{Manager, Emitter};

pub struct BackendProcess {
    child: Option<std::process::Child>,
    pub port: u16,
}

impl BackendProcess {
    pub fn new() -> Self {
        BackendProcess {
            child: None,
            port: 0,
        }
    }

    /// Start the Python backend using the prebuilt bundled python-env.
    /// Only called in release builds — in debug mode the backend runs separately.
    #[allow(dead_code)]
    pub fn start(&mut self, app_handle: &tauri::AppHandle) -> Result<u16, String> {
        let app_data_dir = app_handle.path()
            .app_data_dir()
            .map_err(|e| format!("Failed to get app data dir: {}", e))?;

        std::fs::create_dir_all(&app_data_dir)
            .map_err(|e| format!("Failed to create app data dir: {}", e))?;

        let resource_dir = app_handle.path()
            .resource_dir()
            .map_err(|e| format!("Failed to get resource dir: {}", e))?;

        let python_exe = find_bundled_python(&resource_dir)?;

        if !python_exe.exists() {
            return Err(format!("Bundled Python not found at {:?}", python_exe));
        }

        // Sync config and skills to app data dir on first install / upgrade
        let window = app_handle.get_webview_window("main");
        emit_progress(&app_handle, &window, "Initializing app data...");
        sync_app_data(&resource_dir, &app_data_dir)?;

        // Generate CLI shim pointing at the bundled Python
        ensure_cli_shim(&app_data_dir, &python_exe)?;

        emit_progress(&app_handle, &window, "Starting backend server...");

        let port_to_use = read_last_stable_port(&app_data_dir).unwrap_or(0);

        let mut command = Command::new(&python_exe);
        command.args(["-m", "suzent.server"])
            .env("SUZENT_PORT", port_to_use.to_string())
            .env("SUZENT_HOST", "127.0.0.1")
            .env("SUZENT_APP_DATA", &app_data_dir)
            .env("CHATS_DB_PATH", app_data_dir.join("chats.db"))
            .env("LANCEDB_URI", app_data_dir.join("memory"))
            .env("SANDBOX_DATA_PATH", app_data_dir.join("sandbox-data"))
            .env("SKILLS_DIR", app_data_dir.join("skills"))
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .stdin(Stdio::piped());

        #[cfg(windows)]
        {
            command.creation_flags(0x08000000);
        }

        let mut child = command.spawn()
            .map_err(|e| format!("Failed to start Python backend: {}", e))?;

        let stdout = child.stdout.take().ok_or("Failed to capture stdout")?;
        let stderr = child.stderr.take().ok_or("Failed to capture stderr")?;

        let (tx, rx_port) = std::sync::mpsc::channel();

        thread::spawn(move || {
            let reader = BufReader::new(stdout);
            let mut port_found = false;
            for line in reader.lines() {
                match line {
                    Ok(line_str) => {
                        println!("BE: {}", line_str);
                        if !port_found {
                            if let Some(idx) = line_str.find("SERVER_PORT:") {
                                let after = &line_str[idx + "SERVER_PORT:".len()..];
                                if let Some(token) = after.split_whitespace().next() {
                                    if let Ok(port) = token.parse::<u16>() {
                                        let _ = tx.send(port);
                                        port_found = true;
                                    }
                                }
                            }
                        }
                    }
                    Err(_) => break,
                }
            }
        });

        thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines().flatten() {
                println!("BE ERR: {}", line);
            }
        });

        self.child = Some(child);

        match rx_port.recv_timeout(Duration::from_secs(30)) {
            Ok(port) => {
                self.port = port;
                println!("Backend reported port: {}", port);
                self.wait_for_backend()?;
                Ok(port)
            }
            Err(_) => {
                self.stop();
                Err("Timed out waiting for backend to report port".to_string())
            }
        }
    }

    fn wait_for_backend(&self) -> Result<(), String> {
        let url = format!("http://127.0.0.1:{}/config", self.port);
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(2))
            .build()
            .map_err(|e| format!("Failed to create HTTP client: {}", e))?;

        for attempt in 1..=30 {
            thread::sleep(Duration::from_millis(500));
            if let Ok(resp) = client.get(&url).send() {
                if resp.status().is_success() || resp.status().as_u16() == 404 {
                    println!("Backend ready after {} attempts", attempt);
                    return Ok(());
                }
            }
        }

        Err("Backend failed to respond to health check within 15 seconds".to_string())
    }

    pub fn stop(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

impl Drop for BackendProcess {
    fn drop(&mut self) {
        self.stop();
    }
}

// --- Helpers ---

fn emit_progress(app_handle: &tauri::AppHandle, window: &Option<tauri::WebviewWindow>, msg: &str) {
    println!("SETUP: {}", msg);
    let _ = app_handle.emit("setup-progress", msg);
    if let Some(w) = window {
        let escaped = msg.replace('\\', "\\\\").replace('"', "\\\"");
        let _ = w.eval(&format!("window.__SUZENT_SETUP_STEP__ = \"{}\";", escaped));
    }
}

/// Resolve the resources base dir (Tauri nests bundled resources under resources/).
fn resolve_resources_base(resource_dir: &Path) -> PathBuf {
    let nested = resource_dir.join("resources");
    if nested.exists() { nested } else { resource_dir.to_path_buf() }
}

/// Find the prebuilt Python executable inside python-env/.
fn find_bundled_python(resource_dir: &Path) -> Result<PathBuf, String> {
    let base = resolve_resources_base(resource_dir);
    let candidates = if cfg!(windows) {
        vec![base.join("python-env").join("python.exe")]
    } else {
        vec![
            base.join("python-env").join("bin").join("python3"),
            base.join("python-env").join("bin").join("python"),
        ]
    };

    for p in &candidates {
        if p.exists() {
            return Ok(p.clone());
        }
    }

    Err(format!("Bundled Python not found under {:?}", base.join("python-env")))
}

fn read_last_stable_port(app_data_dir: &Path) -> Option<u16> {
    let port_file = app_data_dir.join("server.port");
    let content = std::fs::read_to_string(&port_file).ok()?;
    let port: u16 = content.trim().parse().ok()?;
    if port == 0 {
        return None;
    }
    if TcpListener::bind(("127.0.0.1", port)).is_ok() {
        println!("Reusing last known backend port: {}", port);
        Some(port)
    } else {
        println!("Last known port {} is in use, using dynamic port assignment", port);
        None
    }
}

/// Sync config and skills from bundled resources to app data dir.
pub fn sync_app_data(resource_dir: &Path, app_data_dir: &Path) -> Result<(), String> {
    let base = resolve_resources_base(resource_dir);

    for dir_name in &["config", "skills"] {
        let dest_dir = app_data_dir.join(dir_name);
        let src_dir = base.join(dir_name);

        if !src_dir.exists() {
            println!("  WARNING: Bundled {} directory not found, skipping", dir_name);
            continue;
        }

        if !dest_dir.exists() {
            println!("  Initializing {} directory...", dir_name);
            copy_dir_recursive(&src_dir, &dest_dir, true)
                .map_err(|e| format!("Failed to copy {}: {}", dir_name, e))?;
        } else {
            copy_missing_files(&src_dir, &dest_dir)
                .map_err(|e| format!("Failed to sync {}: {}", dir_name, e))?;
        }
    }

    Ok(())
}

fn copy_dir_recursive(src: &Path, dest: &Path, rename_examples: bool) -> std::io::Result<()> {
    std::fs::create_dir_all(dest)?;

    for entry in std::fs::read_dir(src)? {
        let entry = entry?;
        let src_path = entry.path();
        let file_name = entry.file_name().to_string_lossy().to_string();

        if src_path.is_dir() {
            copy_dir_recursive(&src_path, &dest.join(&file_name), rename_examples)?;
        } else {
            std::fs::copy(&src_path, dest.join(&file_name))?;
            if rename_examples && file_name.contains(".example.") {
                let dest_name = file_name.replace(".example.", ".");
                let dest_path = dest.join(&dest_name);
                if !dest_path.exists() {
                    std::fs::copy(&src_path, &dest_path)?;
                }
            }
        }
    }

    Ok(())
}

fn copy_missing_files(src: &Path, dest: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(dest)?;

    for entry in std::fs::read_dir(src)? {
        let entry = entry?;
        let src_path = entry.path();
        let file_name = entry.file_name().to_string_lossy().to_string();

        if src_path.is_dir() {
            copy_missing_files(&src_path, &dest.join(&file_name))?;
        } else if file_name.contains(".example.") {
            let example_dest = dest.join(&file_name);
            std::fs::copy(&src_path, &example_dest)?;

            let user_dest_path = dest.join(file_name.replace(".example.", "."));
            if !user_dest_path.exists() {
                std::fs::copy(&src_path, &user_dest_path)?;
                println!("  Created default configuration: {:?}", user_dest_path);
            }
        } else {
            let dest_path = dest.join(&file_name);
            if !dest_path.exists() {
                std::fs::copy(&src_path, &dest_path)?;
                println!("  Restored missing file: {:?}", dest_path);
            }
        }
    }

    Ok(())
}

/// Generate a CLI shim in app_data_dir/bin pointing at the bundled Python.
fn ensure_cli_shim(app_data_dir: &Path, python_exe: &Path) -> Result<(), String> {
    let bin_dir = app_data_dir.join("bin");
    std::fs::create_dir_all(&bin_dir)
        .map_err(|e| format!("Failed to create bin dir: {}", e))?;

    if cfg!(windows) {
        let shim_path = bin_dir.join("suzent.cmd");
        let content = format!(
            "@echo off\r\n\"{}\" -m suzent.cli %*",
            python_exe.to_string_lossy()
        );
        std::fs::write(&shim_path, content)
            .map_err(|e| format!("Failed to write shim: {}", e))?;
    } else {
        let shim_path = bin_dir.join("suzent");
        let content = format!(
            "#!/bin/sh\nexec \"{}\" -m suzent.cli \"$@\"",
            python_exe.to_string_lossy()
        );
        std::fs::write(&shim_path, content)
            .map_err(|e| format!("Failed to write shim: {}", e))?;

        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = std::fs::metadata(&shim_path)
                .map_err(|e| format!("Failed to get shim metadata: {}", e))?
                .permissions();
            perms.set_mode(0o755);
            std::fs::set_permissions(&shim_path, perms)
                .map_err(|e| format!("Failed to set shim permissions: {}", e))?;
        }
    }

    Ok(())
}
