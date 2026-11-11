//! Live status in the tray: chats waiting on the user, chats running, and
//! whether the backend answers at all.
//!
//! A thread polls `GET /focal/chats` on the local backend and, only when the
//! picture changes, rebuilds the tray menu, tooltip and icon badge. Polling
//! from Rust rather than the webview keeps it current while the window is
//! hidden, when the webview may be throttled.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use serde::Deserialize;
use tauri::image::Image;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::{AppHandle, Emitter, Manager};

pub const CHAT_PREFIX: &str = "tray-chat:";
const POLL_EVERY: Duration = Duration::from_secs(4);
const MAX_LISTED: usize = 4;
const TITLE_MAX_CHARS: usize = 28;

static LANGUAGE: Mutex<String> = Mutex::new(String::new());
static FORCE_REFRESH: AtomicBool = AtomicBool::new(false);

#[derive(Clone, Debug, Default, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct ChatRow {
    pub chat_id: String,
    pub title: Option<String>,
    pub state: String,
    pub waiting_kind: Option<String>,
}

#[derive(Debug, Default, Deserialize)]
struct ChatStates {
    #[serde(default)]
    chats: Vec<ChatRow>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Snapshot {
    Starting,
    Unreachable,
    Ready {
        waiting: Vec<ChatRow>,
        running: Vec<ChatRow>,
    },
}

impl Snapshot {
    pub fn from_rows(rows: Vec<ChatRow>) -> Self {
        let (waiting, rest): (Vec<_>, Vec<_>) =
            rows.into_iter().partition(|row| row.state == "waiting");
        let running = rest
            .into_iter()
            .filter(|row| row.state == "running")
            .collect();
        Self::Ready { waiting, running }
    }

    pub fn needs_attention(&self) -> bool {
        matches!(self, Self::Ready { waiting, .. } if !waiting.is_empty())
    }
}

struct Copy {
    zh: bool,
}

impl Copy {
    fn current() -> Self {
        let language = LANGUAGE.lock().map(|l| l.clone()).unwrap_or_default();
        Self {
            zh: language.trim().to_ascii_lowercase().starts_with("zh"),
        }
    }

    fn pick(&self, zh: &'static str, en: &'static str) -> &'static str {
        if self.zh {
            zh
        } else {
            en
        }
    }

    fn waiting_kind(&self, kind: Option<&str>) -> &'static str {
        match kind {
            Some("question") => self.pick("有问题问你", "has a question"),
            Some("approval") => self.pick("等你批准", "needs approval"),
            Some("task") => self.pick("任务卡住了", "task is blocked"),
            _ => self.pick("等你回复", "waiting for you"),
        }
    }
}

fn clip(title: Option<&str>, fallback: &str) -> String {
    let title = title
        .map(str::trim)
        .filter(|t| !t.is_empty())
        .unwrap_or(fallback);
    if title.chars().count() <= TITLE_MAX_CHARS {
        return title.to_string();
    }
    let mut short: String = title.chars().take(TITLE_MAX_CHARS - 1).collect();
    short.push('…');
    short
}

pub fn tooltip(snapshot: &Snapshot, zh: bool) -> String {
    let copy = Copy { zh };
    match snapshot {
        Snapshot::Starting => format!("SUZENT · {}", copy.pick("正在启动…", "starting…")),
        Snapshot::Unreachable => format!("SUZENT · {}", copy.pick("后端未连接", "backend offline")),
        Snapshot::Ready { waiting, running } => match (waiting.len(), running.len()) {
            (0, 0) => format!("SUZENT · {}", copy.pick("一切就绪", "all clear")),
            (w, r) if zh => {
                let mut parts = Vec::new();
                if w > 0 {
                    parts.push(format!("{w} 个聊天在等你"));
                }
                if r > 0 {
                    parts.push(format!("{r} 个正在运行"));
                }
                format!("SUZENT · {}", parts.join(" · "))
            }
            (w, r) => {
                let mut parts = Vec::new();
                if w > 0 {
                    parts.push(format!("{w} waiting for you"));
                }
                if r > 0 {
                    parts.push(format!("{r} running"));
                }
                format!("SUZENT · {}", parts.join(" · "))
            }
        },
    }
}

