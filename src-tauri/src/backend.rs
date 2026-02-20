use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::Duration;
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use std::thread;
use std::io::{BufRead, BufReader};

use tauri::Manager;

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

    /// Start the Python backend by launching the bundled Python interpreter.
    /// Only called in release builds - in debug mode the backend runs separately.
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

        // First-run setup: create/update venv from bundled wheel
        ensure_backend_setup(&resource_dir, &app_data_dir)?;

        // Copy config and skills to app data dir if needed
        sync_app_data(&resource_dir, &app_data_dir)?;

        // Resolve python executable inside the venv
        let venv_dir = app_data_dir.join("backend-venv");
        let python_exe = get_venv_python(&venv_dir);

        if !python_exe.exists() {
            return Err(format!("Python not found at {:?}", python_exe));
        }

        // Generate CLI shim
        ensure_cli_shim(&app_data_dir, &python_exe)?;

        // Launch: python -m suzent.server
        let mut command = Command::new(&python_exe);
        command.args(["-m", "suzent.server"])
            .env("VIRTUAL_ENV", &venv_dir)
            .env("SUZENT_PORT", "0")
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
            // CREATE_NO_WINDOW
            command.creation_flags(0x08000000);
        }

        let mut child = command.spawn()
            .map_err(|e| format!("Failed to start Python backend: {}", e))?;

        // Read stdout in a thread to extract the port
        let stdout = child.stdout.take()
            .ok_or("Failed to capture stdout")?;
        let stderr = child.stderr.take()
            .ok_or("Failed to capture stderr")?;

        let (tx, rx_port) = std::sync::mpsc::channel();

        // Stdout reader thread — extracts SERVER_PORT and prints output
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

        // Stderr reader thread
        thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines().flatten() {
                println!("BE ERR: {}", line);
            }
        });

        self.child = Some(child);

        // Wait for the port (timeout 60s — first-run may be slow)
        match rx_port.recv_timeout(Duration::from_secs(60)) {
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

    /// Poll the backend health endpoint until it responds or timeout.
    fn wait_for_backend(&self) -> Result<(), String> {
        let url = format!("http://127.0.0.1:{}/config", self.port);
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(2))
            .build()
            .map_err(|e| format!("Failed to create HTTP client: {}", e))?;

        // 30 attempts * 500ms = 15 seconds timeout
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

    /// Stop the backend process gracefully.
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

// --- First-run setup helpers ---

/// Get the path to the Python executable inside a venv.
fn get_venv_python(venv_dir: &Path) -> PathBuf {
    if cfg!(windows) {
        venv_dir.join("Scripts").join("python.exe")
    } else {
        venv_dir.join("bin").join("python")
    }
}

/// Ensure the backend venv exists and is up-to-date.
/// On first run (or version change), creates a venv and installs the suzent wheel.
pub fn ensure_backend_setup(resource_dir: &Path, app_data_dir: &Path) -> Result<(), String> {
    let venv_dir = app_data_dir.join("backend-venv");
    let marker = venv_dir.join(".suzent-version");

    let current_version = env!("CARGO_PKG_VERSION");

    let needs_setup = if marker.exists() {
        let stored = std::fs::read_to_string(&marker).unwrap_or_default();
        if stored.trim() != current_version {
            true
        } else {
            // Version matches, but let's verify integrity (specifically CLI entry point)
            let python = get_venv_python(&venv_dir);
            if !python.exists() {
                true
            } else {
                // Check if we can import suzent.cli.__main__
                // This handles cases where upgrade failed or files are missing
                let mut cmd = Command::new(&python);
                cmd.args(["-c", "import suzent.cli.__main__"])
                   .stdout(Stdio::null())
                   .stderr(Stdio::null())
                   .stdin(Stdio::null());
                   
                #[cfg(windows)]
                cmd.creation_flags(0x08000000);
                
                let status = cmd.status();
                
                match status {
                    Ok(s) if s.success() => false,
                    _ => {
                        println!("Backend integrity check failed, forcing setup...");
                        true
                    }
                }
            }
        }
    } else {
        true
    };

    if !needs_setup {
        // concise startup: silent on success
        return Ok(());
    }

    println!("Setting up backend venv (v{})...", current_version);

    // Locate uv binary
    let uv_exe = find_uv(resource_dir)?;
    // Locate bundled Python
    let bundled_python = find_bundled_python(resource_dir)?;

    // Check if python is locked before trying to recreate venv to avoid corruption
    let venv_python = get_venv_python(&venv_dir);
    if venv_python.exists() {
        if let Err(e) = std::fs::OpenOptions::new().append(true).open(&venv_python) {
            if e.kind() == std::io::ErrorKind::PermissionDenied {
                println!("  WARNING: Backend environment is in use by another instance. Skipping update to avoid corruption.");
                return Ok(());
            }
        }
    }

    // Step 1: Create venv
    println!("  Creating venv at {:?}...", venv_dir);
    let mut cmd = Command::new(&uv_exe);
    cmd.args(["venv", &venv_dir.to_string_lossy(), "--python", &bundled_python.to_string_lossy()])
       .stdin(Stdio::null())
       .stdout(Stdio::null())
       .stderr(Stdio::null());
    
    #[cfg(windows)]
    cmd.creation_flags(0x08000000);

    let status = cmd.status()
        .map_err(|e| format!("Failed to run uv venv: {}", e))?;

    if !status.success() {
        return Err("uv venv creation failed".to_string());
    }

    // Step 2: Find the wheel
    let wheel_dir = resource_dir.join("resources").join("wheel");
    // Also try directly under resource_dir (depends on Tauri resource flattening)
    let wheel_path = find_wheel(&wheel_dir)
        .or_else(|_| find_wheel(&resource_dir.join("wheel")))
        .or_else(|_| find_wheel(resource_dir))?;

    // Step 3: Install the wheel into the venv
    let venv_python = get_venv_python(&venv_dir);
    println!("  Installing suzent wheel...");
    let mut cmd = Command::new(&uv_exe);
    cmd.args([
            "pip", "install",
            &wheel_path.to_string_lossy(),
            "--python", &venv_python.to_string_lossy(),
            "--force-reinstall",
        ])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
        
    #[cfg(windows)]
    cmd.creation_flags(0x08000000);

    let status = cmd.status()
        .map_err(|e| format!("Failed to run uv pip install: {}", e))?;

    if !status.success() {
        return Err("uv pip install failed".to_string());
    }

    // Step 4: Install Playwright Chromium browser
    println!("  Installing Playwright Chromium (this may take a few minutes)...");
    let mut cmd = Command::new(&venv_python);
    cmd.args(["-m", "playwright", "install", "chromium"])
       .stdin(Stdio::null())
       .stdout(Stdio::null())
       .stderr(Stdio::null());
       
    #[cfg(windows)]
    cmd.creation_flags(0x08000000);

    let playwright_status = cmd.status();

    match playwright_status {
        Ok(status) if status.success() => {
            println!("  Playwright Chromium installed successfully.");
        }
        Ok(status) => {
            // Non-fatal: browsing tool will retry on first use
            println!("  WARNING: Playwright install exited with code {:?} (will retry on first use)", status.code());
        }
        Err(e) => {
            println!("  WARNING: Failed to run playwright install: {} (will retry on first use)", e);
        }
    }

    // Write version marker
    std::fs::write(&marker, current_version)
        .map_err(|e| format!("Failed to write version marker: {}", e))?;

    println!("  Backend setup complete!");
    Ok(())
}

/// Find the uv binary inside the resource directory.
fn find_uv(resource_dir: &Path) -> Result<PathBuf, String> {
    let exe_name = if cfg!(windows) { "uv.exe" } else { "uv" };

    // Check directly in resources/
    let direct = resource_dir.join(exe_name);
    if direct.exists() {
        return Ok(direct);
    }

    // Check in resources/resources/ (Tauri nesting)
    let nested = resource_dir.join("resources").join(exe_name);
    if nested.exists() {
        return Ok(nested);
    }

    Err(format!("uv binary not found in {:?}", resource_dir))
}

/// Find the bundled Python executable.
fn find_bundled_python(resource_dir: &Path) -> Result<PathBuf, String> {
    let candidates = if cfg!(windows) {
        vec![
            resource_dir.join("resources").join("python").join("python.exe"),
            resource_dir.join("python").join("python.exe"),
        ]
    } else {
        vec![
            resource_dir.join("resources").join("python").join("bin").join("python3"),
            resource_dir.join("python").join("bin").join("python3"),
            resource_dir.join("resources").join("python").join("bin").join("python"),
            resource_dir.join("python").join("bin").join("python"),
        ]
    };

    for p in &candidates {
        if p.exists() {
            return Ok(p.clone());
        }
    }

    Err(format!("Bundled Python not found in {:?}", resource_dir))
}

/// Find a .whl file in the given directory.
fn find_wheel(dir: &Path) -> Result<PathBuf, String> {
    if !dir.exists() {
        return Err(format!("Wheel directory not found: {:?}", dir));
    }

    for entry in std::fs::read_dir(dir).map_err(|e| format!("Failed to read dir: {}", e))? {
        if let Ok(entry) = entry {
            let path = entry.path();
            if path.extension().is_some_and(|ext| ext == "whl") {
                return Ok(path);
            }
        }
    }

    Err(format!("No .whl file found in {:?}", dir))
}

/// Sync config and skills from bundled resources to app data dir.
pub fn sync_app_data(resource_dir: &Path, app_data_dir: &Path) -> Result<(), String> {
    // Try both direct and nested resource paths
    let prefixes = [
        resource_dir.join("resources"),
        resource_dir.to_path_buf(),
    ];

    for dir_name in &["config", "skills"] {
        let dest_dir = app_data_dir.join(dir_name);

        // Find source
        let mut src_dir = None;
        for prefix in &prefixes {
            let candidate = prefix.join(dir_name);
            if candidate.exists() {
                src_dir = Some(candidate);
                break;
            }
        }

        let src_dir = match src_dir {
            Some(d) => d,
            None => {
                println!("  WARNING: Bundled {} directory not found, skipping", dir_name);
                continue;
            }
        };

        if !dest_dir.exists() {
            // First install: copy everything, renaming .example. files
            println!("  Initializing {} directory...", dir_name);
            copy_dir_recursive(&src_dir, &dest_dir, true)
                .map_err(|e| format!("Failed to copy {}: {}", dir_name, e))?;
        } else {
            // Subsequent runs: only copy missing files
            copy_missing_files(&src_dir, &dest_dir)
                .map_err(|e| format!("Failed to sync {}: {}", dir_name, e))?;
        }
    }

    Ok(())
}

/// Recursively copy a directory, optionally copying .example. files to their non-example names too.
fn copy_dir_recursive(src: &Path, dest: &Path, rename_examples: bool) -> std::io::Result<()> {
    std::fs::create_dir_all(dest)?;

    for entry in std::fs::read_dir(src)? {
        let entry = entry?;
        let src_path = entry.path();
        let file_name = entry.file_name().to_string_lossy().to_string();

        if src_path.is_dir() {
            copy_dir_recursive(&src_path, &dest.join(&file_name), rename_examples)?;
        } else {
            // ALWAYS copy the file with its original name
            std::fs::copy(&src_path, dest.join(&file_name))?;

            // If it's an example file and we should deploy base configs, create the non-example version
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

/// Copy only files that don't exist in the destination, while ensuring .example. files are updated.
fn copy_missing_files(src: &Path, dest: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(dest)?;

    for entry in std::fs::read_dir(src)? {
        let entry = entry?;
        let src_path = entry.path();
        let file_name = entry.file_name().to_string_lossy().to_string();

        if src_path.is_dir() {
            copy_missing_files(&src_path, &dest.join(&file_name))?;
        } else {
            // Provide a graceful fallback: For example files, we always want to overwrite the
            // destination example file to ensure the application has the latest defaults.
            // We never overwrite the user's custom (non-example) file.

            if file_name.contains(".example.") {
                // Always overwrite the .example. file to give the backend the latest fallback values
                let example_dest = dest.join(&file_name);
                std::fs::copy(&src_path, &example_dest)?;
                // println!("  Updated example fallback: {:?}", example_dest);

                // Check if the user is missing the non-example configuration file entirely
                let user_dest_name = file_name.replace(".example.", ".");
                let user_dest_path = dest.join(&user_dest_name);
                if !user_dest_path.exists() {
                    std::fs::copy(&src_path, &user_dest_path)?;
                    println!("  Created default configuration: {:?}", user_dest_path);
                }
            } else {
                // For non-example utility files, only copy if they don't exist
                let dest_path = dest.join(&file_name);
                if !dest_path.exists() {
                    std::fs::copy(&src_path, &dest_path)?;
                    println!("  Restored missing file: {:?}", dest_path);
                }
            }
        }
    }

    Ok(())
}

/// Generate a CLI shim script in app_data_dir/bin.
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
        // macOS/Linux
        let shim_path = bin_dir.join("suzent");
        let content = format!(
            "#!/bin/sh\nexec \"{}\" -m suzent.cli \"$@\"",
            python_exe.to_string_lossy()
        );
        std::fs::write(&shim_path, content)
            .map_err(|e| format!("Failed to write shim: {}", e))?;
        
        // Make executable using std::os::unix::fs::PermissionsExt (only on unix)
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
