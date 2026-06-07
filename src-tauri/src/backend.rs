use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::Duration;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

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

    pub fn stop(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

// Launch and health-check the backend process.
impl BackendProcess {
    /// Start backend: prefer venv Python directly (avoids uv wrapper stdout pipe issues on Windows).
    /// Falls back to `uv run --no-sync` if venv not found.
    ///
    /// stdout/stderr are redirected to the log file, and Windows launches the
    /// backend without opening a console window.
    pub fn start_with_uv(
        &mut self,
        uv_exe: &Path,
        repo_dir: &Path,
        hint_port: u16,
    ) -> Result<u16, String> {
        let data_dir = find_data_dir();
        let runtime_dir = data_dir.join("runtime");
        std::fs::create_dir_all(&runtime_dir)
            .map_err(|e| format!("Failed to create runtime dir: {}", e))?;

        let port_file = runtime_dir.join("server.port");
        // Delete stale port file so we can detect when the new backend writes it.
        let _ = std::fs::remove_file(&port_file);

        let log_file = runtime_dir.join("server.log");
        let log_handle = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_file)
            .map_err(|e| format!("Failed to open log file: {}", e))?;

        let venv_python = find_venv_python(repo_dir);
        let mut command = if let Some(ref py) = venv_python {
            let mut cmd = Command::new(py);
            cmd.args(["-m", "suzent.server"]);
            cmd
        } else {
            let mut cmd = Command::new(uv_exe);
            cmd.args(["run", "--no-sync", "python", "-m", "suzent.server"]);
            cmd
        };

        // Duplicate the log handle for stderr.
        let log_handle_stderr = log_handle
            .try_clone()
            .map_err(|e| format!("Failed to clone log handle: {}", e))?;

        command
            .env("SUZENT_PORT", hint_port.to_string())
            .env("SUZENT_HOST", "127.0.0.1")
            .env("SUZENT_DATA_DIR", &data_dir)
            .env("PYTHONUNBUFFERED", "1")
            .env("LOG_FILE", &log_file)
            .current_dir(repo_dir)
            .stdout(Stdio::from(log_handle))
            .stderr(Stdio::from(log_handle_stderr))
            .stdin(Stdio::piped()); // keep pipe open; Python monitor_stdin blocks on it until Tauri exits

        hide_command_window(&mut command);

        let child = command
            .spawn()
            .map_err(|e| format!("Failed to start backend: {}", e))?;

        self.child = Some(child);

        // Poll server.port file written by Python's write_port_file() at startup.
        let port = self.poll_port_file(&port_file, Duration::from_secs(30))?;
        self.port = port;
        println!("Backend reported port: {}", port);
        self.wait_for_backend()?;
        Ok(port)
    }

    fn poll_port_file(
        &self,
        port_file: &std::path::Path,
        timeout: Duration,
    ) -> Result<u16, String> {
        let deadline = std::time::Instant::now() + timeout;
        loop {
            if std::time::Instant::now() >= deadline {
                return Err("Timed out waiting for backend to write server.port".to_string());
            }
            if let Ok(contents) = std::fs::read_to_string(port_file) {
                if let Ok(port) = contents.trim().parse::<u16>() {
                    return Ok(port);
                }
            }
            thread::sleep(Duration::from_millis(200));
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
        Err("Backend failed health check within 15 seconds".to_string())
    }
}

impl Drop for BackendProcess {
    fn drop(&mut self) {
        self.stop();
    }
}

// ── Path resolution helpers ──────────────────────────────────────────────────

/// Find the repo root directory.
/// In dev the exe lives under target/; walk up until we find pyproject.toml.
/// Fall back to the exe's directory.
pub fn find_repo_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("SUZENT_DIR") {
        let path = PathBuf::from(dir);
        if path.join("pyproject.toml").exists() {
            return path;
        }
    }

    if let Ok(exe) = std::env::current_exe() {
        let mut dir = exe.parent().map(PathBuf::from).unwrap_or_default();
        for _ in 0..6 {
            if dir.join("pyproject.toml").exists() {
                return dir;
            }
            if let Some(parent) = dir.parent() {
                dir = parent.to_path_buf();
            } else {
                break;
            }
        }
        // Fall back to exe directory
        if let Some(parent) = exe.parent() {
            return parent.to_path_buf();
        }
    }

    let default_workspace = default_install_dir();
    if default_workspace.join("pyproject.toml").exists() {
        return default_workspace;
    }

    std::env::current_dir().unwrap_or_default()
}