fn build_menu(app: &AppHandle, snapshot: &Snapshot) -> tauri::Result<Menu<tauri::Wry>> {
    let copy = Copy::current();
    let menu = Menu::new(app)?;
    let untitled = copy.pick("未命名聊天", "Untitled chat");

    match snapshot {
        Snapshot::Starting => {
            menu.append(&MenuItem::new(
                app,
                copy.pick("◌ 后端正在启动…", "◌ Backend starting…"),
                false,
                None::<&str>,
            )?)?;
        }
        Snapshot::Unreachable => {
            menu.append(&MenuItem::new(
                app,
                copy.pick("⚠ 后端未连接", "⚠ Backend offline"),
                false,
                None::<&str>,
            )?)?;
        }
        Snapshot::Ready { waiting, running } => {
            if waiting.is_empty() && running.is_empty() {
                menu.append(&MenuItem::new(
                    app,
                    copy.pick("✓ 没有等你处理的事", "✓ Nothing needs you"),
                    false,
                    None::<&str>,
                )?)?;
            }
            if !waiting.is_empty() {
                let header = if copy.zh {
                    format!("● 等你处理（{}）", waiting.len())
                } else {
                    format!("● Needs you ({})", waiting.len())
                };
                menu.append(&MenuItem::new(app, header, false, None::<&str>)?)?;
                for row in waiting.iter().take(MAX_LISTED) {
                    let label = format!(
                        "    {} — {}",
                        clip(row.title.as_deref(), untitled),
                        copy.waiting_kind(row.waiting_kind.as_deref())
                    );
                    let id = format!("{CHAT_PREFIX}{}", row.chat_id);
                    menu.append(&MenuItem::with_id(app, id, label, true, None::<&str>)?)?;
                }
            }
            if !running.is_empty() {
                if !waiting.is_empty() {
                    menu.append(&PredefinedMenuItem::separator(app)?)?;
                }
                let header = if copy.zh {
                    format!("▶ 正在运行（{}）", running.len())
                } else {
                    format!("▶ Running ({})", running.len())
                };
                menu.append(&MenuItem::new(app, header, false, None::<&str>)?)?;
                for row in running.iter().take(MAX_LISTED) {
                    let label = format!("    {}", clip(row.title.as_deref(), untitled));
                    let id = format!("{CHAT_PREFIX}{}", row.chat_id);
                    menu.append(&MenuItem::with_id(app, id, label, true, None::<&str>)?)?;
                }
            }
        }
    }

    menu.append(&PredefinedMenuItem::separator(app)?)?;
    menu.append(&MenuItem::with_id(
        app,
        crate::tray::SHOW_ID,
        copy.pick("打开", "Open"),
        true,
        None::<&str>,
    )?)?;
    menu.append(&MenuItem::with_id(
        app,
        crate::tray::QUIT_ID,
        copy.pick("退出", "Quit"),
        true,
        None::<&str>,
    )?)?;
    Ok(menu)
}

const ATTENTION_RGB: [u8; 3] = [255, 77, 61];
const BADGE_RADIUS: f32 = 0.19;
const BADGE_GAP: f32 = 0.06;
const OFFLINE_OPACITY: f32 = 0.45;

