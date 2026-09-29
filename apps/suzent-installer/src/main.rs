#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod git_install;
mod updater;

use serde::{Deserialize, Serialize};
use std::cell::RefCell;
use std::env;
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;
use tauri::Emitter;
use tauri::Manager;
use tauri_plugin_dialog::DialogExt;

const PROTOCOL_VERSION: u16 = 1;
const TARGET_PYTHON_VERSION: &str = "3.12";
const DEFAULT_BRANCH: &str = "main";
const REPO_URL: &str = "https://github.com/cyzus/suzent.git";
const UV_INSTALL_SH_URL: &str = "https://astral.sh/uv/install.sh";
const UV_INSTALL_PS1_URL: &str = "https://astral.sh/uv/install.ps1";
const RELEASE_BASE_URL: &str = "https://github.com/cyzus/suzent/releases/latest/download";
const LATEST_RELEASE_API: &str = "https://api.github.com/repos/cyzus/suzent/releases/latest";

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

thread_local! {
    static STAGE_LOGS: RefCell<Vec<String>> = const { RefCell::new(Vec::new()) };
}

#[derive(Clone, Copy)]
struct InstallStage {
    name: &'static str,
    title: &'static str,
    category: &'static str,
    needs_user_input: bool,
    worker: fn(&InstallConfig) -> StageOutcome,
}

#[derive(Clone)]
struct InstallConfig {
    dir: PathBuf,
    branch: String,
    branch_explicit: bool,
    skip_playwright: bool,
    china_mirror: bool,
    repo_url: String,
    repo_url_override: bool,
    uv_install_url: String,
    release_base_url: String,
    release_base_url_override: bool,
    release_tag_override: Option<String>,
    json: bool,
    non_interactive: bool,
}

#[derive(Deserialize)]
struct StageRequest {
    stage: String,
    dir: String,
}

#[derive(Deserialize)]
struct ReleaseResponse {
    tag_name: String,
}

#[derive(Default)]
struct StageOutcome {
    ok: bool,
    skipped: bool,
    reason: Option<String>,
}

#[derive(Serialize)]
struct ManifestPayload {
    protocol_version: u16,
    stages: Vec<ManifestStage>,
}

#[derive(Serialize)]
struct ManifestStage {
    name: &'static str,
    title: &'static str,
    category: &'static str,
    needs_user_input: bool,
}

#[derive(Serialize)]
struct StageResult {
    stage: String,
    ok: bool,
    skipped: bool,
    reason: Option<String>,
    duration_ms: u128,
    logs: Vec<String>,
}

#[derive(Serialize)]
struct InstallerContext {
    mode: &'static str,
    repair: bool,
    dir: String,
    target: String,
    branch: Option<String>,
    native_titlebar: bool,
}

#[derive(Serialize)]
struct DestinationInfo {
    kind: &'static str,
    branch: Option<String>,
}

fn inspect_destination_path(root: &Path) -> DestinationInfo {
    let info = |kind, branch| DestinationInfo { kind, branch };
    if !root.is_absolute() {
        return info("invalid", None);
    }
    if !root.exists() {
        return info("new", None);
    }
    if !root.is_dir() {
        return info("invalid", None);
    }
    if root.join(".git").exists()
        && (!root.join("pyproject.toml").is_file() || !root.join("src/suzent").is_dir())
    {
        return info("occupied", None);
    }
    if !root.join(".git").exists() {
        return info(
            if is_empty_dir(root) {
                "new"
            } else {
                "occupied"
            },
            None,
        );
    }
    let git = |args: &[&str]| {
        let mut command = Command::new("git");
        command.args(args).current_dir(root);
        hide_command_window(&mut command);
        command
            .output()
            .ok()
            .filter(|output| output.status.success())
            .map(|output| String::from_utf8_lossy(&output.stdout).trim().to_string())
    };
    let branch = git(&["branch", "--show-current"]).filter(|value| !value.is_empty());
    let channel = fs::read_to_string(root.join(".suzent/update-channel")).unwrap_or_default();
    if branch.is_some()
        || channel.trim() == "dev"
        || !root.join(".suzent-bootstrap-complete").is_file()
    {
        return info("development", branch);
    }
    if git(&["rev-parse", "HEAD"]).is_none() {
        return info("invalid", None);
    }
    let kind = if root.join(".suzent/update-transaction.json").exists()
        || !workspace_python(root).is_file()
    {
        "repair"
    } else {
        "update"
    };
    info(kind, None)
}

#[tauri::command]
async fn inspect_destination(dir: String) -> Result<DestinationInfo, String> {
    tauri::async_runtime::spawn_blocking(move || inspect_destination_path(Path::new(&dir)))
        .await
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn open_existing_updater(dir: String) -> Result<(), String> {
    let root = PathBuf::from(dir);
    let destination = inspect_destination_path(&root);
    let mode = match destination.kind {
        "update" => "--update",
        "repair" => "--repair",
        _ => return Err("This directory is not a managed release installation. Review its development update instructions instead.".into()),
    };
    let mut command = Command::new(env::current_exe().map_err(|error| error.to_string())?);
    command.args([mode, "--dir"]).arg(&root).current_dir(&root);
    hide_command_window(&mut command);
    command.spawn().map_err(|error| error.to_string())?;
    Ok(())
}

struct UpdateRuntime {
    args: Vec<String>,
    repair: bool,
    running: AtomicBool,
    result: Mutex<Option<UpdateResult>>,
}

#[derive(Clone, Serialize)]
struct UpdateResult {
    code: i32,
    error: Option<String>,
}

#[tauri::command]
fn updater_result(runtime: tauri::State<'_, Arc<UpdateRuntime>>) -> Option<UpdateResult> {
    runtime.result.lock().ok()?.clone()
}

#[tauri::command]
async fn save_diagnostics(app: tauri::AppHandle, content: String) -> Result<bool, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let Some(file) = app
            .dialog()
            .file()
            .set_file_name("suzent-diagnostics.txt")
            .blocking_save_file()
        else {
            return Ok(false);
        };
        let path = file.into_path().map_err(|error| error.to_string())?;
        fs::write(path, content).map_err(|error| error.to_string())?;
        Ok(true)
    })
    .await
    .map_err(|error| error.to_string())?
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    if has_flag(&args, "--update") || has_flag(&args, "--repair") {
        let repair = has_flag(&args, "--repair");
        if has_flag(&args, "--headless") {
            show_update_console();
            std::process::exit(updater::run(&args, repair));
        }
        run_update_tauri(args, repair);
        return;
    }
    if args.is_empty() {
        run_tauri_app();
        return;
    }

    let config = InstallConfig::from_env_and_args(&args);

    if has_flag(&args, "--protocol-version") {
        println!("{PROTOCOL_VERSION}");
        return;
    }

    if has_flag(&args, "--manifest") {
        print_json(&manifest(&config));
        return;
    }

    if let Some(stage_name) = flag_value(&args, "--stage") {
        run_stage_command(&config, &stage_name);
        return;
    }

    write_banner(&config);

    if has_flag(&args, "--preview") {
        print_preview(&config);
        exit_with_prompt(0, config.non_interactive);
    }

    for stage in stages(&config) {
        let result = run_stage(&config, stage);
        if config.json {
            print_json(&result);
        }
        if !result.ok {
            exit_with_prompt(1, config.non_interactive);
        }
    }

    if let Err(error) = write_bootstrap_marker(&config) {
        eprintln!("Failed to write bootstrap marker: {error}");
        exit_with_prompt(1, config.non_interactive);
    }
    if let Err(error) = write_install_dir_marker(&config.dir) {
        eprintln!("Failed to save install directory: {error}");
        exit_with_prompt(1, config.non_interactive);
    }

    print_completion(&config);
    exit_with_prompt(0, config.non_interactive);
}