pub fn find_install_workspace_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("SUZENT_DIR") {
        if !dir.trim().is_empty() {
            return PathBuf::from(dir);
        }
    }

    if let Ok(dir) = std::fs::read_to_string(install_workspace_marker_path()) {
        let trimmed = dir.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed);
        }
    }

    default_install_dir()
}

pub fn persist_install_workspace_dir(dir: &std::path::Path) -> Result<(), String> {
    let marker = install_workspace_marker_path();
    if let Some(parent) = marker.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("Failed to create install config directory: {}", e))?;
    }
    std::fs::write(&marker, dir.display().to_string())
        .map_err(|e| format!("Failed to save install directory: {}", e))
}

pub fn default_install_dir() -> PathBuf {
    dirs_home().join("suzent")
}

fn install_workspace_marker_path() -> PathBuf {
    find_data_dir().join("install-dir.txt")
}

pub fn is_workspace_bootstrapped(repo_dir: &std::path::Path) -> bool {
    if !repo_dir.join("pyproject.toml").exists() {
        return false;
    }
    if !repo_dir.join(".suzent-bootstrap-complete").exists() {
        return false;
    }

    let py = if cfg!(windows) {
        repo_dir.join(".venv").join("Scripts").join("python.exe")
    } else {
        repo_dir.join(".venv").join("bin").join("python")
    };

    py.exists()
}

/// Locate SUZENT's user data directory.
pub fn find_data_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("SUZENT_DATA_DIR") {
        if !dir.trim().is_empty() {
            return PathBuf::from(dir);
        }
    }
    dirs_home().join(".suzent")
}

/// Locate the `uv` executable (PATH, ~/.cargo/bin, ~/.local/bin).
pub fn find_uv() -> PathBuf {
    // Try PATH first
    if let Ok(path) = which_uv() {
        return path;
    }

    // Common install locations
    let candidates: Vec<PathBuf> = if cfg!(windows) {
        vec![
            dirs_home().join(".cargo").join("bin").join("uv.exe"),
            dirs_home().join(".local").join("bin").join("uv.exe"),
        ]
    } else {
        vec![
            dirs_home().join(".cargo").join("bin").join("uv"),
            dirs_home().join(".local").join("bin").join("uv"),
        ]
    };

    for c in candidates {
        if c.exists() {
            return c;
        }
    }

    // Give up — let the OS resolve it and show a clear error on spawn
    PathBuf::from("uv")
}

fn which_uv() -> Result<PathBuf, ()> {
    let name = if cfg!(windows) { "uv.exe" } else { "uv" };
    let path_var = std::env::var("PATH").unwrap_or_default();
    for dir in std::env::split_paths(&path_var) {
        let candidate = dir.join(name);
        if candidate.exists() {
            return Ok(candidate);
        }
    }
    Err(())
}

/// Return the venv Python executable if the venv exists under repo_dir.
fn find_venv_python(repo_dir: &Path) -> Option<PathBuf> {
    let py = if cfg!(windows) {
        repo_dir.join(".venv").join("Scripts").join("python.exe")
    } else {
        repo_dir.join(".venv").join("bin").join("python")
    };
    if py.exists() {
        Some(py)
    } else {
        None
    }
}

fn dirs_home() -> PathBuf {
    std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .map(PathBuf::from)
        .unwrap_or_default()
}

#[cfg(windows)]
fn hide_command_window(command: &mut Command) {
    use std::os::windows::process::CommandExt;
    command.creation_flags(CREATE_NO_WINDOW);
}

#[cfg(not(windows))]
fn hide_command_window(_command: &mut Command) {}