/// Puts a small dot in the bottom-right corner, clear of the logo's eyes,
/// and cuts a transparent gap around it so it reads on light and dark
/// taskbars alike. Edges are anti-aliased because the icon is tiny.
pub fn badged(base: &Image<'_>, rgb: [u8; 3]) -> Image<'static> {
    let (width, height) = (base.width(), base.height());
    let mut rgba = base.rgba().to_vec();
    let size = width.min(height) as f32;
    let radius = size * BADGE_RADIUS;
    let gap = (size * BADGE_GAP).max(1.0);
    let (cx, cy) = (width as f32 - radius - 0.5, height as f32 - radius - 0.5);
    for y in 0..height {
        for x in 0..width {
            let distance = ((x as f32 + 0.5 - cx).powi(2) + (y as f32 + 0.5 - cy).powi(2)).sqrt();
            let pixel = ((y * width + x) * 4) as usize;
            let keep = (distance - radius - gap + 0.5).clamp(0.0, 1.0);
            let dot = (radius - distance + 0.5).clamp(0.0, 1.0);
            let under = rgba[pixel + 3] as f32 / 255.0 * keep;
            let alpha = dot + under * (1.0 - dot);
            if alpha <= 0.0 {
                rgba[pixel..pixel + 4].copy_from_slice(&[0, 0, 0, 0]);
                continue;
            }
            for channel in 0..3 {
                let over = rgb[channel] as f32 * dot;
                let below = rgba[pixel + channel] as f32 * under * (1.0 - dot);
                rgba[pixel + channel] = ((over + below) / alpha).round() as u8;
            }
            rgba[pixel + 3] = (alpha * 255.0).round() as u8;
        }
    }
    Image::new_owned(rgba, width, height)
}

/// The same icon at reduced opacity, the usual tray cue for "disconnected".
pub fn faded(base: &Image<'_>) -> Image<'static> {
    let mut rgba = base.rgba().to_vec();
    for pixel in rgba.chunks_exact_mut(4) {
        pixel[3] = (pixel[3] as f32 * OFFLINE_OPACITY).round() as u8;
    }
    Image::new_owned(rgba, base.width(), base.height())
}

fn icon_for(snapshot: &Snapshot) -> Option<Image<'static>> {
    let base = Image::from_bytes(crate::tray::windows_tray_bytes()).ok()?;
    let base = Image::new_owned(base.rgba().to_vec(), base.width(), base.height());
    Some(match snapshot {
        _ if snapshot.needs_attention() => badged(&base, ATTENTION_RGB),
        Snapshot::Unreachable => faded(&base),
        _ => base,
    })
}

fn backend_port(app: &AppHandle) -> Option<u16> {
    let state = app.try_state::<crate::AppState>()?;
    let guard = state.backend.lock().ok()?;
    guard
        .as_ref()
        .map(|backend| backend.port)
        .filter(|port| *port != 0)
}

fn fetch(client: &reqwest::blocking::Client, port: u16) -> Snapshot {
    let url = format!("http://127.0.0.1:{port}/focal/chats");
    let body = client
        .get(url)
        .send()
        .and_then(|response| response.error_for_status())
        .and_then(|response| response.text());
    match body
        .ok()
        .and_then(|text| serde_json::from_str::<ChatStates>(&text).ok())
    {
        Some(states) => Snapshot::from_rows(states.chats),
        None => Snapshot::Unreachable,
    }
}

fn apply(app: &AppHandle, snapshot: &Snapshot) {
    let Some(tray) = app.tray_by_id("tray") else {
        return;
    };
    let zh = Copy::current().zh;
    let _ = tray.set_tooltip(Some(tooltip(snapshot, zh)));
    if cfg!(windows) {
        if let Some(icon) = icon_for(snapshot) {
            let _ = tray.set_icon(Some(icon));
        }
    }
    match build_menu(app, snapshot) {
        Ok(menu) => {
            let _ = tray.set_menu(Some(menu));
        }
        Err(error) => eprintln!("Could not rebuild the tray menu: {error}"),
    }
}

pub fn set_language(language: &str) {
    if let Ok(mut current) = LANGUAGE.lock() {
        *current = language.to_string();
    }
    FORCE_REFRESH.store(true, Ordering::SeqCst);
}

pub fn open_chat(app: &AppHandle, chat_id: &str) {
    crate::tray::reveal_main(app);
    let _ = app.emit("tray-open-chat", chat_id.to_string());
}

pub fn start(app: AppHandle, initial_language: String) {
    set_language(&initial_language);
    std::thread::spawn(move || {
        let client = match reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(3))
            .build()
        {
            Ok(client) => client,
            Err(error) => {
                eprintln!("Tray status is off: {error}");
                return;
            }
        };
        let mut last: Option<Snapshot> = None;
        loop {
            if crate::tray::is_exiting() {
                return;
            }
            let snapshot = match backend_port(&app) {
                Some(port) => fetch(&client, port),
                None => Snapshot::Starting,
            };
            let forced = FORCE_REFRESH.swap(false, Ordering::SeqCst);
            if forced || last.as_ref() != Some(&snapshot) {
                let handle = app.clone();
                let shown = snapshot.clone();
                let _ = app.run_on_main_thread(move || apply(&handle, &shown));
                last = Some(snapshot);
            }
            std::thread::sleep(POLL_EVERY);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::{badged, faded, tooltip, ChatRow, Snapshot};
    use tauri::image::Image;

    fn row(id: &str, state: &str) -> ChatRow {
        ChatRow {
            chat_id: id.into(),
            title: Some(id.into()),
            state: state.into(),
            waiting_kind: Some("question".into()),
        }
    }

    #[test]
    fn rows_split_into_waiting_and_running() {
        let snapshot = Snapshot::from_rows(vec![
            row("a", "waiting"),
            row("b", "running"),
            row("c", "idle"),
        ]);
        let Snapshot::Ready { waiting, running } = &snapshot else {
            panic!("expected ready");
        };
        assert_eq!(waiting.len(), 1);
        assert_eq!(running.len(), 1);
        assert!(snapshot.needs_attention());
    }

    #[test]
    fn tooltip_counts_what_needs_the_user() {
        let snapshot = Snapshot::from_rows(vec![
            row("a", "waiting"),
            row("b", "waiting"),
            row("c", "running"),
        ]);
        assert_eq!(
            tooltip(&snapshot, true),
            "SUZENT · 2 个聊天在等你 · 1 个正在运行"
        );
        assert_eq!(
            tooltip(&snapshot, false),
            "SUZENT · 2 waiting for you · 1 running"
        );
        assert_eq!(
            tooltip(&Snapshot::from_rows(vec![]), false),
            "SUZENT · all clear"
        );
    }

    fn pixel(image: &Image<'_>, x: u32, y: u32) -> Vec<u8> {
        let i = ((y * image.width() + x) * 4) as usize;
        image.rgba()[i..i + 4].to_vec()
    }

    #[test]
    fn badge_sits_bottom_right_with_a_clear_gap() {
        let base = Image::new_owned([20, 20, 20, 255].repeat(32 * 32), 32, 32);
        let image = badged(&base, [255, 0, 0]);
        assert_eq!(pixel(&image, 25, 25), vec![255, 0, 0, 255]);
        assert_eq!(pixel(&image, 25, 18)[3], 0, "gap above the dot is cut out");
        assert_eq!(
            pixel(&image, 8, 8),
            vec![20, 20, 20, 255],
            "rest of the logo untouched"
        );
    }

    #[test]
    fn offline_icon_is_faded_not_recoloured() {
        let base = Image::new_owned([20, 20, 20, 255].repeat(4), 2, 2);
        assert_eq!(pixel(&faded(&base), 1, 1), vec![20, 20, 20, 115]);
    }
}