#[tauri::command]
fn installer_manifest() -> Result<String, String> {
    let config = InstallConfig::from_env_and_args(&env::args().skip(1).collect::<Vec<_>>());
    serde_json::to_string(&manifest(&config)).map_err(|error| error.to_string())
}

#[tauri::command]
fn default_install_dir_command() -> String {
    default_install_dir().display().to_string()
}

#[tauri::command]
async fn run_installer_stage(request: StageRequest) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let args = vec![
            "--stage".to_string(),
            request.stage.clone(),
            "--json".to_string(),
            "--non-interactive".to_string(),
            "--dir".to_string(),
            request.dir,
        ];
        let mut config = InstallConfig::from_env_and_args(&env::args().skip(1).collect::<Vec<_>>());
        config.dir = PathBuf::from(flag_value(&args, "--dir").expect("stage directory"));
        config.json = true;
        config.non_interactive = true;
        if config.dir.join(".git").exists() && matches!(request.stage.as_str(), "git" | "repository") {
            return Err("An existing checkout must use update/repair, not first-time installation. No branch was changed.".into());
        }
        let Some(stage) = stages(&config)
            .into_iter()
            .find(|stage| stage.name == request.stage)
        else {
            let result = StageResult {
                stage: request.stage,
                ok: false,
                skipped: false,
                reason: Some("unknown installer stage".to_string()),
                duration_ms: 0,
                logs: Vec::new(),
            };
            return serde_json::to_string(&result).map_err(|error| error.to_string());
        };

        serde_json::to_string(&run_stage(&config, stage)).map_err(|error| error.to_string())
    })
    .await
    .map_err(|error| error.to_string())?
}

#[tauri::command]
fn installer_context() -> InstallerContext {
    let args: Vec<String> = env::args().skip(1).collect();
    let repair = has_flag(&args, "--repair");
    let config = InstallConfig::from_env_and_args(&args);
    InstallerContext {
        mode: if has_flag(&args, "--update") || repair {
            "update"
        } else {
            "install"
        },
        repair,
        dir: InstallConfig::from_env_and_args(&args)
            .dir
            .display()
            .to_string(),
        target: flag_value(&args, "--target").unwrap_or_default(),
        branch: config.branch_explicit.then_some(config.branch),
        native_titlebar: cfg!(target_os = "macos"),
    }
}

#[tauri::command]
fn updater_status() -> Option<String> {
    let args: Vec<String> = env::args().skip(1).collect();
    let root = flag_value(&args, "--dir").map(PathBuf::from)?;
    fs::read_to_string(root.join(".suzent").join("update-status.json")).ok()
}

#[tauri::command]
fn retry_update(
    app_handle: tauri::AppHandle,
    runtime: tauri::State<'_, Arc<UpdateRuntime>>,
    repair: Option<bool>,
) -> Result<(), String> {
    start_update_worker(
        app_handle,
        runtime.inner().clone(),
        repair.unwrap_or(runtime.repair),
        None,
    )
}

#[tauri::command]
async fn confirm_git_recovery(
    app_handle: tauri::AppHandle,
    runtime: tauri::State<'_, Arc<UpdateRuntime>>,
    chinese: bool,
) -> Result<bool, String> {
    let runtime = runtime.inner().clone();
    let error = runtime
        .result
        .lock()
        .map_err(|error| error.to_string())?
        .as_ref()
        .and_then(|result| result.error.clone())
        .filter(|error| error.starts_with("CONFIRM_GIT_RECOVERY:"))
        .ok_or("No Git recovery confirmation is pending")?;
    let status: serde_json::Value =
        serde_json::from_str(&updater_status().ok_or("Missing update status")?)
            .map_err(|error| error.to_string())?;
    let target = status["target_version"]
        .as_str()
        .filter(|tag| is_release_tag(tag))
        .ok_or("Missing recovery target")?
        .to_string();
    if !error.contains(&format!("\nTarget: {target}\n")) {
        return Err(
            "Update target changed; retry to review the new target before confirming".into(),
        );
    }
    let error = error
        .trim_start_matches("CONFIRM_GIT_RECOVERY: ")
        .to_string();
    let dialog_app = app_handle.clone();
    let dialog_parent = app_handle
        .get_webview_window("main")
        .ok_or("Missing updater window")?;
    let accepted = tauri::async_runtime::spawn_blocking(move || {
        dialog_app.dialog().message(format!("{}\n\n{error}", if chinese {
            "将停止此安装的程序，校验备份本地文件、Git index 和操作状态，再清理冲突并更新到下面的目标版本。本地修改不会自动合回；忽略文件和数据库不会被清理。失败可能需要手动恢复冲突现场。备份失败不会清理源码。"
        } else {
            "Stop this installation, verify backups of local files, Git index and operation state, then clear conflicts and update to the target below. Local changes are not reapplied. Ignored files and databases are not cleaned. Failure may require manual recovery of the conflict state. A failed backup never permits source cleanup."
        }))
        .parent(&dialog_parent)
        .title(if chinese { "确认备份并继续更新" } else { "Confirm backup and update" })
        .buttons(tauri_plugin_dialog::MessageDialogButtons::OkCancelCustom(
            if chinese { "备份并继续更新" } else { "Back up and update" }.into(),
            if chinese { "取消" } else { "Cancel" }.into(),
        )).blocking_show()
    }).await.map_err(|error| error.to_string())?;
    if accepted {
        start_update_worker(app_handle, runtime, false, Some(target))?;
    }
    Ok(accepted)
}

#[tauri::command]
fn launch_installed_app(dir: String) -> Result<(), String> {
    let workspace = PathBuf::from(dir);
    let ui = workspace.join("bin").join(ui_binary_name());
    if !ui.exists() {
        return Err(format!("Suzent app not found at {}", ui.display()));
    }

    let mut command = Command::new(&ui);
    command.current_dir(&workspace);
    hide_command_window(&mut command);
    command.spawn().map_err(|error| error.to_string())?;
    Ok(())
}

fn installer_context_config() -> tauri::Context<tauri::Wry> {
    let mut context = tauri::generate_context!();
    if cfg!(target_os = "macos") {
        for window in &mut context.config_mut().app.windows {
            window.decorations = true;
        }
    }
    context
}

fn run_tauri_app() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            installer_manifest,
            installer_context,
            default_install_dir_command,
            run_installer_stage,
            launch_installed_app,
            updater_status,
            save_diagnostics,
            inspect_destination,
            open_existing_updater,
        ])
        .run(installer_context_config())
        .expect("error while running Suzent installer");
}

fn run_update_tauri(args: Vec<String>, repair: bool) {
    let runtime = Arc::new(UpdateRuntime {
        args,
        repair,
        running: AtomicBool::new(false),
        result: Mutex::new(None),
    });
    let setup_runtime = runtime.clone();
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .manage(runtime)
        .invoke_handler(tauri::generate_handler![
            installer_context,
            updater_status,
            retry_update,
            confirm_git_recovery,
            updater_result,
            launch_installed_app,
            save_diagnostics,
        ])
        .setup(move |app| {
            start_update_worker(app.handle().clone(), setup_runtime.clone(), repair, None)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window
                    .state::<Arc<UpdateRuntime>>()
                    .running
                    .load(Ordering::SeqCst)
                {
                    api.prevent_close();
                }
            }
        })
        .run(installer_context_config())
        .expect("error while running Suzent updater");
}

