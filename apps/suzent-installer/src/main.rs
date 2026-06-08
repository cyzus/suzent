#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::cell::RefCell;
use std::env;
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::Instant;

const PROTOCOL_VERSION: u16 = 1;
const TARGET_PYTHON_VERSION: &str = "3.12";
const DEFAULT_BRANCH: &str = "main";
const REPO_URL: &str = "https://github.com/cyzus/suzent.git";

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
    skip_playwright: bool,
    json: bool,
    non_interactive: bool,
}

#[derive(Deserialize)]
struct StageRequest {
    stage: String,
    dir: String,
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

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
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
        print_json(&manifest());
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

    for stage in stages() {
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

    print_completion(&config);
    exit_with_prompt(0, config.non_interactive);
}

#[tauri::command]
fn installer_manifest() -> Result<String, String> {
    serde_json::to_string(&manifest()).map_err(|error| error.to_string())
}

#[tauri::command]
fn default_install_dir_command() -> String {
    default_install_dir().display().to_string()
}

#[tauri::command]
fn run_installer_stage(request: StageRequest) -> Result<String, String> {
    let args = vec![
        "--stage".to_string(),
        request.stage.clone(),
        "--json".to_string(),
        "--non-interactive".to_string(),
        "--dir".to_string(),
        request.dir,
    ];
    let config = InstallConfig::from_env_and_args(&args);
    let Some(stage) = stages()
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
}

fn run_tauri_app() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            installer_manifest,
            default_install_dir_command,
            run_installer_stage,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Suzent installer");
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
        let branch = flag_value(args, "--branch")
            .or_else(|| {
                env::var("SUZENT_BRANCH")
                    .ok()
                    .filter(|value| !value.trim().is_empty())
            })
            .unwrap_or_else(|| DEFAULT_BRANCH.to_string());
        let skip_playwright = has_flag(args, "--skip-playwright")
            || env::var("SUZENT_SKIP_PLAYWRIGHT")
                .map(|value| value == "1" || value.eq_ignore_ascii_case("true"))
                .unwrap_or(false);

        Self {
            dir,
            branch,
            skip_playwright,
            json: has_flag(args, "--json"),
            non_interactive: has_flag(args, "--non-interactive")
                || has_flag(args, "--json")
                || has_flag(args, "--stage"),
        }
    }
}

