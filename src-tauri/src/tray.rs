//! Windows notification area and macOS menu bar.
//!
//! Closing the main window hides it, quits, or asks, per the user's close
//! preference (see `close_action`). A hidden app, and any backend it owns,
//! keeps running until an explicit quit. Quit, restart, and the updater call
//! `AppHandle::exit`, which does not go through this hide path, so child
//! cleanup and staged updates still run.
//!
//! If the icon cannot be created, close is left alone. The app must not stay
//! up with no window and no way to quit.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, Runtime};

use crate::close_action::CloseAction;

pub const SHOW_ID: &str = "tray-show";
pub const QUIT_ID: &str = "tray-quit";

static TRAY_READY: AtomicBool = AtomicBool::new(false);
static EXITING: AtomicBool = AtomicBool::new(false);
static QUIT_HOOK_INSTALLED: AtomicBool = AtomicBool::new(false);

pub struct TrayState {
    items: Mutex<Option<TrayItems>>,
}

struct TrayItems {
    show: MenuItem<tauri::Wry>,
    quit: MenuItem<tauri::Wry>,
}

impl Default for TrayState {
    fn default() -> Self {
        Self {
            items: Mutex::new(None),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TrayHost {
    Windows,
    MacOs,
    Unsupported,
}

impl TrayHost {
    pub fn current() -> Self {
        if cfg!(windows) {
            Self::Windows
        } else if cfg!(target_os = "macos") {
            Self::MacOs
        } else {
            Self::Unsupported
        }
    }

    pub fn supports_tray(self) -> bool {
        matches!(self, Self::Windows | Self::MacOs)
    }

    /// macOS menu-bar extras open their menu on click. Windows uses the left
    /// click to restore the window and the right click for the menu.
    pub fn menu_on_left_click(self) -> bool {
        matches!(self, Self::MacOs)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CloseDecision {
    Hide,
    Allow,
}

pub fn decide_close(host: TrayHost, tray_ready: bool, exiting: bool) -> CloseDecision {
    if exiting || !tray_ready || !host.supports_tray() {
        CloseDecision::Allow
    } else {
        CloseDecision::Hide
    }
}

/// Child webviews (previews, embedded pages) still close on their own.
pub fn should_hide_on_close(label: &str, host: TrayHost, tray_ready: bool, exiting: bool) -> bool {
    label == "main" && decide_close(host, tray_ready, exiting) == CloseDecision::Hide
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MenuAction {
    Show,
    Quit,
}

pub fn menu_action(id: &str) -> Option<MenuAction> {
    match id {
        SHOW_ID => Some(MenuAction::Show),
        QUIT_ID => Some(MenuAction::Quit),
        _ => None,
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TrayClick {
    PrimaryUp,
    Other,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ClickAction {
    Restore,
    None,
}

pub fn click_action(host: TrayHost, click: TrayClick) -> ClickAction {
    match (host, click) {
        (TrayHost::Windows, TrayClick::PrimaryUp) => ClickAction::Restore,
        _ => ClickAction::None,
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RevealPlan {
    pub show: bool,
    pub unminimize: bool,
    pub focus: bool,
}

/// Hidden, minimized, and already-visible windows all come forward.
/// Restoring never hides, so a double-click cannot dismiss the window.
pub fn reveal_plan() -> RevealPlan {
    RevealPlan {
        show: true,
        unminimize: true,
        focus: true,
    }
}

pub fn activates_app(host: TrayHost) -> bool {
    matches!(host, TrayHost::MacOs)
}

pub struct TrayCopy {
    pub show: &'static str,
    pub quit: &'static str,
    pub tooltip: &'static str,
}

pub fn copy_for_language(language: &str) -> TrayCopy {
    let normalized = language.trim().to_ascii_lowercase().replace('_', "-");
    let normalized = normalized
        .split(['.', '@'])
        .next()
        .unwrap_or(normalized.as_str());
    if normalized.starts_with("zh") {
        TrayCopy {
            show: "打开",
            quit: "退出",
            tooltip: "SUZENT",
        }
    } else {
        TrayCopy {
            show: "Open",
            quit: "Quit",
            tooltip: "SUZENT",
        }
    }
}

pub fn macos_template_bytes() -> &'static [u8] {
    include_bytes!("../icons/tray-template.png")
}

pub fn windows_tray_bytes() -> &'static [u8] {
    include_bytes!("../icons/32x32.png")
}

pub fn mark_exiting() {
    EXITING.store(true, Ordering::SeqCst);
}

pub fn is_exiting() -> bool {
    EXITING.load(Ordering::SeqCst)
}

fn tray_is_ready() -> bool {
    TRAY_READY.load(Ordering::SeqCst)
}

pub fn reveal_main<R: Runtime>(app: &AppHandle<R>) {
    let Some(window) = app.get_webview_window("main") else {
        return;
    };
    let plan = reveal_plan();
    if plan.show {
        let _ = window.show();
    }
    if plan.unminimize {
        let _ = window.unminimize();
    }
    #[cfg(target_os = "macos")]
    if activates_app(TrayHost::current()) {
        // A miniaturized or hidden window does not become key until the app
        // itself is active. Dock and menu-bar restores both need that.
        let _ = app.show();
    }
    if plan.focus {
        let _ = window.set_focus();
    }
}

pub fn on_close_requested<R: Runtime>(window: &tauri::Window<R>, api: &tauri::CloseRequestApi) {
    if !should_hide_on_close(
        window.label(),
        TrayHost::current(),
        tray_is_ready(),
        is_exiting(),
    ) {
        return;
    }
    match crate::close_action::current() {
        CloseAction::Quit => {
            api.prevent_close();
            quit(window.app_handle());
        }
        CloseAction::Ask => {
            api.prevent_close();
            crate::close_action::prompt(window.app_handle());
        }
        // Hide first. prevent_close only after that succeeds, so a failed hide
        // still closes the window instead of leaving an invisible app.
        CloseAction::Tray => match window.hide() {
            Ok(()) => api.prevent_close(),
            Err(error) => {
                eprintln!("Could not hide the window, so it will close: {error}");
            }
        },
    }
}

/// An explicit quit: skips the hide path so child cleanup and staged
/// updates still run.
pub fn quit<R: Runtime>(app: &AppHandle<R>) {
    mark_exiting();
    app.exit(0);
}

fn on_menu(app: &AppHandle, id: &str) {
    if let Some(chat_id) = id.strip_prefix(crate::tray_status::CHAT_PREFIX) {
        crate::tray_status::open_chat(app, chat_id);
        return;
    }
    match menu_action(id) {
        Some(MenuAction::Show) => reveal_main(app),
        Some(MenuAction::Quit) => quit(app),
        None => {}
    }
}

fn on_tray_click<R: Runtime>(icon: &tauri::tray::TrayIcon<R>, event: TrayIconEvent) {
    let click = match event {
        TrayIconEvent::Click {
            button: MouseButton::Left,
            button_state: MouseButtonState::Up,
            ..
        } => TrayClick::PrimaryUp,
        _ => TrayClick::Other,
    };
    if click_action(TrayHost::current(), click) == ClickAction::Restore {
        reveal_main(icon.app_handle());
    }
}

pub fn install(app: &AppHandle) -> Result<(), String> {
    let host = TrayHost::current();
    if !host.supports_tray() {
        return Ok(());
    }
    let copy = copy_for_language(&system_language());
    let show = MenuItem::with_id(app, SHOW_ID, copy.show, true, None::<&str>)
        .map_err(|error| error.to_string())?;
    let quit = MenuItem::with_id(app, QUIT_ID, copy.quit, true, None::<&str>)
        .map_err(|error| error.to_string())?;
    let separator = PredefinedMenuItem::separator(app).map_err(|error| error.to_string())?;
    let menu =
        Menu::with_items(app, &[&show, &separator, &quit]).map_err(|error| error.to_string())?;
    let icon = tauri::image::Image::from_bytes(match host {
        TrayHost::MacOs => macos_template_bytes(),
        TrayHost::Windows => windows_tray_bytes(),
        TrayHost::Unsupported => unreachable!("unsupported hosts return above"),
    })
    .map_err(|error| error.to_string())?;

    TrayIconBuilder::with_id("tray")
        .tooltip(copy.tooltip)
        .icon(icon)
        .icon_as_template(host == TrayHost::MacOs)
        .menu(&menu)
        .show_menu_on_left_click(host.menu_on_left_click())
        .on_menu_event(|app, event| on_menu(app, event.id().as_ref()))
        .on_tray_icon_event(on_tray_click)
        .build(app)
        .map_err(|error| error.to_string())?;

    if let Some(state) = app.try_state::<TrayState>() {
        if let Ok(mut items) = state.items.lock() {
            *items = Some(TrayItems { show, quit });
        }
    }
    TRAY_READY.store(true, Ordering::SeqCst);
    crate::tray_status::start(app.clone(), system_language());
    install_quit_hook_if_needed();
    println!(
        "Closing the window leaves Suzent in the {}",
        match host {
            TrayHost::MacOs => "menu bar",
            TrayHost::Windows => "notification area",
            TrayHost::Unsupported => "background",
        }
    );
    Ok(())
}

/// Dock Quit and Cmd+Q on macOS ask the process to terminate, which then
/// delivers a window close. That has to count as an explicit exit before the
/// close handler runs, or the close would hide the window and cancel the quit.
pub fn install_quit_hook_if_needed() {
    if !tray_is_ready() || QUIT_HOOK_INSTALLED.load(Ordering::SeqCst) {
        return;
    }
    #[cfg(target_os = "macos")]
    if !install_macos_quit_hook() {
        return;
    }
    QUIT_HOOK_INSTALLED.store(true, Ordering::SeqCst);
}

#[cfg(target_os = "macos")]
fn install_macos_quit_hook() -> bool {
    use objc2::ffi::class_addMethod;
    use objc2::runtime::{AnyClass, AnyObject, Imp, Sel};
    use std::ffi::{c_char, CStr};

    // NSTerminateNow. Returning this lets AppKit proceed; the close that
    // follows sees `EXITING` and is allowed through.
    const NS_TERMINATE_NOW: usize = 1;

    extern "C-unwind" fn application_should_terminate(
        _this: *mut AnyObject,
        _sel: Sel,
        _sender: *mut AnyObject,
    ) -> usize {
        mark_exiting();
        NS_TERMINATE_NOW
    }

    // tao's NSApplication delegate does not implement this selector. Adding
    // it is what distinguishes the red close button from Dock Quit / Cmd+Q.
    const CANDIDATES: &[&CStr] = &[c"TaoAppDelegateParent", c"TaoAppDelegate"];
    let Some(class) = CANDIDATES.iter().find_map(|name| AnyClass::get(name)) else {
        eprintln!(
            "macOS quit hook was not installed. Quit in the menu bar still exits; Dock Quit may only hide the window."
        );
        return false;
    };
    let selector = Sel::register(c"applicationShouldTerminate:");
    if class.instance_method(selector).is_some() {
        return true;
    }
    let added = unsafe {
        class_addMethod(
            std::ptr::from_ref(class).cast_mut(),
            selector,
            std::mem::transmute::<
                extern "C-unwind" fn(*mut AnyObject, Sel, *mut AnyObject) -> usize,
                Imp,
            >(application_should_terminate),
            c"Q@:@".as_ptr().cast::<c_char>(),
        )
    };
    if added.as_bool() {
        return true;
    }
    eprintln!("Could not install the macOS quit hook.");
    false
}

#[tauri::command]
pub fn set_tray_language(
    state: tauri::State<'_, TrayState>,
    language: String,
) -> Result<(), String> {
    crate::tray_status::set_language(&language);
    let copy = copy_for_language(&language);
    let items = state
        .items
        .lock()
        .map_err(|error| format!("Lock error: {error}"))?;
    let Some(items) = items.as_ref() else {
        return Ok(());
    };
    items
        .show
        .set_text(copy.show)
        .map_err(|error| error.to_string())?;
    items
        .quit
        .set_text(copy.quit)
        .map_err(|error| error.to_string())?;
    Ok(())
}

fn env_language() -> Option<String> {
    std::env::var("LC_ALL")
        .or_else(|_| std::env::var("LANG"))
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty() && value != "C" && value != "POSIX")
}

#[cfg(windows)]
fn system_language() -> String {
    if let Some(language) = env_language() {
        return language;
    }
    use windows_sys::Win32::Globalization::GetUserDefaultLocaleName;
    let mut buffer = [0u16; 85];
    let len = unsafe { GetUserDefaultLocaleName(buffer.as_mut_ptr(), buffer.len() as i32) };
    if len <= 1 {
        return String::new();
    }
    String::from_utf16_lossy(&buffer[..len as usize - 1])
}

#[cfg(target_os = "macos")]
fn system_language() -> String {
    if let Some(language) = env_language() {
        return language;
    }
    // GUI launches often have no LANG. AppleLocale is the per-user language
    // until the webview reports the language chosen in Settings.
    std::process::Command::new("defaults")
        .args(["read", "-g", "AppleLocale"])
        .output()
        .ok()
        .filter(|output| output.status.success())
        .and_then(|output| String::from_utf8(output.stdout).ok())
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_default()
}

#[cfg(not(any(windows, target_os = "macos")))]
fn system_language() -> String {
    env_language().unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::{
        activates_app, click_action, copy_for_language, decide_close, macos_template_bytes,
        menu_action, reveal_plan, should_hide_on_close, windows_tray_bytes, ClickAction,
        CloseDecision, MenuAction, TrayClick, TrayHost,
    };

    #[test]
    fn closing_with_a_tray_hides_and_keeps_the_process() {
        assert_eq!(
            decide_close(TrayHost::Windows, true, false),
            CloseDecision::Hide
        );
        assert_eq!(
            decide_close(TrayHost::MacOs, true, false),
            CloseDecision::Hide
        );
    }

    #[test]
    fn explicit_exit_is_not_swallowed_by_the_tray() {
        // Quit, Dock Quit, restart, and the updater all set the exiting flag
        // before the window close that shutdown delivers. Allowing that close
        // is what lets the process end and the owned backend stop.
        for host in [TrayHost::Windows, TrayHost::MacOs] {
            assert_eq!(decide_close(host, true, true), CloseDecision::Allow);
        }
    }

    #[test]
    fn a_failed_tray_does_not_trap_the_app() {
        assert_eq!(
            decide_close(TrayHost::Windows, false, false),
            CloseDecision::Allow
        );
        assert_eq!(
            decide_close(TrayHost::MacOs, false, false),
            CloseDecision::Allow
        );
    }

    #[test]
    fn linux_never_hides_on_close() {
        let host = TrayHost::Unsupported;
        assert!(!host.supports_tray());
        assert_eq!(decide_close(host, true, false), CloseDecision::Allow);
        assert!(!should_hide_on_close("main", host, true, false));
    }

    #[test]
    fn this_host_matches_the_platform() {
        let host = TrayHost::current();
        if cfg!(windows) {
            assert_eq!(host, TrayHost::Windows);
        } else if cfg!(target_os = "macos") {
            assert_eq!(host, TrayHost::MacOs);
        } else {
            assert_eq!(host, TrayHost::Unsupported);
        }
    }

    #[test]
    fn only_the_main_window_hides() {
        assert!(should_hide_on_close("main", TrayHost::Windows, true, false));
        assert!(!should_hide_on_close(
            "preview",
            TrayHost::Windows,
            true,
            false
        ));
        assert!(!should_hide_on_close("main", TrayHost::Windows, true, true));
    }

    #[test]
    fn menu_offers_show_and_quit() {
        assert_eq!(menu_action("tray-show"), Some(MenuAction::Show));
        assert_eq!(menu_action("tray-quit"), Some(MenuAction::Quit));
        assert_eq!(menu_action("toggle"), None);
        assert_ne!(menu_action("tray-show"), menu_action("tray-quit"));
    }

    #[test]
    fn click_follows_the_platform() {
        assert!(TrayHost::MacOs.menu_on_left_click());
        assert!(!TrayHost::Windows.menu_on_left_click());
        assert!(!TrayHost::Unsupported.menu_on_left_click());
        assert_eq!(
            click_action(TrayHost::Windows, TrayClick::PrimaryUp),
            ClickAction::Restore
        );
        assert_eq!(
            click_action(TrayHost::Windows, TrayClick::Other),
            ClickAction::None
        );
        assert_eq!(
            click_action(TrayHost::MacOs, TrayClick::PrimaryUp),
            ClickAction::None
        );
    }

    #[test]
    fn reveal_restores_minimized_windows_and_focuses() {
        let plan = reveal_plan();
        assert!(plan.show);
        assert!(plan.unminimize);
        assert!(plan.focus);
        assert!(activates_app(TrayHost::MacOs));
        assert!(!activates_app(TrayHost::Windows));
    }

    #[test]
    fn menu_copy_follows_the_app_language() {
        assert_eq!(copy_for_language("en-US").show, "Open");
        assert_eq!(copy_for_language("en-US").quit, "Quit");
        assert_eq!(copy_for_language("zh-CN").show, "打开");
        assert_eq!(copy_for_language("zh_CN.UTF-8").quit, "退出");
        assert_eq!(copy_for_language("zh-Hans").show, "打开");
        assert_eq!(copy_for_language("").quit, "Quit");
        assert_eq!(copy_for_language("zh-CN").tooltip, "SUZENT");
        assert!(!copy_for_language("en").show.is_empty());
    }

    #[test]
    fn macos_template_is_black_ink_on_a_clear_background() {
        let image =
            tauri::image::Image::from_bytes(macos_template_bytes()).expect("template png decodes");
        assert_eq!((image.width(), image.height()), (44, 44));
        let rgba = image.rgba();
        let mut ink = 0usize;
        let mut clear = 0usize;
        for pixel in rgba.chunks(4) {
            if pixel[3] == 0 {
                clear += 1;
                continue;
            }
            assert_eq!(&pixel[0..3], &[0, 0, 0], "template ink is black");
            if pixel[3] > 200 {
                ink += 1;
            }
        }
        assert!(ink > 40, "the menu-bar glyph is visible");
        assert!(clear > ink, "the menu bar shows through");
        for (x, y) in [(0, 0), (43, 0), (0, 43), (43, 43)] {
            let index = ((y * 44 + x) * 4) as usize;
            assert_eq!(rgba[index + 3], 0, "corner {x},{y} stays clear");
        }
    }

    #[test]
    fn windows_tray_icon_stays_legible_on_light_and_dark_bars() {
        let image =
            tauri::image::Image::from_bytes(windows_tray_bytes()).expect("windows icon decodes");
        assert_eq!((image.width(), image.height()), (32, 32));
        let rgba = image.rgba();
        let opaque = rgba.chunks(4).filter(|pixel| pixel[3] > 200).count();
        let light = rgba
            .chunks(4)
            .filter(|pixel| pixel[0] > 200 && pixel[1] > 200 && pixel[2] > 200)
            .count();
        let dark = rgba
            .chunks(4)
            .filter(|pixel| pixel[0] < 40 && pixel[1] < 40 && pixel[2] < 40)
            .count();
        assert!(opaque > 32 * 32 * 4 / 5, "the tile does not vanish");
        assert!(light > 10, "eyes stay visible on a dark tray");
        assert!(dark > 10, "the tile stays visible on a light tray");
        assert_ne!(macos_template_bytes(), windows_tray_bytes());
    }
}