fn start_update_worker(
    app_handle: tauri::AppHandle,
    runtime: Arc<UpdateRuntime>,
    repair: bool,
    recovery_target: Option<String>,
) -> Result<(), String> {
    if runtime.running.swap(true, Ordering::SeqCst) {
        return Err("An update is already running".to_string());
    }
    *runtime.result.lock().map_err(|error| error.to_string())? = None;
    std::thread::spawn(move || {
        let mut args = runtime.args.clone();
        if let Some(target) = recovery_target {
            // Prepend the confirmed target so a later --target cannot change it.
            args.splice(
                0..0,
                ["--target".into(), target, "--backup-conflicts".into()],
            );
        }
        let error = updater::run_inner(&args, repair).err();
        let result = UpdateResult {
            code: if error.is_some() { 1 } else { 0 },
            error,
        };
        if let Ok(mut stored) = runtime.result.lock() {
            *stored = Some(result.clone());
        }
        runtime.running.store(false, Ordering::SeqCst);
        let _ = app_handle.emit("updater-finished", result);
    });
    Ok(())
}

impl InstallConfig {
    fn from_env_and_args(args: &[String]) -> Self {
        let dir = flag_value(args, "--dir")
            .map(PathBuf::from)
            .or_else(|| {
                env::var("SUZENT_DIR")
                    .ok()
                    .filter(|value| !value.trim().is_empty())
                    .map(PathBuf::from)
            })
            .unwrap_or_else(default_install_dir);
        let configured_branch = flag_value(args, "--branch").or_else(|| {
            env::var("SUZENT_BRANCH")
                .ok()
                .filter(|value| !value.trim().is_empty())
        });
        let branch_explicit = configured_branch.is_some();
        let branch = configured_branch.unwrap_or_else(|| DEFAULT_BRANCH.to_string());
        let skip_playwright = has_flag(args, "--skip-playwright")
            || env::var("SUZENT_SKIP_PLAYWRIGHT")
                .map(|value| value == "1" || value.eq_ignore_ascii_case("true"))
                .unwrap_or(false);
        let china_mirror = has_flag(args, "--china-mirror")
            || env::var("SUZENT_CHINA_MIRROR")
                .map(|value| truthy_env(&value))
                .unwrap_or(false);
        let repo_url_env = env::var("SUZENT_REPO_URL")
            .ok()
            .filter(|value| !value.trim().is_empty());
        let repo_url_override = repo_url_env.is_some();
        let repo_url = repo_url_env.unwrap_or_else(|| REPO_URL.to_string());
        let uv_install_url = env::var("SUZENT_UV_INSTALL_URL")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .unwrap_or_else(|| {
                if cfg!(windows) {
                    UV_INSTALL_PS1_URL.to_string()
                } else {
                    UV_INSTALL_SH_URL.to_string()
                }
            });
        let release_base_url_env = env::var("SUZENT_RELEASE_BASE_URL")
            .ok()
            .filter(|value| !value.trim().is_empty());
        let release_base_url_override = release_base_url_env.is_some();
        let release_base_url = release_base_url_env
            .map(|value| value.trim_end_matches('/').to_string())
            .unwrap_or_else(|| RELEASE_BASE_URL.to_string());
        let release_tag_override = env::var("SUZENT_RELEASE_TAG")
            .ok()
            .filter(|value| !value.trim().is_empty());

        Self {
            dir,
            branch,
            branch_explicit,
            skip_playwright,
            china_mirror,
            repo_url,
            repo_url_override,
            uv_install_url,
            release_base_url,
            release_base_url_override,
            release_tag_override,
            json: has_flag(args, "--json"),
            non_interactive: has_flag(args, "--non-interactive")
                || has_flag(args, "--json")
                || has_flag(args, "--stage"),
        }
    }
}

fn stages(config: &InstallConfig) -> Vec<InstallStage> {
    vec![
        InstallStage {
            name: "git",
            title: "Installing Git",
            category: "prereqs",
            needs_user_input: true,
            worker: stage_git,
        },
        InstallStage {
            name: "uv",
            title: "Installing uv package manager",
            category: "prereqs",
            needs_user_input: false,
            worker: stage_uv,
        },
        InstallStage {
            name: "python",
            title: "Verifying Python 3.12",
            category: "prereqs",
            needs_user_input: false,
            worker: stage_python,
        },
        InstallStage {
            name: "repository",
            title: "Cloning Suzent repository",
            category: "install",
            needs_user_input: false,
            worker: stage_repository,
        },
        InstallStage {
            name: "env",
            title: "Writing environment template",
            category: "install",
            needs_user_input: false,
            worker: stage_env,
        },
        InstallStage {
            name: "dependencies",
            title: "Installing Python dependencies",
            category: "install",
            needs_user_input: false,
            worker: stage_dependencies,
        },
        InstallStage {
            name: "ui",
            title: if config.branch_explicit {
                "Building desktop UI from source"
            } else {
                "Downloading desktop UI binary"
            },
            category: "install",
            needs_user_input: false,
            worker: stage_ui,
        },
        InstallStage {
            name: "updater",
            title: "Installing standalone updater",
            category: "install",
            needs_user_input: false,
            worker: stage_updater,
        },
        InstallStage {
            name: "playwright",
            title: "Installing Playwright Chromium",
            category: "install",
            needs_user_input: false,
            worker: stage_playwright,
        },
        InstallStage {
            name: "shortcuts",
            title: "Creating desktop shortcuts",
            category: "finalize",
            needs_user_input: false,
            worker: stage_shortcuts,
        },
        InstallStage {
            name: "shim",
            title: "Writing CLI shim",
            category: "finalize",
            needs_user_input: false,
            worker: stage_shim,
        },
    ]
}

fn manifest(config: &InstallConfig) -> ManifestPayload {
    ManifestPayload {
        protocol_version: PROTOCOL_VERSION,
        stages: stages(config)
            .into_iter()
            .map(|stage| ManifestStage {
                name: stage.name,
                title: stage.title,
                category: stage.category,
                needs_user_input: stage.needs_user_input,
            })
            .collect(),
    }
}

fn run_stage_command(config: &InstallConfig, stage_name: &str) {
    let Some(stage) = stages(config)
        .into_iter()
        .find(|stage| stage.name == stage_name)
    else {
        print_json(&StageResult {
            stage: stage_name.to_string(),
            ok: false,
            skipped: false,
            reason: Some(format!(
                "unknown stage: {stage_name}. Run --manifest to list valid stages."
            )),
            duration_ms: 0,
            logs: Vec::new(),
        });
        std::process::exit(2);
    };

    let result = run_stage(config, stage);
    print_json(&result);
    std::process::exit(if result.ok { 0 } else { 1 });
}

fn run_stage(config: &InstallConfig, stage: InstallStage) -> StageResult {
    let quiet = config.json || config.non_interactive;
    if !quiet {
        println!("-> {}", stage.title);
    }

    let started = Instant::now();
    clear_stage_logs();
    let outcome = if (stage.name == "git" && inspect_destination_path(&config.dir).kind != "new")
        || (stage.name == "repository" && config.dir.join(".git").exists())
    {
        StageOutcome::fail("Existing or unrecognized directories cannot use first-time installation. Use the existing installation's update/repair flow, or review development update instructions. No branch was changed.")
    } else {
        (stage.worker)(config)
    };

    StageResult {
        stage: stage.name.to_string(),
        ok: outcome.ok,
        skipped: outcome.skipped,
        reason: outcome.reason,
        duration_ms: started.elapsed().as_millis(),
        logs: take_stage_logs(),
    }
}

