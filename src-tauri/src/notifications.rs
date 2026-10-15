//! Native notifications that bring Suzent back to the front when clicked.
//!
//! `tauri-plugin-notification` shows desktop notifications but never reports a
//! click on them, so these are sent with `notify-rust` directly and a thread
//! waits for the user's response.

use notify_rust::{Notification, NotificationResponse};
use tauri::{AppHandle, Manager, Runtime};

pub fn focus_main_window<R: Runtime>(app: &AppHandle<R>) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn build_notification<R: Runtime>(app: &AppHandle<R>, title: &str, body: &str) -> Notification {
    let mut notification = Notification::new();
    notification.summary(title).body(body).auto_icon();

    #[cfg(any(windows, target_os = "macos"))]
    let identifier = app.config().identifier.clone();
    #[cfg(not(any(windows, target_os = "macos")))]
    let _ = app;

    // Without a default action most Linux notification servers treat a click
    // on the body as a dismissal.
    #[cfg(all(unix, not(target_os = "macos")))]
    notification.action("default", "Open");

    // Mirrors the plugin: the AppUserModel ID only resolves for the installed
    // app, and a dev build would otherwise show nothing.
    #[cfg(windows)]
    if !tauri::is_dev() {
        notification.app_id(&identifier);
    }

    #[cfg(target_os = "macos")]
    {
        let _ = notify_rust::set_application(if tauri::is_dev() {
            "com.apple.Terminal"
        } else {
            &identifier
        });
    }

    notification
}

#[tauri::command]
pub fn show_notification<R: Runtime>(app: AppHandle<R>, title: String, body: String) {
    let notification = build_notification(&app, &title, &body);
    // Waiting for the response blocks until the notification is clicked or
    // dismissed, so each one gets its own thread.
    std::thread::spawn(move || {
        let handle = match notification.show() {
            Ok(handle) => handle,
            Err(err) => {
                eprintln!("[notifications] failed to show notification: {err}");
                return;
            }
        };
        let _ = handle.wait_for_response(|response: &NotificationResponse| {
            if response.is_default_action() {
                focus_main_window(&app);
            }
        });
    });
}
