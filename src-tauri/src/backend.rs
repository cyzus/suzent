use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;
use std::net::TcpListener;
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

    /// Find an available port on localhost by binding to port 0.
    fn find_available_port() -> Result<u16, String> {
        TcpListener::bind("127.0.0.1:0")
            .and_then(|listener| listener.local_addr())
            .map(|addr| addr.port())
            .map_err(|e| format!("Failed to find available port: {}", e))
    }



    /// Start the Python backend as a sidecar process.
    /// Only called in release builds - in debug mode the backend runs separately.
    #[allow(dead_code)] // Only used in release builds via cfg
    pub fn start(&mut self, app_handle: &tauri::AppHandle) -> Result<u16, String> {
        let port = Self::find_available_port()?;
        self.port = port;


        let app_data_dir = app_handle.path()
            .app_data_dir()
            .map_err(|e| format!("Failed to get app data dir: {}", e))?;

        // Ensure app data directory exists for persistent storage
        std::fs::create_dir_all(&app_data_dir)
            .map_err(|e| format!("Failed to create app data dir: {}", e))?;

        // Start backend with environment variables for configuration
        let (rx, child) = app_handle.shell()
            .sidecar("suzent-backend")
            .map_err(|e| format!("Failed to create sidecar command: {}", e))?
            .env("SUZENT_PORT", port.to_string())
            .env("SUZENT_HOST", "127.0.0.1")
            .env("SUZENT_APP_DATA", &app_data_dir)
            .env("CHATS_DB_PATH", app_data_dir.join("chats.db"))
            .env("LANCEDB_URI", app_data_dir.join("memory"))
            .env("SANDBOX_DATA_PATH", app_data_dir.join("sandbox-data"))
            .env("SKILLS_DIR", app_data_dir.join("skills"))
            .spawn()
            .map_err(|e| format!("Failed to start backend: {}", e))?;

        let mut rx = rx;
        tauri::async_runtime::spawn(async move {
            while let Some(event) = rx.recv().await {
                match event {
                    CommandEvent::Stdout(line) => {
                        println!("BE: {}", String::from_utf8_lossy(&line));
                    }
                    CommandEvent::Stderr(line) => {
                        println!("BE ERR: {}", String::from_utf8_lossy(&line));
                    }
                    _ => {}
                }
            }
        });

        self.child = Some(child);
        self.wait_for_backend()?;

        Ok(port)
    }

    /// Poll the backend health endpoint until it responds or timeout.
    fn wait_for_backend(&self) -> Result<(), String> {
        let url = format!("http://127.0.0.1:{}/api/config", self.port);
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(2))
            .build()
            .map_err(|e| format!("Failed to create HTTP client: {}", e))?;

        // 60 attempts * 500ms = 30 seconds timeout
        for attempt in 1..=60 {
            thread::sleep(Duration::from_millis(500));

            if let Ok(resp) = client.get(&url).send() {
                // Accept success or 404 (endpoint exists but might not have data yet)
                if resp.status().is_success() || resp.status().as_u16() == 404 {
                    println!("Backend ready after {} attempts", attempt);
                    return Ok(());
                }
            }
        }

        Err("Backend failed to start within 30 seconds".to_string())
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