fn stage_git(_config: &InstallConfig) -> StageOutcome {
    if let Some(path) = find_git_after_install() {
        print_human(format!("[OK] Git found at {}", path.display()));
        return StageOutcome::ok();
    }

    if cfg!(windows) && find_executable("winget").is_some() {
        print_human("Installing Git via winget...");
        let mut command = Command::new("winget");
        command
            .args([
                "install",
                "--id",
                "Git.Git",
                "--source",
                "winget",
                "--accept-package-agreements",
                "--accept-source-agreements",
                "--silent",
            ])
            .stdout(child_stdio())
            .stderr(child_stdio());
        hide_command_window(&mut command);
        let installed = run_command(&mut command);

        if installed && find_git_after_install().is_some() {
            print_human("[OK] Git installed");
            return StageOutcome::ok();
        }
    }

    if cfg!(target_os = "macos") {
        return git_install::install_macos();
    }
    if cfg!(target_os = "linux") {
        // GUI stage requests suppress terminal prompts but can use PolicyKit dialogs.
        let gui = git_install::allows_gui_authorization(&env::args().skip(1).collect::<Vec<_>>());
        return git_install::install_linux(_config.non_interactive && !gui);
    }
    StageOutcome::fail("Git is required. Install it from https://git-scm.com/downloads and retry.")
}

fn stage_uv(_config: &InstallConfig) -> StageOutcome {
    if let Some(path) = find_executable("uv") {
        print_human(format!("[OK] uv found at {}", path.display()));
        return StageOutcome::ok();
    }

    print_human("Installing uv...");
    let status = if cfg!(windows) {
        let mut command = Command::new("powershell");
        command
            .args([
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                &format!(
                    "irm '{}' | iex",
                    escape_powershell_single_quoted(&_config.uv_install_url)
                ),
            ])
            .stdout(child_stdio())
            .stderr(child_stdio());
        configure_mirror_env(&mut command, _config);
        hide_command_window(&mut command);
        run_command(&mut command)
    } else {
        let mut command = Command::new("sh");
        command
            .args([
                "-c",
                &format!(
                    "curl -LsSf '{}' | sh",
                    shell_single_quote(&_config.uv_install_url)
                ),
            ])
            .stdout(child_stdio())
            .stderr(child_stdio());
        configure_mirror_env(&mut command, _config);
        run_command(&mut command)
    };

    if status && find_uv_after_install().is_some() {
        print_human("[OK] uv installed");
        return StageOutcome::ok();
    }

    StageOutcome::fail("uv is required. Install it from https://docs.astral.sh/uv/ and retry.")
}

fn stage_python(config: &InstallConfig) -> StageOutcome {
    let Some(uv) = find_uv_after_install() else {
        return StageOutcome::fail("uv is not installed; run the uv stage first.");
    };

    let mut find_command = Command::new(&uv);
    find_command
        .args(["python", "find", TARGET_PYTHON_VERSION])
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    configure_mirror_env(&mut find_command, config);
    hide_command_window(&mut find_command);
    log_command_start(&find_command);
    let found = find_command.output();
    log_command_output(&found);

    if matches!(found, Ok(out) if out.status.success()) {
        print_human(format!(
            "[OK] Python {TARGET_PYTHON_VERSION}+ is available to uv"
        ));
        return StageOutcome::ok();
    }

    print_human(format!(
        "Python {TARGET_PYTHON_VERSION} not found through uv. Installing..."
    ));
    let mut install_command = Command::new(&uv);
    install_command
        .args(["python", "install", TARGET_PYTHON_VERSION])
        .stdout(child_stdio())
        .stderr(child_stdio());
    configure_mirror_env(&mut install_command, config);
    let status = run_command(&mut install_command);

    if status {
        print_human(format!("[OK] Python {TARGET_PYTHON_VERSION} installed"));
        StageOutcome::ok()
    } else {
        StageOutcome::fail("Python 3.12 is required and uv could not install it.")
    }
}

fn is_release_tag(value: &str) -> bool {
    let Some(version) = value.strip_prefix('v') else {
        return false;
    };
    let parts: Vec<&str> = version.split('.').collect();
    parts.len() == 3
        && parts
            .iter()
            .all(|part| !part.is_empty() && part.chars().all(|ch| ch.is_ascii_digit()))
}

fn resolve_release_tag(config: &InstallConfig) -> Result<String, String> {
    let tag = if let Some(tag) = &config.release_tag_override {
        tag.trim().to_string()
    } else {
        reqwest::blocking::Client::builder()
            .user_agent("suzent-installer")
            .build()
            .map_err(|error| format!("Failed to create release client: {error}"))?
            .get(LATEST_RELEASE_API)
            .send()
            .and_then(|response| response.error_for_status())
            .map_err(|error| format!("Failed to resolve latest stable release: {error}"))?
            .json::<ReleaseResponse>()
            .map_err(|error| format!("Invalid latest release response: {error}"))?
            .tag_name
    };
    if !is_release_tag(&tag) {
        return Err(format!("Invalid stable release tag: {tag}"));
    }
    Ok(tag)
}

fn write_install_release_state(
    config: &InstallConfig,
    release_tag: Option<&str>,
) -> io::Result<()> {
    let state_dir = config.dir.join(".suzent");
    fs::create_dir_all(&state_dir)?;
    fs::write(
        state_dir.join("update-channel"),
        if release_tag.is_some() {
            "stable"
        } else {
            "dev"
        },
    )?;
    let release_file = state_dir.join("release-tag");
    if let Some(tag) = release_tag {
        fs::write(release_file, tag)?;
    } else if release_file.exists() {
        fs::remove_file(release_file)?;
    }
    Ok(())
}

fn read_install_release_tag(config: &InstallConfig) -> Option<String> {
    fs::read_to_string(config.dir.join(".suzent").join("release-tag"))
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| is_release_tag(value))
}

fn stage_repository(config: &InstallConfig) -> StageOutcome {
    let Some(git) = find_git_after_install() else {
        return StageOutcome::fail("Git is not installed; run the git stage first.");
    };

    let release_tag = if config.branch_explicit {
        None
    } else {
        match resolve_release_tag(config) {
            Ok(tag) => Some(tag),
            Err(error) => return StageOutcome::fail(error),
        }
    };
    let target_ref = release_tag.as_deref().unwrap_or(&config.branch);

    let repository_ready = if config.dir.join(".git").exists() {
        print_human("Existing Suzent repository found. Updating...");
        let update_remote = if config.repo_url_override {
            config.repo_url.as_str()
        } else {
            "origin"
        };
        if let Some(tag) = &release_tag {
            if !run_command(
                Command::new(&git)
                    .args(["fetch", update_remote, "tag", tag])
                    .current_dir(&config.dir),
            ) || !run_command(
                Command::new(&git)
                    .args(["checkout", "--detach", tag])
                    .current_dir(&config.dir),
            ) {
                return StageOutcome::fail("Failed to check out stable release tag.");
            }
        } else {
            if !run_command(
                Command::new(&git)
                    .args(["fetch", update_remote, target_ref])
                    .current_dir(&config.dir),
            ) {
                return StageOutcome::fail("Failed to fetch repository updates.");
            }
            let mut checkout_command = Command::new(&git);
            checkout_command
                .args(["checkout", target_ref])
                .current_dir(&config.dir)
                .stdout(child_stdio())
                .stderr(child_stdio());
            let _ = run_command(&mut checkout_command);
            if !run_command(
                Command::new(&git)
                    .args(["pull", update_remote, target_ref])
                    .current_dir(&config.dir),
            ) {
                return StageOutcome::fail("Failed to update repository.");
            }
        }
        true
    } else if config.dir.exists() && !is_empty_dir(&config.dir) {
        return StageOutcome::fail(format!(
            "{} already exists but is not a Git repository. Set SUZENT_DIR or --dir to another path.",
            config.dir.display()
        ));
    } else {
        if let Some(parent) = config.dir.parent() {
            if let Err(error) = fs::create_dir_all(parent) {
                return StageOutcome::fail(format!(
                    "Failed to create install parent directory: {error}"
                ));
            }
        }
        run_command(Command::new(&git).args([
            "clone",
            "--branch",
            target_ref,
            &config.repo_url,
            config.dir.to_string_lossy().as_ref(),
        ]))
    };

    if !repository_ready {
        return StageOutcome::fail("Failed to clone Suzent repository.");
    }
    if let Err(error) = write_install_release_state(config, release_tag.as_deref()) {
        return StageOutcome::fail(format!("Failed to record install channel: {error}"));
    }
    StageOutcome::ok()
}