fn stages() -> Vec<InstallStage> {
    vec![
        InstallStage {
            name: "git",
            title: "Installing Git",
            category: "prereqs",
            needs_user_input: false,
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
            title: "Downloading desktop UI binary",
            category: "install",
            needs_user_input: false,
            worker: stage_ui,
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

fn manifest() -> ManifestPayload {
    ManifestPayload {
        protocol_version: PROTOCOL_VERSION,
        stages: stages()
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
    let Some(stage) = stages().into_iter().find(|stage| stage.name == stage_name) else {
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
    let outcome = (stage.worker)(config);

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
    if let Some(path) = find_executable("git") {
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
                "irm https://astral.sh/uv/install.ps1 | iex",
            ])
            .stdout(child_stdio())
            .stderr(child_stdio());
        hide_command_window(&mut command);
        run_command(&mut command)
    } else {
        let mut command = Command::new("sh");
        command
            .args(["-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"])
            .stdout(child_stdio())
            .stderr(child_stdio());
        run_command(&mut command)
    };

    if status && find_uv_after_install().is_some() {
        print_human("[OK] uv installed");
        return StageOutcome::ok();
    }

    StageOutcome::fail("uv is required. Install it from https://docs.astral.sh/uv/ and retry.")
}

fn stage_python(_config: &InstallConfig) -> StageOutcome {
    let Some(uv) = find_uv_after_install() else {
        return StageOutcome::fail("uv is not installed; run the uv stage first.");
    };

    let mut find_command = Command::new(&uv);
    find_command
        .args(["python", "find", TARGET_PYTHON_VERSION])
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
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
    let status = run_command(&mut install_command);

    if status {
        print_human(format!("[OK] Python {TARGET_PYTHON_VERSION} installed"));
        StageOutcome::ok()
    } else {
        StageOutcome::fail("Python 3.12 is required and uv could not install it.")
    }
}

fn stage_repository(config: &InstallConfig) -> StageOutcome {
    let Some(git) = find_git_after_install() else {
        return StageOutcome::fail("Git is not installed; run the git stage first.");
    };

    if config.dir.join(".git").exists() {
        print_human("Existing Suzent repository found. Updating...");
        if !run_command(
            Command::new(&git)
                .args(["fetch", "origin"])
                .current_dir(&config.dir),
        ) {
            return StageOutcome::fail("Failed to fetch repository updates.");
        }
        let mut checkout_command = Command::new(&git);
        checkout_command
            .args(["checkout", &config.branch])
            .current_dir(&config.dir)
            .stdout(child_stdio())
            .stderr(child_stdio());
        let _ = run_command(&mut checkout_command);
        if !run_command(
            Command::new(&git)
                .args(["pull", "origin", &config.branch])
                .current_dir(&config.dir),
        ) {
            return StageOutcome::fail("Failed to update repository.");
        }
        return StageOutcome::ok();
    }

    if config.dir.exists() && !is_empty_dir(&config.dir) {
        return StageOutcome::fail(format!(
            "{} already exists but is not a Git repository. Set SUZENT_DIR or --dir to another path.",
            config.dir.display()
        ));
    }

    if let Some(parent) = config.dir.parent() {
        if let Err(error) = fs::create_dir_all(parent) {
            return StageOutcome::fail(format!(
                "Failed to create install parent directory: {error}"
            ));
        }
    }

    if run_command(Command::new(&git).args([
        "clone",
        "--branch",
        &config.branch,
        REPO_URL,
        config.dir.to_string_lossy().as_ref(),
    ])) {
        StageOutcome::ok()
    } else {
        StageOutcome::fail("Failed to clone Suzent repository.")
    }
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

    if run_command(
        Command::new(&uv)
            .args(["sync", "--extra", "social"])
            .current_dir(&config.dir),
    ) {
        StageOutcome::ok()
    } else {
        StageOutcome::fail("uv sync --extra social failed.")
    }
}

fn stage_ui(config: &InstallConfig) -> StageOutcome {
    let asset = ui_asset_name();
    let url = format!("https://github.com/cyzus/suzent/releases/latest/download/{asset}");
    let bin_dir = config.dir.join("bin");
    let dest = bin_dir.join(ui_binary_name());
    let tmp = dest.with_extension("tmp");

    if let Err(error) = fs::create_dir_all(&bin_dir) {
        return StageOutcome::fail(format!("Failed to create bin directory: {error}"));
    }

    let response = reqwest::blocking::get(&url).and_then(|resp| resp.error_for_status());
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

    let _ = fs::write(bin_dir.join("version.txt"), "latest");
    print_human(format!("[OK] UI binary ready at {}", dest.display()));
    StageOutcome::ok()
}

fn stage_playwright(config: &InstallConfig) -> StageOutcome {
    if config.skip_playwright {
        return StageOutcome::skipped("Playwright Chromium skipped by request.");
    }

    let Some(uv) = find_uv_after_install() else {
        return StageOutcome::fail("uv is not installed; run the uv stage first.");
    };

    if run_command(
        Command::new(&uv)
            .args(["run", "playwright", "install", "chromium"])
            .current_dir(&config.dir),
    ) {
        StageOutcome::ok()
    } else {
        StageOutcome::skipped(
            "Playwright Chromium install failed; browser automation needs repair before web tasks work.",
        )
    }
}

fn stage_shortcuts(config: &InstallConfig) -> StageOutcome {
    let ui = config.dir.join("bin").join(ui_binary_name());
    if !ui.exists() {
        return StageOutcome::skipped(format!(
            "Desktop UI binary not found at {}; shortcut creation skipped.",
            ui.display()
        ));
    }

    if cfg!(windows) {
        return create_windows_shortcuts(config, &ui);
    }
    if cfg!(target_os = "linux") {
        return create_linux_shortcuts(config, &ui);
    }
    if cfg!(target_os = "macos") {
        return create_macos_shortcuts(config, &ui);
    }

    StageOutcome::skipped("Shortcut creation is not implemented for this platform yet.")
}

#[cfg(windows)]
fn create_windows_shortcuts(config: &InstallConfig, ui: &std::path::Path) -> StageOutcome {
    let desktop = dirs_home().join("Desktop").join("Suzent.lnk");
    let start_menu = env::var("APPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|_| dirs_home().join("AppData").join("Roaming"))
        .join("Microsoft")
        .join("Windows")
        .join("Start Menu")
        .join("Programs")
        .join("Suzent.lnk");

    for path in [&desktop, &start_menu] {
        if let Some(parent) = path.parent() {
            if let Err(error) = fs::create_dir_all(parent) {
                return StageOutcome::skipped(format!(
                    "Failed to create shortcut directory {}: {}",
                    parent.display(),
                    error
                ));
            }
        }

        let script = format!(
            "$w = New-Object -ComObject WScript.Shell; \
             $s = $w.CreateShortcut('{}'); \
             $s.TargetPath = '{}'; \
             $s.WorkingDirectory = '{}'; \
             $s.IconLocation = '{}'; \
             $s.Save()",
            escape_powershell_single_quoted(&path.display().to_string()),
            escape_powershell_single_quoted(&ui.display().to_string()),
            escape_powershell_single_quoted(&config.dir.display().to_string()),
            escape_powershell_single_quoted(&ui.display().to_string()),
        );

        let mut command = Command::new("powershell");
        command
            .args([
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                &script,
            ])
            .stdout(child_stdio())
            .stderr(child_stdio());
        hide_command_window(&mut command);
        let status = run_command(&mut command);

        if !status {
            return StageOutcome::skipped(format!(
                "Failed to create shortcut at {}; install can continue.",
                path.display()
            ));
        }
    }

    StageOutcome::ok()
}

#[cfg(not(windows))]
fn create_windows_shortcuts(_config: &InstallConfig, _ui: &std::path::Path) -> StageOutcome {
    StageOutcome::skipped("Windows shortcuts are not supported on this platform.")
}

#[cfg(target_os = "linux")]
fn create_linux_shortcuts(config: &InstallConfig, ui: &std::path::Path) -> StageOutcome {
    let applications_dir = dirs_home()
        .join(".local")
        .join("share")
        .join("applications");
    if let Err(error) = fs::create_dir_all(&applications_dir) {
        return StageOutcome::skipped(format!(
            "Failed to create applications directory {}: {}",
            applications_dir.display(),
            error
        ));
    }

    let desktop_file = applications_dir.join("suzent.desktop");
    let content = format!(
        "[Desktop Entry]\n\
Type=Application\n\
Name=Suzent\n\
Comment=Your personal agent\n\
Exec=\"{}\"\n\
Path={}\n\
Terminal=false\n\
Categories=Utility;Development;\n",
        ui.display(),
        config.dir.display()
    );

    if let Err(error) = fs::write(&desktop_file, content) {
        return StageOutcome::skipped(format!(
            "Failed to write Linux desktop launcher {}: {}",
            desktop_file.display(),
            error
        ));
    }

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if let Ok(metadata) = fs::metadata(&desktop_file) {
            let mut permissions = metadata.permissions();
            permissions.set_mode(0o755);
            let _ = fs::set_permissions(&desktop_file, permissions);
        }
    }

    StageOutcome::ok()
}

#[cfg(not(target_os = "linux"))]
fn create_linux_shortcuts(_config: &InstallConfig, _ui: &std::path::Path) -> StageOutcome {
    StageOutcome::skipped("Linux shortcuts are not supported on this platform.")
}

#[cfg(target_os = "macos")]
fn create_macos_shortcuts(config: &InstallConfig, ui: &Path) -> StageOutcome {
    let app_bundle = config.dir.join("Suzent.app");
    let contents_dir = app_bundle.join("Contents");
    let macos_dir = contents_dir.join("MacOS");
    let executable = macos_dir.join("Suzent");
    let plist = contents_dir.join("Info.plist");

    if let Err(error) = fs::create_dir_all(&macos_dir) {
        return StageOutcome::skipped(format!(
            "Failed to create macOS app bundle {}: {}",
            app_bundle.display(),
            error
        ));
    }

    let launcher = format!(
        "#!/bin/sh\n\
exec \"{}\" \"$@\"\n",
        ui.display()
    );
    if let Err(error) = fs::write(&executable, launcher) {
        return StageOutcome::skipped(format!(
            "Failed to write macOS launcher {}: {}",
            executable.display(),
            error
        ));
    }

    let plist_content = r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>Suzent</string>
  <key>CFBundleDisplayName</key>
  <string>Suzent</string>
  <key>CFBundleIdentifier</key>
  <string>com.suzent.app</string>
  <key>CFBundleVersion</key>
  <string>0.6.3</string>
  <key>CFBundleShortVersionString</key>
  <string>0.6.3</string>
  <key>CFBundleExecutable</key>
  <string>Suzent</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>LSMinimumSystemVersion</key>
  <string>10.13</string>
</dict>
</plist>
"#;
    if let Err(error) = fs::write(&plist, plist_content) {
        return StageOutcome::skipped(format!(
            "Failed to write macOS Info.plist {}: {}",
            plist.display(),
            error
        ));
    }

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if let Ok(metadata) = fs::metadata(&executable) {
            let mut permissions = metadata.permissions();
            permissions.set_mode(0o755);
            let _ = fs::set_permissions(&executable, permissions);
        }
    }

    let applications_dir = dirs_home().join("Applications");
    if let Err(error) = fs::create_dir_all(&applications_dir) {
        return StageOutcome::skipped(format!(
            "Failed to create user Applications directory {}: {}",
            applications_dir.display(),
            error
        ));
    }

    let app_link = applications_dir.join("Suzent.app");
    if let Ok(metadata) = fs::symlink_metadata(&app_link) {
        if metadata.file_type().is_symlink() {
            let _ = fs::remove_file(&app_link);
        } else {
            return StageOutcome::skipped(format!(
                "{} already exists and is not a symlink; app bundle is available at {}.",
                app_link.display(),
                app_bundle.display()
            ));
        }
    }

    if let Err(error) = std::os::unix::fs::symlink(&app_bundle, &app_link) {
        return StageOutcome::skipped(format!(
            "Failed to link macOS app into {}: {}. App bundle is available at {}.",
            app_link.display(),
            error,
            app_bundle.display()
        ));
    }

    StageOutcome::ok()
}

#[cfg(not(target_os = "macos"))]
fn create_macos_shortcuts(_config: &InstallConfig, _ui: &Path) -> StageOutcome {
    StageOutcome::skipped("macOS shortcuts are not supported on this platform.")
}

fn stage_shim(config: &InstallConfig) -> StageOutcome {
    if !cfg!(windows) {
        if let Err(error) = write_bootstrap_marker(config) {
            return StageOutcome::fail(format!("Failed to write bootstrap marker: {error}"));
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
    println!();
}

fn print_preview(config: &InstallConfig) {
    println!("Preview mode: no changes will be made.");
    println!();
    for (idx, stage) in stages().into_iter().enumerate() {
        println!("Step {}/{}: {}", idx + 1, stages().len(), stage.title);
        match stage.name {
            "repository" => {
                println!("  Clone or update {REPO_URL}");
                println!("  Target: {}", config.dir.display());
            }
            "dependencies" => println!("  uv sync --extra social"),
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
        let result = command.stdout(Stdio::piped()).stderr(Stdio::piped()).output();
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
    find_executable("git").or_else(|| {
        if cfg!(windows) {
            [
                r"C:\Program Files\Git\cmd\git.exe",
                r"C:\Program Files\Git\bin\git.exe",
                r"C:\Program Files (x86)\Git\cmd\git.exe",
            ]
            .iter()
            .map(PathBuf::from)
            .find(|path| path.exists())
        } else {
            None
        }
    })
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

fn default_install_dir() -> PathBuf {
    dirs_home().join("suzent")
}

fn dirs_home() -> PathBuf {
    env::var("HOME")
        .or_else(|_| env::var("USERPROFILE"))
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
    for line in text.lines().map(str::trim_end).filter(|line| !line.is_empty()) {
        log_detail(format!("{name}: {line}"));
    }
}

fn command_display(command: &Command) -> String {
    let mut parts = vec![command.get_program().to_string_lossy().to_string()];
    parts.extend(command.get_args().map(|arg| arg.to_string_lossy().to_string()));
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
