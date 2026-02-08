use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

use std::time::Duration;
use std::thread;
use tauri::Manager;

pub struct BackendProcess {
    child: Option<CommandChild>,
    pub port: u16,
}

impl BackendProcess {
    pub fn new() -> Self {
        BackendProcess {
            child: None,
            port: 0,
        }
    }

    /// Start the Python backend as a sidecar process.
    /// Only called in release builds - in debug mode the backend runs separately.
    #[allow(dead_code)] // Only used in release builds via cfg
    pub fn start(&mut self, app_handle: &tauri::AppHandle) -> Result<u16, String> {
        // In release mode, we let the backend pick a random free port by passing 0
        // The backend will report the actual port it bound to via stdout
        let app_data_dir = app_handle.path()
            .app_data_dir()
            .map_err(|e| format!("Failed to get app data dir: {}", e))?;

        // Ensure app data directory exists for persistent storage
        std::fs::create_dir_all(&app_data_dir)
            .map_err(|e| format!("Failed to create app data dir: {}", e))?;

        // Start backend with environment variables for configuration
        // We set SUZENT_PORT to 0 to trigger dynamic port assignment in the backend
        let (rx, child) = app_handle.shell()
            .sidecar("suzent-backend")
            .map_err(|e| format!("Failed to create sidecar command: {}", e))?
            .env("SUZENT_PORT", "0")
            .env("SUZENT_HOST", "127.0.0.1")
            .env("SUZENT_APP_DATA", &app_data_dir)
            .env("CHATS_DB_PATH", app_data_dir.join("chats.db"))
            .env("LANCEDB_URI", app_data_dir.join("memory"))
            .env("SANDBOX_DATA_PATH", app_data_dir.join("sandbox-data"))
            .env("SKILLS_DIR", app_data_dir.join("skills"))
            .spawn()
            .map_err(|e| format!("Failed to start backend: {}", e))?;

        let (tx, rx_port) = std::sync::mpsc::channel();
        let mut rx = rx;
        
        // Spawn a thread to read stdout/stderr and extract the port
        tauri::async_runtime::spawn(async move {
            let mut port_found = false;
            while let Some(event) = rx.recv().await {
                match event {
                    CommandEvent::Stdout(line) => {
                        let line_str = String::from_utf8_lossy(&line);
                        println!("BE: {}", line_str);
                        
                        // Look for the magic string "SERVER_PORT:<port>"
                        // This avoids the race condition of finding a port before binding
                        if !port_found {
                            if let Some(idx) = line_str.find("SERVER_PORT:") {
                                let after_port = &line_str[idx + "SERVER_PORT:".len()..];
                                // Extract port number (first token after prefix)
                                if let Some(port_token) = after_port.split_whitespace().next() {
                                    if let Ok(port) = port_token.parse::<u16>() {
                                        let _ = tx.send(port);
                                        port_found = true;
                                    }
                                }
                            }
                        }
                    }
                    CommandEvent::Stderr(line) => {
                        println!("BE ERR: {}", String::from_utf8_lossy(&line));
                    }
                    _ => {}
                }
            }
        });

        self.child = Some(child);
        
        // Wait for the port to be reported (with a timeout)
        // We give it 45 seconds to start up and report the port (initial setup can be slow)
        match rx_port.recv_timeout(Duration::from_secs(45)) {
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
        let url = format!("http://127.0.0.1:{}/api/config", self.port);
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(1))
            .build()
            .map_err(|e| format!("Failed to create HTTP client: {}", e))?;

        // 30 attempts * 500ms = 15 seconds timeout (after port is reported)
        for attempt in 1..=30 {
            thread::sleep(Duration::from_millis(500));

            if let Ok(resp) = client.get(&url).send() {
                // Accept success or 404 (endpoint exists but might not have data yet)
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
        if let Some(child) = self.child.take() {
            let _ = child.kill();
        }
    }
}

impl Drop for BackendProcess {
    fn drop(&mut self) {
        self.stop();
    }
}