fn stage_env(config: &InstallConfig) -> StageOutcome {
    let env_file = config.dir.join(".env");
    if env_file.exists() {
        print_human("[OK] .env already exists");
        return StageOutcome::ok();
    }

    let example = config.dir.join(".env.example");
    if !example.exists() {
        return StageOutcome::skipped(".env.example not found; skipping .env creation.");
    }

    match fs::copy(&example, &env_file) {
        Ok(_) => {
            print_human("[OK] Created .env from .env.example");
            StageOutcome::ok()
        }
        Err(error) => StageOutcome::fail(format!("Failed to create .env: {error}")),
    }
}

fn stage_dependencies(config: &InstallConfig) -> StageOutcome {
    let Some(uv) = find_uv_after_install() else {
        return StageOutcome::fail("uv is not installed; run the uv stage first.");
    };

    let mut command = Command::new(&uv);
    command
        .args(["sync", "--frozen", "--extra", "social"])
        .current_dir(&config.dir);
    configure_mirror_env(&mut command, config);

    if run_command(&mut command) {
        StageOutcome::ok()
    } else {
        StageOutcome::fail("uv sync --frozen --extra social failed.")
    }
}

fn stage_ui(config: &InstallConfig) -> StageOutcome {
    let release_tag = read_install_release_tag(config);
    if release_tag.is_none() {
        return stage_source_ui(config);
    }
    let asset = ui_asset_name();
    let release_base_url = if let Some(tag) = &release_tag {
        if config.release_base_url_override {
            config.release_base_url.clone()
        } else {
            format!("https://github.com/cyzus/suzent/releases/download/{tag}")
        }
    } else {
        config.release_base_url.clone()
    };
    let url = format!("{release_base_url}/{asset}");
    let bin_dir = config.dir.join("bin");
    let dest = bin_dir.join(ui_binary_name());
    let tmp = dest.with_extension("tmp");

    if let Err(error) = fs::create_dir_all(&bin_dir) {
        return StageOutcome::fail(format!("Failed to create bin directory: {error}"));
    }

    let client = reqwest::blocking::Client::new();
    let response = client
        .get(&url)
        .send()
        .and_then(|resp| resp.error_for_status());
    let bytes = match response.and_then(|resp| resp.bytes()) {
        Ok(bytes) => bytes,
        Err(error) => {
            return StageOutcome::skipped(format!(
                "UI binary download failed: {error}. Download later from {url}."
            ));
        }
    };

    if let Err(error) = fs::write(&tmp, &bytes) {
        return StageOutcome::fail(format!("Failed to write temporary UI binary: {error}"));
    }
    if let Err(error) = fs::rename(&tmp, &dest) {
        let _ = fs::remove_file(&tmp);
        return StageOutcome::fail(format!("Failed to install UI binary: {error}"));
    }

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if let Ok(metadata) = fs::metadata(&dest) {
            let mut permissions = metadata.permissions();
            permissions.set_mode(0o755);
            let _ = fs::set_permissions(&dest, permissions);
        }
    }

    let ui_version = release_tag.as_deref().unwrap_or("latest");
    let _ = fs::write(bin_dir.join("version.txt"), ui_version);
    print_human(format!("[OK] UI binary ready at {}", dest.display()));
    StageOutcome::ok()
}

fn stage_source_ui(config: &InstallConfig) -> StageOutcome {
    if find_executable("cargo").is_none() || find_executable("node").is_none() {
        return StageOutcome::fail(
            "Branch installations require Node.js, npm, Rust and the platform build tools. Install them and retry; a release desktop cannot be paired with development source.",
        );
    }
    build_source_ui(config, run_command)
}

fn build_source_ui(
    config: &InstallConfig,
    mut run: impl FnMut(&mut Command) -> bool,
) -> StageOutcome {
    for (directory, args) in [
        ("frontend", vec!["ci"]),
        ("src-tauri", vec!["ci"]),
        ("src-tauri", vec!["run", "build:dist", "--", "--no-bundle"]),
    ] {
        let mut command = if cfg!(windows) {
            let mut command = Command::new("cmd");
            command.args(["/d", "/c", "npm"]);
            command
        } else {
            Command::new("npm")
        };
        command.args(args).current_dir(config.dir.join(directory));
        // A global Cargo target override must not redirect the artifact we install.
        command.env("CARGO_TARGET_DIR", config.dir.join("src-tauri/target"));
        configure_mirror_env(&mut command, config);
        if !run(&mut command) {
            return StageOutcome::fail("Failed to build the desktop from this checkout. Check Node.js/Rust build dependencies and retry; no release desktop was downloaded.");
        }
    }
    let binary = config
        .dir
        .join("src-tauri/target/release")
        .join(if cfg!(windows) {
            "suzent.exe"
        } else {
            "suzent"
        });
    let bin = config.dir.join("bin");
    let destination = bin.join(ui_binary_name());
    let staged = destination.with_extension("source.tmp");
    if let Err(error) = fs::create_dir_all(&bin)
        .and_then(|()| fs::copy(&binary, &staged).map(|_| ()))
        .and_then(|()| fs::rename(&staged, &destination))
    {
        let _ = fs::remove_file(&staged);
        return StageOutcome::fail(format!(
            "Failed to install the source-built desktop: {error}"
        ));
    }
    if let Err(error) = fs::remove_file(bin.join("version.txt")) {
        if error.kind() != io::ErrorKind::NotFound {
            return StageOutcome::fail(format!(
                "Failed to clear stale release desktop metadata: {error}"
            ));
        }
    }
    StageOutcome::ok()
}

#[cfg(windows)]
fn show_update_console() {
    unsafe {
        windows_sys::Win32::System::Console::AllocConsole();
    }
}

#[cfg(not(windows))]
fn show_update_console() {}

fn stage_updater(_config: &InstallConfig) -> StageOutcome {
    let current = match env::current_exe() {
        Ok(path) => path,
        Err(error) => {
            return StageOutcome::fail(format!("Failed to locate installer executable: {error}"));
        }
    };
    let updater_dir = dirs_home().join(".suzent").join("updater");
    let destination = updater_dir.join(if cfg!(windows) {
        "suzent-installer.exe"
    } else {
        "suzent-installer"
    });
    if current == destination {
        return StageOutcome::ok();
    }
    if let Err(error) = fs::create_dir_all(&updater_dir) {
        return StageOutcome::fail(format!("Failed to create updater directory: {error}"));
    }
    let temporary = destination.with_extension("new");
    if let Err(error) = fs::copy(&current, &temporary) {
        return StageOutcome::fail(format!("Failed to stage standalone updater: {error}"));
    }
    if destination.exists() {
        if let Err(error) = fs::remove_file(&destination) {
            let _ = fs::remove_file(&temporary);
            return StageOutcome::fail(format!("Failed to replace standalone updater: {error}"));
        }
    }
    if let Err(error) = fs::rename(&temporary, &destination) {
        let _ = fs::remove_file(&temporary);
        return StageOutcome::fail(format!("Failed to install standalone updater: {error}"));
    }
    let tag = format!("v{}", env!("CARGO_PKG_VERSION"));
    if let Err(error) = fs::write(updater_dir.join("version.txt"), tag) {
        return StageOutcome::fail(format!("Failed to record updater version: {error}"));
    }
    print_human(format!(
        "[OK] Standalone updater ready at {}",
        destination.display()
    ));
    StageOutcome::ok()
}

