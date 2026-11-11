//! What closing the main window does when a tray icon is available: ask,
//! hide to the tray, or quit. The choice is a one-word file next to the other
//! desktop preferences so Rust can read it before the webview answers.
//!
//! "Ask" hands the decision to the webview's prompt. If the webview does not
//! acknowledge the prompt quickly (still loading, hung), the window hides, so
//! the close button never silently does nothing.

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use tauri::{AppHandle, Emitter, Manager, Runtime};

use crate::tray::TrayHost;

pub const PROMPT_EVENT: &str = "close-prompt";
const PROMPT_ACK_TIMEOUT: Duration = Duration::from_millis(1500);

static PROMPT_SEQ: AtomicU64 = AtomicU64::new(0);
static PROMPT_ACKED: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CloseAction {
    Ask,
    Tray,
    Quit,
}

impl CloseAction {
    pub fn parse(value: &str) -> Option<Self> {
        match value.trim() {
            "ask" => Some(Self::Ask),
            "tray" => Some(Self::Tray),
            "quit" => Some(Self::Quit),
            _ => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Ask => "ask",
            Self::Tray => "tray",
            Self::Quit => "quit",
        }
    }

    /// macOS apps conventionally stay alive when their window closes, so
    /// only Windows asks until the user picks.
    pub fn default_for(host: TrayHost) -> Self {
        match host {
            TrayHost::MacOs => Self::Tray,
            _ => Self::Ask,
        }
    }
}

fn preference_path(root: &Path) -> PathBuf {
    root.join(".suzent").join("close-action")
}

pub fn load(root: &Path, host: TrayHost) -> CloseAction {
    fs::read_to_string(preference_path(root))
        .ok()
        .and_then(|value| CloseAction::parse(&value))
        .unwrap_or_else(|| CloseAction::default_for(host))
}

pub fn save(root: &Path, action: CloseAction) -> Result<(), String> {
    let path = preference_path(root);
    if let Some(dir) = path.parent() {
        fs::create_dir_all(dir).map_err(|error| error.to_string())?;
    }
    fs::write(path, action.as_str()).map_err(|error| error.to_string())
}

pub fn current() -> CloseAction {
    load(
        &crate::backend::find_install_workspace_dir(),
        TrayHost::current(),
    )
}

pub fn hide_main<R: Runtime>(app: &AppHandle<R>) {
    if let Some(window) = app.get_webview_window("main") {
        if let Err(error) = window.hide() {
            eprintln!("Could not hide the window: {error}");
        }
    }
}

/// Asks the webview to show the close prompt, hiding the window instead if
/// the prompt is not acknowledged in time.
pub fn prompt<R: Runtime>(app: &AppHandle<R>) {
    let seq = PROMPT_SEQ.fetch_add(1, Ordering::SeqCst) + 1;
    if app.emit_to("main", PROMPT_EVENT, seq).is_err() {
        hide_main(app);
        return;
    }
    let app = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(PROMPT_ACK_TIMEOUT);
        if PROMPT_ACKED.load(Ordering::SeqCst) < seq {
            let handle = app.clone();
            let _ = app.run_on_main_thread(move || hide_main(&handle));
        }
    });
}

#[tauri::command]
pub fn ack_close_prompt(seq: u64) {
    PROMPT_ACKED.fetch_max(seq, Ordering::SeqCst);
}

/// `None` where there is no tray, so closing always quits and the setting
/// does not apply.
#[tauri::command]
pub fn get_close_action() -> Option<String> {
    TrayHost::current()
        .supports_tray()
        .then(|| current().as_str().to_string())
}

#[tauri::command]
pub fn set_close_action(action: String) -> Result<(), String> {
    let action =
        CloseAction::parse(&action).ok_or_else(|| format!("Unknown close action: {action}"))?;
    save(&crate::backend::find_install_workspace_dir(), action)
}

/// The prompt's answer. `choice` is "tray" or "quit"; `remember` stores it.
#[tauri::command]
pub fn resolve_close(app: AppHandle, choice: String, remember: bool) -> Result<(), String> {
    let action = match CloseAction::parse(&choice) {
        Some(action @ (CloseAction::Tray | CloseAction::Quit)) => action,
        _ => return Err(format!("Unknown close choice: {choice}")),
    };
    if remember {
        save(&crate::backend::find_install_workspace_dir(), action)?;
    }
    match action {
        CloseAction::Quit => crate::tray::quit(&app),
        _ => hide_main(&app),
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{load, save, CloseAction};
    use crate::tray::TrayHost;

    #[test]
    fn windows_asks_and_macos_hides_until_the_user_picks() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(load(dir.path(), TrayHost::Windows), CloseAction::Ask);
        assert_eq!(load(dir.path(), TrayHost::MacOs), CloseAction::Tray);
    }

    #[test]
    fn a_saved_choice_wins_and_junk_falls_back() {
        let dir = tempfile::tempdir().unwrap();
        save(dir.path(), CloseAction::Quit).unwrap();
        assert_eq!(load(dir.path(), TrayHost::Windows), CloseAction::Quit);
        std::fs::write(dir.path().join(".suzent").join("close-action"), "nope").unwrap();
        assert_eq!(load(dir.path(), TrayHost::Windows), CloseAction::Ask);
    }
}
