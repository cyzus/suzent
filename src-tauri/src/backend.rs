use std::path::PathBuf;

#[cfg(not(debug_assertions))]
use std::path::Path;
#[cfg(not(debug_assertions))]
use std::process::{Command, Stdio};
#[cfg(not(debug_assertions))]
use std::time::Duration;
#[cfg(all(not(debug_assertions), windows))]
use std::os::windows::process::CommandExt;
#[cfg(not(debug_assertions))]
use std::thread;
#[cfg(not(debug_assertions))]
use std::io::{BufRead, BufReader};

pub struct BackendProcess {
    child: Option<std::process::Child>,
    pub port: u16,
}

impl BackendProcess {
    pub fn new() -> Self {
        BackendProcess { child: None, port: 0 }
    }

    pub fn stop(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

// Release-only: launch and health-check the backend process.
#[cfg(not(debug_assertions))]
impl BackendProcess {
    /// Start backend using `uv run python -m suzent.server` in the repo directory.
    pub fn start_with_uv(&mut self, uv_exe: &Path, repo_dir: &Path, hint_port: u16) -> Result<u16, String> {
        let mut command = Command::new(uv_exe);
        command
            .args(["run", "python", "-m", "suzent.server"])
            .env("SUZENT_PORT", hint_port.to_string())
            .env("SUZENT_HOST", "127.0.0.1")
            .current_dir(repo_dir)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .stdin(Stdio::null());

        #[cfg(windows)]
        command.creation_flags(0x08000000); // CREATE_NO_WINDOW

        let mut child = command.spawn()
            .map_err(|e| format!("Failed to start backend: {}", e))?;

        let stdout = child.stdout.take().ok_or("Failed to capture stdout")?;
        let stderr = child.stderr.take().ok_or("Failed to capture stderr")?;

        let (tx, rx) = std::sync::mpsc::channel::<u16>();

        thread::spawn(move || {
            let reader = BufReader::new(stdout);
            let mut sent = false;
            for line in reader.lines().flatten() {
                println!("BE: {}", line);
                if !sent {
                    if let Some(idx) = line.find("SERVER_PORT:") {
                        let after = &line[idx + "SERVER_PORT:".len()..];
                        if let Some(token) = after.split_whitespace().next() {
                            if let Ok(port) = token.parse::<u16>() {
                                let _ = tx.send(port);
                                sent = true;
                            }
                        }
                    }
                }
            }
        });

        thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines().flatten() {
                eprintln!("BE ERR: {}", line);
            }
        });

        self.child = Some(child);

        match rx.recv_timeout(Duration::from_secs(30)) {
            Ok(port) => {
                self.port = port;
                println!("Backend reported port: {}", port);
                self.wait_for_backend()?;
                Ok(port)
            }
            Err(_) => {
                self.stop();
                Err("Timed out waiting for backend to start".to_string())
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
    std::env::current_dir().unwrap_or_default()
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

fn dirs_home() -> PathBuf {
    std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .map(PathBuf::from)
        .unwrap_or_default()
}