fn stage_playwright(config: &InstallConfig) -> StageOutcome {
    if config.skip_playwright {
        return StageOutcome::skipped("Playwright Chromium skipped by request.");
    }

    let mut command = if let Some(playwright) = playwright_executable(&config.dir) {
        let mut command = Command::new(playwright);
        command
            .args(["install", "chromium"])
            .current_dir(&config.dir);
        command
    } else {
        let Some(uv) = find_uv_after_install() else {
            return StageOutcome::fail("uv is not installed; run the uv stage first.");
        };
        let mut command = Command::new(&uv);
        command
            .args(["run", "playwright", "install", "chromium"])
            .current_dir(&config.dir);
        command
    };
    configure_mirror_env(&mut command, config);

    if run_command(&mut command) {
        StageOutcome::ok()
    } else {
        StageOutcome::skipped(
            "Playwright Chromium install failed; browser automation needs repair before web tasks work.",
        )
    }
}

/// Delegates to `suzent.cli.shortcuts`, the single implementation the updater
/// and the shell setup scripts also use, so an entry created here is repaired
/// by every later update no matter which path runs it.
fn stage_shortcuts(config: &InstallConfig) -> StageOutcome {
    let ui = config.dir.join("bin").join(ui_binary_name());
    if !ui.exists() {
        return StageOutcome::skipped(format!(
            "Desktop UI binary not found at {}; shortcut creation skipped.",
            ui.display()
        ));
    }

    let python = workspace_python(&config.dir);
    if !python.exists() {
        return StageOutcome::skipped(format!(
            "Python environment not found at {}; run 'suzent shortcuts' once install finishes.",
            python.display()
        ));
    }

    let mut command = Command::new(&python);
    command
        .args(["-m", "suzent.cli", "shortcuts"])
        .current_dir(&config.dir);

    if run_command(&mut command) {
        print_human("[OK] Launcher shortcuts created");
        StageOutcome::ok()
    } else {
        StageOutcome::skipped(
            "Shortcut creation failed; run 'suzent shortcuts' to retry. Install can continue.",
        )
    }
}

fn workspace_python(workspace: &Path) -> PathBuf {
    if cfg!(windows) {
        workspace.join(".venv").join("Scripts").join("python.exe")
    } else {
        workspace.join(".venv").join("bin").join("python")
    }
}

fn stage_shim(config: &InstallConfig) -> StageOutcome {
    if !cfg!(windows) {
        if let Err(error) = write_bootstrap_marker(config) {
            return StageOutcome::fail(format!("Failed to write bootstrap marker: {error}"));
        }
        if let Err(error) = write_install_dir_marker(&config.dir) {
            return StageOutcome::fail(format!("Failed to save install directory: {error}"));
        }
        return StageOutcome::skipped("CLI shim writing is currently Windows-only.");
    }

    let bin_dir = dirs_home().join(".local").join("bin");
    if let Err(error) = fs::create_dir_all(&bin_dir) {
        return StageOutcome::fail(format!("Failed to create shim directory: {error}"));
    }

    let shim = bin_dir.join("suzent.cmd");
    let content = format!(
        "@echo off\r\ncd /d \"{}\"\r\nuv run suzent %*\r\n",
        config.dir.display()
    );

    if let Err(error) = fs::write(&shim, content) {
        return StageOutcome::fail(format!("Failed to write CLI shim: {error}"));
    }

    if let Err(error) = write_bootstrap_marker(config) {
        return StageOutcome::fail(format!("Failed to write bootstrap marker: {error}"));
    }
    if let Err(error) = write_install_dir_marker(&config.dir) {
        return StageOutcome::fail(format!("Failed to save install directory: {error}"));
    }

    print_human(format!("[OK] CLI shim written to {}", shim.display()));
    StageOutcome::ok()
}

fn write_bootstrap_marker(config: &InstallConfig) -> io::Result<()> {
    fs::write(
        config.dir.join(".suzent-bootstrap-complete"),
        format!("protocol={PROTOCOL_VERSION}\n"),
    )
}

fn escape_powershell_single_quoted(value: &str) -> String {
    value.replace('\'', "''")
}

fn shell_single_quote(value: &str) -> String {
    value.replace('\'', "'\\''")
}

fn truthy_env(value: &str) -> bool {
    matches!(
        value.trim().to_ascii_lowercase().as_str(),
        "1" | "true" | "yes" | "cn"
    )
}

fn configure_mirror_env(command: &mut Command, config: &InstallConfig) {
    if !config.china_mirror {
        return;
    }

    env_if_missing(
        command,
        "UV_DEFAULT_INDEX",
        "https://pypi.tuna.tsinghua.edu.cn/simple",
    );
    env_if_missing(
        command,
        "NPM_CONFIG_REGISTRY",
        "https://registry.npmmirror.com",
    );
    env_if_missing(
        command,
        "PLAYWRIGHT_DOWNLOAD_HOST",
        "https://npmmirror.com/mirrors/playwright",
    );
    env_if_missing(
        command,
        "NVM_NODEJS_ORG_MIRROR",
        "https://npmmirror.com/mirrors/node",
    );
    env_if_missing(
        command,
        "RUSTUP_DIST_SERVER",
        "https://mirrors.tuna.tsinghua.edu.cn/rustup",
    );
    env_if_missing(
        command,
        "RUSTUP_UPDATE_ROOT",
        "https://mirrors.tuna.tsinghua.edu.cn/rustup/rustup",
    );
}

fn env_if_missing(command: &mut Command, key: &str, value: &str) {
    if env::var(key)
        .ok()
        .filter(|existing| !existing.trim().is_empty())
        .is_none()
    {
        command.env(key, value);
    }
}

fn is_empty_dir(path: &Path) -> bool {
    path.is_dir()
        && fs::read_dir(path)
            .map(|mut entries| entries.next().is_none())
            .unwrap_or(false)
}

impl StageOutcome {
    fn ok() -> Self {
        Self {
            ok: true,
            skipped: false,
            reason: None,
        }
    }

    fn fail(reason: impl Into<String>) -> Self {
        Self {
            ok: false,
            skipped: false,
            reason: Some(reason.into()),
        }
    }

    fn skipped(reason: impl Into<String>) -> Self {
        let reason = reason.into();
        print_human(format!("[!] {reason}"));
        Self {
            ok: true,
            skipped: true,
            reason: Some(reason),
        }
    }
}

fn write_banner(config: &InstallConfig) {
    println!("===================================================");
    println!("          SUZENT Desktop Setup Wizard              ");
    println!("===================================================");
    println!();
    println!("Install directory: {}", config.dir.display());
    println!("Branch: {}", config.branch);
    if config.china_mirror {
        println!("China mirror mode: enabled");
    }
    println!();
}

fn print_preview(config: &InstallConfig) {
    println!("Preview mode: no changes will be made.");
    println!();
    let plan = stages(config);
    let count = plan.len();
    for (idx, stage) in plan.into_iter().enumerate() {
        println!("Step {}/{}: {}", idx + 1, count, stage.title);
        match stage.name {
            "repository" => {
                println!("  Clone or update {}", config.repo_url);
                println!("  Target: {}", config.dir.display());
            }
            "dependencies" => println!("  uv sync --frozen --extra social"),
            "ui" if config.branch_explicit => {
                println!("  Branch: {}", config.branch);
                println!("  npm ci (frontend and src-tauri)");
                println!("  npm run build:dist -- --no-bundle (src-tauri)");
                println!("  Requires Node.js/npm, Rust and platform build tools; no release UI download.");
            }
            "ui" => println!("  {}", ui_asset_name()),
            "playwright" => {
                if config.skip_playwright {
                    println!("  skipped by request");
                } else {
                    println!("  uv run playwright install chromium");
                }
            }
            "shortcuts" => println!("  Create launcher shortcuts for {}", ui_binary_name()),
            _ => {}
        }
    }
    println!();
    println!("Run without --preview to perform the installation.");
    println!("Run --manifest or --stage <name> --json for GUI/automation mode.");
}

fn print_completion(config: &InstallConfig) {
    println!();
    println!("===================================================");
    println!("    SUZENT installation finished");
    println!("===================================================");
    println!("Workspace: {}", config.dir.display());
    println!(
        "Launch: {}",
        config.dir.join("bin").join(ui_binary_name()).display()
    );
}

fn run_command(command: &mut Command) -> bool {
    hide_command_window(command);
    log_command_start(command);

    if machine_mode() {
        let result = command
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .output();
        let success = matches!(&result, Ok(output) if output.status.success());
        log_command_output(&result);
        return success;
    }

    matches!(
        command
            .stdout(child_stdio())
            .stderr(child_stdio())
            .status(),
        Ok(status) if status.success()
    )
}

fn find_executable(name: &str) -> Option<PathBuf> {
    let exe_name = if cfg!(windows) && !name.ends_with(".exe") {
        format!("{name}.exe")
    } else {
        name.to_string()
    };

    let path_var = env::var("PATH").unwrap_or_default();
    for dir in env::split_paths(&path_var) {
        let candidate = dir.join(&exe_name);
        if candidate.exists() {
            return Some(candidate);
        }
    }

    let lookup = if cfg!(windows) { "where" } else { "which" };
    let mut command = Command::new(lookup);
    command.arg(name);
    hide_command_window(&mut command);
    let output = command.output().ok()?;
    if !output.status.success() {
        return None;
    }
    let path = String::from_utf8_lossy(&output.stdout)
        .lines()
        .next()
        .unwrap_or("")
        .trim()
        .to_string();
    if path.is_empty() {
        None
    } else {
        Some(PathBuf::from(path))
    }
}

fn find_git_after_install() -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = find_executable("git").into_iter().collect();
    if cfg!(windows) {
        candidates.extend(
            [
                r"C:\Program Files\Git\cmd\git.exe",
                r"C:\Program Files\Git\bin\git.exe",
                r"C:\Program Files (x86)\Git\cmd\git.exe",
            ]
            .map(PathBuf::from),
        );
    } else if cfg!(target_os = "macos") {
        candidates.extend(
            [
                "/opt/homebrew/bin/git",
                "/usr/local/bin/git",
                "/usr/bin/git",
            ]
            .map(PathBuf::from),
        );
    }
    candidates
        .into_iter()
        .find(|path| git_install::usable_git(path))
}

fn find_uv_after_install() -> Option<PathBuf> {
    find_executable("uv").or_else(|| {
        let home = dirs_home();
        let candidates = if cfg!(windows) {
            vec![
                home.join(".cargo").join("bin").join("uv.exe"),
                home.join(".local").join("bin").join("uv.exe"),
            ]
        } else {
            vec![
                home.join(".cargo").join("bin").join("uv"),
                home.join(".local").join("bin").join("uv"),
            ]
        };
        candidates.into_iter().find(|path| path.exists())
    })
}

fn playwright_executable(workspace: &Path) -> Option<PathBuf> {
    let path = if cfg!(windows) {
        workspace
            .join(".venv")
            .join("Scripts")
            .join("playwright.exe")
    } else {
        workspace.join(".venv").join("bin").join("playwright")
    };
    path.exists().then_some(path)
}

fn default_install_dir() -> PathBuf {
    saved_install_dir(&install_dir_marker_path()).unwrap_or_else(|| dirs_home().join("suzent"))
}

fn install_dir_marker_path() -> PathBuf {
    env::var("SUZENT_DATA_DIR")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| dirs_home().join(".suzent"))
        .join("install-dir.txt")
}

fn saved_install_dir(marker: &Path) -> Option<PathBuf> {
    let path = PathBuf::from(fs::read_to_string(marker).ok()?.trim());
    // A missing drive or broken environment needs repair, not a second install.
    path.is_absolute().then_some(path)
}

fn write_install_dir_marker(dir: &Path) -> io::Result<()> {
    let marker = install_dir_marker_path();
    fs::create_dir_all(marker.parent().expect("install marker parent"))?;
    fs::write(marker, fs::canonicalize(dir)?.display().to_string())
}

fn dirs_home() -> PathBuf {
    let primary = if cfg!(windows) { "USERPROFILE" } else { "HOME" };
    let secondary = if cfg!(windows) { "HOME" } else { "USERPROFILE" };
    env::var(primary)
        .or_else(|_| env::var(secondary))
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."))
}

fn ui_asset_name() -> &'static str {
    if cfg!(windows) {
        "suzent-windows-x86_64.exe"
    } else if cfg!(all(target_os = "macos", target_arch = "aarch64")) {
        "suzent-macos-aarch64"
    } else if cfg!(all(target_os = "macos", target_arch = "x86_64")) {
        "suzent-macos-x86_64"
    } else {
        "suzent-linux-x86_64"
    }
}

fn ui_binary_name() -> &'static str {
    if cfg!(windows) {
        "suzent-ui.exe"
    } else {
        "suzent-ui"
    }
}

fn has_flag(args: &[String], flag: &str) -> bool {
    args.iter().any(|arg| arg == flag)
}

fn flag_value(args: &[String], flag: &str) -> Option<String> {
    args.windows(2)
        .find(|pair| pair[0] == flag)
        .map(|pair| pair[1].clone())
}

fn print_json<T: Serialize>(value: &T) {
    match serde_json::to_string(value) {
        Ok(json) => println!("{json}"),
        Err(error) => {
            eprintln!("Failed to serialize JSON: {error}");
            std::process::exit(1);
        }
    }
}

fn print_human(message: impl AsRef<str>) {
    if !machine_mode() {
        println!("{}", message.as_ref());
    } else {
        log_detail(message.as_ref());
    }
}

fn clear_stage_logs() {
    STAGE_LOGS.with(|logs| logs.borrow_mut().clear());
}

fn take_stage_logs() -> Vec<String> {
    STAGE_LOGS.with(|logs| std::mem::take(&mut *logs.borrow_mut()))
}

fn log_detail(message: impl AsRef<str>) {
    let message = message.as_ref().trim();
    if message.is_empty() {
        return;
    }
    STAGE_LOGS.with(|logs| logs.borrow_mut().push(message.to_string()));
}

fn log_command_start(command: &Command) {
    log_detail(format!("$ {}", command_display(command)));
}

fn log_command_output(result: &io::Result<std::process::Output>) {
    match result {
        Ok(output) => {
            log_detail(format!("exit code: {}", output.status.code().unwrap_or(-1)));
            log_stream("stdout", &output.stdout);
            log_stream("stderr", &output.stderr);
        }
        Err(error) => log_detail(format!("failed to start command: {error}")),
    }
}

fn log_stream(name: &str, bytes: &[u8]) {
    let text = String::from_utf8_lossy(bytes);
    for line in text
        .lines()
        .map(str::trim_end)
        .filter(|line| !line.is_empty())
    {
        log_detail(format!("{name}: {line}"));
    }
}

fn command_display(command: &Command) -> String {
    let mut parts = vec![command.get_program().to_string_lossy().to_string()];
    parts.extend(
        command
            .get_args()
            .map(|arg| arg.to_string_lossy().to_string()),
    );
    parts.join(" ")
}

fn machine_mode() -> bool {
    env::args().any(|arg| {
        arg == "--json" || arg == "--stage" || arg == "--manifest" || arg == "--protocol-version"
    })
}

fn child_stdio() -> Stdio {
    if machine_mode() {
        Stdio::null()
    } else {
        Stdio::inherit()
    }
}

#[cfg(windows)]
fn hide_command_window(command: &mut Command) {
    use std::os::windows::process::CommandExt;
    command.creation_flags(CREATE_NO_WINDOW);
}

#[cfg(not(windows))]
fn hide_command_window(_command: &mut Command) {}

fn exit_with_prompt(code: i32, non_interactive: bool) -> ! {
    if !non_interactive {
        println!();
        println!("Press Enter to exit...");
        let mut input = String::new();
        let _ = io::stdin().read_line(&mut input);
    } else {
        let _ = io::stdout().flush();
    }
    std::process::exit(code);
}

#[cfg(test)]
mod tests {
    use super::{is_release_tag, saved_install_dir, workspace_python};
    use std::fs;

    #[test]
    fn destination_detection_distinguishes_new_development_and_release_repair() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path();
        assert_eq!(super::inspect_destination_path(root).kind, "new");
        fs::write(root.join("unrelated.txt"), "keep").unwrap();
        assert_eq!(super::inspect_destination_path(root).kind, "occupied");
        let git = |args: &[&str]| {
            let mut command = std::process::Command::new("git");
            command
                .args([
                    "-c",
                    "user.name=Installer Test",
                    "-c",
                    "user.email=installer@example.invalid",
                ])
                .args(args)
                .current_dir(root);
            super::hide_command_window(&mut command);
            assert!(command.output().unwrap().status.success());
        };
        git(&["init", "-b", "development"]);
        fs::write(root.join("pyproject.toml"), "[project]\nname = 'suzent'\n").unwrap();
        fs::create_dir_all(root.join("src/suzent")).unwrap();
        git(&["add", "pyproject.toml"]);
        git(&["commit", "-m", "initial"]);
        let development = super::inspect_destination_path(root);
        assert_eq!(development.kind, "development");
        assert_eq!(development.branch.as_deref(), Some("development"));
        fs::write(root.join(".suzent-bootstrap-complete"), "ready").unwrap();
        assert_eq!(super::inspect_destination_path(root).kind, "development");
        git(&["checkout", "--detach"]);
        assert_eq!(super::inspect_destination_path(root).kind, "repair");
        let python = super::workspace_python(root);
        fs::create_dir_all(python.parent().unwrap()).unwrap();
        fs::write(python, "").unwrap();
        assert_eq!(super::inspect_destination_path(root).kind, "update");
        fs::create_dir_all(root.join(".suzent")).unwrap();
        fs::write(root.join(".suzent/update-transaction.json"), "{}").unwrap();
        assert_eq!(super::inspect_destination_path(root).kind, "repair");
        let config =
            super::InstallConfig::from_env_and_args(&["--dir".into(), root.display().to_string()]);
        let stage = super::stages(&config)
            .into_iter()
            .find(|stage| stage.name == "repository")
            .unwrap();
        assert!(!super::run_stage(&config, stage).ok);
        assert_eq!(
            fs::read_to_string(root.join("unrelated.txt")).unwrap(),
            "keep"
        );
    }

    #[test]
    fn desktop_stage_copy_matches_install_mode_in_manifest_and_execution() {
        let mut config = super::InstallConfig::from_env_and_args(&[]);
        for (development, expected) in [
            (false, "Downloading desktop UI binary"),
            (true, "Building desktop UI from source"),
        ] {
            config.branch_explicit = development;
            let stage = super::stages(&config)
                .into_iter()
                .find(|stage| stage.name == "ui")
                .unwrap();
            let manifest = super::manifest(&config);
            let published = manifest
                .stages
                .iter()
                .find(|stage| stage.name == "ui")
                .unwrap();
            assert_eq!(stage.title, expected);
            assert_eq!(published.title, expected);
        }
    }

    #[test]
    fn branch_desktop_is_built_from_selected_checkout() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path();
        let config = super::InstallConfig::from_env_and_args(&[
            "--dir".into(),
            root.display().to_string(),
            "--branch".into(),
            "feature".into(),
        ]);
        let artifact = root
            .join("src-tauri/target/release")
            .join(if cfg!(windows) {
                "suzent.exe"
            } else {
                "suzent"
            });
        fs::create_dir_all(artifact.parent().unwrap()).unwrap();
        fs::write(&artifact, b"branch desktop").unwrap();
        let installed = root.join("bin").join(super::ui_binary_name());
        fs::create_dir_all(installed.parent().unwrap()).unwrap();
        fs::write(&installed, b"old desktop").unwrap();
        let mut calls = Vec::new();
        let result = super::build_source_ui(&config, |command| {
            calls.push((
                command.get_current_dir().unwrap().to_path_buf(),
                command
                    .get_args()
                    .map(|arg| arg.to_string_lossy().to_string())
                    .collect::<Vec<_>>(),
            ));
            true
        });
        assert!(result.ok);
        assert_eq!(calls.len(), 3);
        assert_eq!(calls[0].0, root.join("frontend"));
        assert_eq!(calls[2].0, root.join("src-tauri"));
        assert!(calls[2].1.ends_with(&[
            "run".into(),
            "build:dist".into(),
            "--".into(),
            "--no-bundle".into()
        ]));
        assert_eq!(
            fs::read(root.join("bin").join(super::ui_binary_name())).unwrap(),
            b"branch desktop"
        );
    }

    #[test]
    fn failed_source_build_never_replaces_installed_desktop() {
        let temp = tempfile::tempdir().unwrap();
        let config = super::InstallConfig::from_env_and_args(&[
            "--dir".into(),
            temp.path().display().to_string(),
        ]);
        let binary = temp.path().join("bin").join(super::ui_binary_name());
        fs::create_dir_all(binary.parent().unwrap()).unwrap();
        fs::write(&binary, b"old").unwrap();
        assert!(!super::build_source_ui(&config, |_| false).ok);
        assert_eq!(fs::read(binary).unwrap(), b"old");
    }

    #[test]
    fn validates_stable_release_tags() {
        assert!(is_release_tag("v0.7.3"));
        assert!(!is_release_tag("0.7.3"));
        assert!(!is_release_tag("v0.7"));
        assert!(!is_release_tag("v0.7.3-rc1"));
    }

    #[test]
    fn preserves_custom_install_record_when_repair_is_needed() {
        let temp = tempfile::tempdir().unwrap();
        let workspace = temp.path().join("custom install");
        fs::create_dir_all(workspace_python(&workspace).parent().unwrap()).unwrap();
        fs::write(
            workspace.join("pyproject.toml"),
            "[project]\nname='suzent'\n",
        )
        .unwrap();
        fs::write(workspace.join(".suzent-bootstrap-complete"), "ready").unwrap();
        fs::write(workspace_python(&workspace), "").unwrap();
        let marker = temp.path().join("install-dir.txt");
        fs::write(&marker, workspace.display().to_string()).unwrap();
        assert_eq!(saved_install_dir(&marker), Some(workspace.clone()));

        fs::remove_file(workspace.join(".suzent-bootstrap-complete")).unwrap();
        assert_eq!(saved_install_dir(&marker), Some(workspace.clone()));
        fs::remove_file(workspace_python(&workspace)).unwrap();
        assert_eq!(saved_install_dir(&marker), Some(workspace));
        let offline = temp.path().join("offline drive");
        fs::write(&marker, offline.display().to_string()).unwrap();
        assert_eq!(saved_install_dir(&marker), Some(offline));
        for invalid in ["", "relative/install"] {
            fs::write(&marker, invalid).unwrap();
            assert_eq!(saved_install_dir(&marker), None);
        }
    }
}
