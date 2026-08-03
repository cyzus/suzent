use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::env;
use std::fs::{self, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const LATEST_RELEASE_API: &str = "https://api.github.com/repos/cyzus/suzent/releases/latest";
const RELEASE_BASE_URL: &str = "https://github.com/cyzus/suzent/releases/download";

#[derive(Deserialize)]
struct ReleaseResponse {
    tag_name: String,
}

#[derive(Deserialize, Serialize)]
struct UpdateStatus {
    phase: String,
    progress: u8,
    message: String,
    target_version: String,
    updated_at: u64,
    #[serde(default)]
    phase_started_at: u64,
    #[serde(default)]
    phase_durations_ms: BTreeMap<String, u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    downloaded_bytes: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    total_bytes: Option<u64>,
}

#[derive(Serialize, Deserialize)]
struct UpdateTransaction {
    target_tag: String,
    old_commit: String,
    old_branch: String,
    old_release_tag: String,
    old_ui_version: String,
    stashed_changes: bool,
    phase: String,
}

struct UpdateLock {
    path: PathBuf,
}

impl Drop for UpdateLock {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

struct UpdatePaths {
    root: PathBuf,
    state_dir: PathBuf,
    staging_dir: PathBuf,
    backup_dir: PathBuf,
    status: PathBuf,
    journal: PathBuf,
}

impl UpdatePaths {
    fn new(root: PathBuf, tag: &str) -> Self {
        let state_dir = root.join(".suzent");
        Self {
            staging_dir: state_dir.join("update-staging").join(tag),
            backup_dir: state_dir.join("update-backup"),
            status: state_dir.join("update-status.json"),
            journal: state_dir.join("update-transaction.json"),
            root,
            state_dir,
        }
    }

    fn ui_name(&self) -> &'static str {
        if cfg!(windows) {
            "suzent-ui.exe"
        } else {
            "suzent-ui"
        }
    }

    fn ui(&self) -> PathBuf {
        self.root.join("bin").join(self.ui_name())
    }

    fn staged_ui(&self) -> PathBuf {
        self.staging_dir.join(self.ui_name())
    }

    fn backup_ui(&self) -> PathBuf {
        self.backup_dir.join(self.ui_name())
    }

    fn ui_version(&self) -> PathBuf {
        self.root.join("bin").join("version.txt")
    }

    fn backup_ui_version(&self) -> PathBuf {
        self.backup_dir.join("version.txt")
    }
}

pub fn run(args: &[String], repair: bool) -> i32 {
    match run_inner(args, repair) {
        Ok(()) => 0,
        Err(error) => {
            eprintln!(
                "Suzent {} failed: {error}",
                if repair { "repair" } else { "update" }
            );
            1
        }
    }
}

fn run_inner(args: &[String], repair: bool) -> Result<(), String> {
    let root = flag_value(args, "--dir")
        .map(PathBuf::from)
        .ok_or_else(|| "--dir is required for update and repair".to_string())?;
    if !root.join(".git").exists() {
        return Err(format!("{} is not a Suzent Git checkout", root.display()));
    }

    if let Some(pid) = flag_value(args, "--wait-pid").and_then(|value| value.parse().ok()) {
        wait_for_process_exit(pid, Duration::from_secs(120));
    }
    thread::sleep(Duration::from_millis(750));

    let configured_target = flag_value(args, "--target").or_else(|| {
        repair
            .then(|| read_trimmed(root.join(".suzent/release-tag")))
            .flatten()
    });
    let target_tag = match configured_target {
        Some(tag) => tag,
        None => resolve_latest_release()?,
    };
    if !is_release_tag(&target_tag) {
        return Err(format!("invalid release tag: {target_tag}"));
    }

    let paths = UpdatePaths::new(root, &target_tag);
    fs::create_dir_all(&paths.state_dir).map_err(display_io("create update state directory"))?;
    let _lock = acquire_lock(&paths.state_dir)?;
    write_status(&paths, "preflight", 5, "Preparing update", &target_tag)?;

    let old_commit = git_text(&paths.root, &["rev-parse", "HEAD"])?;
    let old_branch = git_text(&paths.root, &["branch", "--show-current"])?;
    let old_release_tag = read_trimmed(paths.state_dir.join("release-tag")).unwrap_or_default();
    let old_ui_version = read_trimmed(paths.ui_version()).unwrap_or_default();
    let mut transaction = UpdateTransaction {
        target_tag: target_tag.clone(),
        old_commit,
        old_branch,
        old_release_tag,
        old_ui_version,
        stashed_changes: false,
        phase: "preflight".to_string(),
    };
    write_journal(&paths, &transaction)?;

    prepare_target(&paths, &target_tag)?;
    transaction.phase = "prepared".to_string();
    write_journal(&paths, &transaction)?;

    if has_local_changes(&paths.root)? {
        write_status(
            &paths,
            "preserve",
            30,
            "Preserving local changes",
            &target_tag,
        )?;
        run_checked(
            Command::new("git")
                .args(["stash", "push", "--include-untracked", "-m"])
                .arg(format!("suzent-update-{target_tag}"))
                .current_dir(&paths.root),
            "preserve local changes",
        )?;
        transaction.stashed_changes = true;
        write_journal(&paths, &transaction)?;
    }

    write_status(
        &paths,
        "stopping",
        40,
        "Stopping Suzent processes",
        &target_tag,
    )?;
    stop_suzent_processes(&paths.root)?;
    transaction.phase = "switching".to_string();
    write_journal(&paths, &transaction)?;

    let result = backup_current_ui(&paths).and_then(|()| install_target(&paths, &target_tag));
    if let Err(error) = result {
        let rollback_result = rollback(&paths, &transaction);
        if rollback_result.is_ok() {
            let _ = write_status(
                &paths,
                "rolled_back",
                100,
                "Update failed; previous version restored",
                &target_tag,
            );
            let _ = fs::remove_file(&paths.journal);
            return Err(error);
        }
        let rollback_error = rollback_result.unwrap_err();
        let _ = write_status(
            &paths,
            "repair_required",
            100,
            "Update and rollback failed; run suzent repair",
            &target_tag,
        );
        return Err(format!("{error}; rollback also failed: {rollback_error}"));
    }

    transaction.phase = "complete".to_string();
    write_journal(&paths, &transaction)?;
    write_status(
        &paths,
        "complete",
        100,
        "Suzent update complete",
        &target_tag,
    )?;
    cleanup_transaction_files(&paths);

    if let Some(relaunch) = flag_value(args, "--relaunch") {
        launch_app(&PathBuf::from(relaunch), &paths.root)?;
    }
    println!("Suzent is ready on {target_tag}");
    Ok(())
}

fn prepare_target(paths: &UpdatePaths, target_tag: &str) -> Result<(), String> {
    write_status(
        paths,
        "download",
        15,
        "Downloading desktop application",
        target_tag,
    )?;
    if paths.staging_dir.exists() {
        fs::remove_dir_all(&paths.staging_dir)
            .map_err(display_io("clear update staging directory"))?;
    }
    fs::create_dir_all(&paths.staging_dir)
        .map_err(display_io("create update staging directory"))?;
    download_file(
        &release_asset_url(target_tag),
        &paths.staged_ui(),
        paths,
        target_tag,
    )?;
    verify_release_asset(&paths.staged_ui(), target_tag, ui_asset_name())?;
    set_executable(&paths.staged_ui())?;

    write_status(paths, "fetch", 25, "Fetching release source", target_tag)?;
    run_checked(
        Command::new("git")
            .args(["fetch", "origin", "tag", target_tag])
            .current_dir(&paths.root),
        "fetch release source",
    )
}

fn install_target(paths: &UpdatePaths, target_tag: &str) -> Result<(), String> {
    write_status(paths, "source", 50, "Switching source version", target_tag)?;
    run_checked(
        Command::new("git")
            .args(["checkout", "--detach", target_tag])
            .current_dir(&paths.root),
        "check out release source",
    )?;

    write_status(
        paths,
        "dependencies",
        65,
        "Synchronizing Python environment",
        target_tag,
    )?;
    run_uv_sync(&paths.root)?;

    write_status(
        paths,
        "desktop",
        82,
        "Installing desktop application",
        target_tag,
    )?;
    install_staged_ui(paths, target_tag)?;

    write_status(
        paths,
        "verify",
        92,
        "Verifying installed version",
        target_tag,
    )?;
    verify_backend_version(&paths.root, target_tag)?;
    fs::write(paths.state_dir.join("release-tag"), target_tag)
        .map_err(display_io("record installed release"))?;
    fs::write(paths.state_dir.join("update-channel"), "stable")
        .map_err(display_io("record update channel"))?;
    Ok(())
}

fn rollback(paths: &UpdatePaths, transaction: &UpdateTransaction) -> Result<(), String> {
    write_status(
        paths,
        "rollback",
        90,
        "Restoring previous version",
        &transaction.target_tag,
    )?;
    let source_result = if transaction.old_branch.is_empty() {
        run_checked(
            Command::new("git")
                .args(["checkout", "--detach", &transaction.old_commit])
                .current_dir(&paths.root),
            "restore previous source",
        )
    } else {
        run_checked(
            Command::new("git")
                .args(["checkout", &transaction.old_branch])
                .current_dir(&paths.root),
            "restore previous branch",
        )
        .and_then(|()| {
            run_checked(
                Command::new("git")
                    .args(["reset", "--hard", &transaction.old_commit])
                    .current_dir(&paths.root),
                "restore previous commit",
            )
        })
    };
    let sync_result = source_result.and_then(|()| run_uv_sync(&paths.root));
    let ui_result = restore_ui_backup(paths, &transaction.old_ui_version);
    if transaction.old_release_tag.is_empty() {
        let _ = fs::remove_file(paths.state_dir.join("release-tag"));
    } else {
        fs::write(
            paths.state_dir.join("release-tag"),
            &transaction.old_release_tag,
        )
        .map_err(display_io("restore release marker"))?;
    }
    sync_result.and(ui_result)
}

fn backup_current_ui(paths: &UpdatePaths) -> Result<(), String> {
    if paths.backup_dir.exists() {
        fs::remove_dir_all(&paths.backup_dir).map_err(display_io("clear update backup"))?;
    }
    fs::create_dir_all(&paths.backup_dir).map_err(display_io("create update backup"))?;
    if paths.ui().exists() {
        fs::rename(paths.ui(), paths.backup_ui())
            .map_err(display_io("back up desktop application"))?;
    }
    if paths.ui_version().exists() {
        fs::rename(paths.ui_version(), paths.backup_ui_version())
            .map_err(display_io("back up desktop version marker"))?;
    }
    Ok(())
}

fn install_staged_ui(paths: &UpdatePaths, target_tag: &str) -> Result<(), String> {
    let bin = paths.root.join("bin");
    fs::create_dir_all(&bin).map_err(display_io("create desktop binary directory"))?;
    fs::rename(paths.staged_ui(), paths.ui()).map_err(display_io("install desktop application"))?;
    fs::write(paths.ui_version(), target_tag)
        .map_err(display_io("write desktop version marker"))?;
    Ok(())
}

fn restore_ui_backup(paths: &UpdatePaths, old_version: &str) -> Result<(), String> {
    if paths.ui().exists() {
        fs::remove_file(paths.ui()).map_err(display_io("remove failed desktop application"))?;
    }
    if paths.backup_ui().exists() {
        fs::rename(paths.backup_ui(), paths.ui())
            .map_err(display_io("restore desktop application"))?;
    }
    if paths.ui_version().exists() {
        fs::remove_file(paths.ui_version()).map_err(display_io("remove failed version marker"))?;
    }
    if paths.backup_ui_version().exists() {
        fs::rename(paths.backup_ui_version(), paths.ui_version())
            .map_err(display_io("restore desktop version marker"))?;
    } else if !old_version.is_empty() {
        fs::write(paths.ui_version(), old_version)
            .map_err(display_io("restore desktop version"))?;
    }
    Ok(())
}

fn verify_backend_version(root: &Path, target_tag: &str) -> Result<(), String> {
    let python = if cfg!(windows) {
        root.join(".venv/Scripts/python.exe")
    } else {
        root.join(".venv/bin/python")
    };
    let output = Command::new(&python)
        .args([
            "-c",
            "from importlib.metadata import version; print(version('suzent'))",
        ])
        .current_dir(root)
        .output()
        .map_err(|error| format!("failed to verify backend version: {error}"))?;
    if !output.status.success() {
        return Err("backend version verification command failed".to_string());
    }
    let actual = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let expected = target_tag.trim_start_matches('v');
    if actual != expected {
        return Err(format!(
            "backend version mismatch: expected {expected}, found {actual}"
        ));
    }
    Ok(())
}

fn run_uv_sync(root: &Path) -> Result<(), String> {
    let mut last_error = String::new();
    for attempt in 1..=3 {
        match run_checked(
            Command::new("uv")
                .args(["sync", "--frozen", "--extra", "social"])
                .current_dir(root),
            "synchronize Python environment",
        ) {
            Ok(()) => return Ok(()),
            Err(error) => last_error = error,
        }
        if attempt < 3 {
            eprintln!("Python environment was still busy; retrying ({attempt}/3)...");
            thread::sleep(Duration::from_secs(2));
        }
    }
    Err(last_error)
}

fn stop_suzent_processes(root: &Path) -> Result<(), String> {
    let root_text = root.display().to_string();
    let current_pid = std::process::id();
    if cfg!(windows) {
        let escaped = root_text.replace('\'', "''");
        let script = format!(
            "$root='{escaped}'; $self={current_pid}; Get-CimInstance Win32_Process | Where-Object {{ $_.ProcessId -ne $self -and $_.Name -notlike 'suzent-installer*' -and (($_.ExecutablePath -like \"$root*\") -or ($_.CommandLine -like \"*$root*\")) }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}"
        );
        let _ = Command::new("powershell")
            .args(["-NoProfile", "-Command", &script])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    } else {
        let output = Command::new("pgrep").args(["-f", &root_text]).output();
        if let Ok(output) = output {
            for line in String::from_utf8_lossy(&output.stdout).lines() {
                if let Ok(pid) = line.trim().parse::<u32>() {
                    if pid != current_pid {
                        let _ = Command::new("kill")
                            .args(["-TERM", &pid.to_string()])
                            .status();
                    }
                }
            }
        }
    }
    thread::sleep(Duration::from_secs(1));
    Ok(())
}

fn wait_for_process_exit(pid: u32, timeout: Duration) {
    let started = SystemTime::now();
    while process_exists(pid) {
        if started.elapsed().unwrap_or_default() >= timeout {
            break;
        }
        thread::sleep(Duration::from_millis(200));
    }
}

#[cfg(windows)]
fn process_exists(pid: u32) -> bool {
    use windows_sys::Win32::Foundation::{CloseHandle, ERROR_INVALID_PARAMETER};
    use windows_sys::Win32::System::Threading::{OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION};

    unsafe {
        let handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
        if !handle.is_null() {
            CloseHandle(handle);
            return true;
        }
        std::io::Error::last_os_error().raw_os_error() != Some(ERROR_INVALID_PARAMETER as i32)
    }
}

#[cfg(not(windows))]
fn process_exists(pid: u32) -> bool {
    Command::new("kill")
        .args(["-0", &pid.to_string()])
        .status()
        .map(|status| status.success())
        .unwrap_or(true)
}

fn acquire_lock(state_dir: &Path) -> Result<UpdateLock, String> {
    let path = state_dir.join("update.lock");
    match OpenOptions::new().write(true).create_new(true).open(&path) {
        Ok(mut file) => {
            writeln!(file, "{}", std::process::id()).map_err(display_io("write update lock"))?;
            Ok(UpdateLock { path })
        }
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {
            let pid = read_trimmed(&path).and_then(|value| value.parse::<u32>().ok());
            if pid.is_some_and(process_exists) {
                return Err(format!(
                    "another Suzent update is already running (PID {})",
                    pid.unwrap()
                ));
            }
            fs::remove_file(&path).map_err(display_io("remove stale update lock"))?;
            acquire_lock(state_dir)
        }
        Err(error) => Err(format!("failed to acquire update lock: {error}")),
    }
}

fn resolve_latest_release() -> Result<String, String> {
    let api =
        env::var("SUZENT_LATEST_RELEASE_API").unwrap_or_else(|_| LATEST_RELEASE_API.to_string());
    let response = reqwest::blocking::Client::builder()
        .user_agent("suzent-installer")
        .build()
        .map_err(|error| format!("failed to create release client: {error}"))?
        .get(api)
        .send()
        .and_then(|response| response.error_for_status())
        .map_err(|error| format!("failed to resolve latest release: {error}"))?
        .json::<ReleaseResponse>()
        .map_err(|error| format!("invalid latest release response: {error}"))?;
    Ok(response.tag_name)
}

fn release_asset_url(tag: &str) -> String {
    let base = release_base_url(tag);
    format!("{}/{}", base.trim_end_matches('/'), ui_asset_name())
}

fn release_base_url(tag: &str) -> String {
    env::var("SUZENT_RELEASE_BASE_URL").unwrap_or_else(|_| format!("{RELEASE_BASE_URL}/{tag}"))
}

fn ui_asset_name() -> &'static str {
    if cfg!(windows) {
        "suzent-windows-x86_64.exe"
    } else if cfg!(target_os = "macos") && cfg!(target_arch = "aarch64") {
        "suzent-macos-aarch64"
    } else if cfg!(target_os = "macos") {
        "suzent-macos-x86_64"
    } else {
        "suzent-linux-x86_64"
    }
}

fn download_file(
    url: &str,
    destination: &Path,
    paths: &UpdatePaths,
    tag: &str,
) -> Result<(), String> {
    let mut response = reqwest::blocking::Client::builder()
        .user_agent("suzent-installer")
        .connect_timeout(Duration::from_secs(30))
        .build()
        .map_err(|error| format!("failed to create download client: {error}"))?
        .get(url)
        .send()
        .and_then(|response| response.error_for_status())
        .map_err(|error| format!("failed to download {url}: {error}"))?;
    let total = response.content_length();
    let temporary = destination.with_extension("download");
    let result = (|| {
        let mut file = fs::File::create(&temporary).map_err(display_io("create download"))?;
        let mut buffer = [0_u8; 256 * 1024];
        let mut downloaded = 0_u64;
        let mut last_report = Instant::now() - Duration::from_secs(1);
        loop {
            let count = response
                .read(&mut buffer)
                .map_err(|error| format!("failed to read {url}: {error}"))?;
            if count == 0 {
                break;
            }
            file.write_all(&buffer[..count])
                .map_err(display_io("write downloaded asset"))?;
            downloaded += count as u64;
            if last_report.elapsed() >= Duration::from_millis(250)
                || total.is_some_and(|size| downloaded >= size)
            {
                write_download_status(paths, tag, downloaded, total)?;
                last_report = Instant::now();
            }
        }
        file.sync_all()
            .map_err(display_io("flush downloaded asset"))?;
        if total.is_some_and(|size| downloaded != size) {
            return Err(format!(
                "incomplete download: received {downloaded} of {} bytes",
                total.unwrap()
            ));
        }
        fs::rename(&temporary, destination).map_err(display_io("finish downloaded asset"))
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

fn verify_release_asset(path: &Path, tag: &str, asset_name: &str) -> Result<(), String> {
    let url = format!("{}/SHA256SUMS", release_base_url(tag).trim_end_matches('/'));
    let checksums = reqwest::blocking::Client::builder()
        .user_agent("suzent-installer")
        .build()
        .map_err(|error| format!("failed to create checksum client: {error}"))?
        .get(&url)
        .send()
        .and_then(|response| response.error_for_status())
        .map_err(|error| format!("failed to download release checksums: {error}"))?
        .text()
        .map_err(|error| format!("failed to read release checksums: {error}"))?;
    let expected = parse_release_checksum(&checksums, asset_name)?;
    let bytes = fs::read(path).map_err(display_io("read downloaded asset"))?;
    let actual = format!("{:x}", Sha256::digest(bytes));
    if actual != expected {
        return Err(format!(
            "checksum mismatch for {asset_name}: expected {expected}, found {actual}"
        ));
    }
    Ok(())
}

fn parse_release_checksum(contents: &str, asset_name: &str) -> Result<String, String> {
    for line in contents.lines() {
        let mut parts = line.split_whitespace();
        let Some(digest) = parts.next() else {
            continue;
        };
        let Some(filename) = parts.next() else {
            continue;
        };
        if filename.trim_start_matches('*') == asset_name
            && digest.len() == 64
            && digest
                .chars()
                .all(|character| character.is_ascii_hexdigit())
        {
            return Ok(digest.to_ascii_lowercase());
        }
    }
    Err(format!("SHA256SUMS has no valid entry for {asset_name}"))
}

fn write_status(
    paths: &UpdatePaths,
    phase: &str,
    progress: u8,
    message: &str,
    tag: &str,
) -> Result<(), String> {
    println!("[{progress:>3}%] {message}");
    write_status_details(paths, phase, progress, message, tag, None, None)
}

fn write_download_status(
    paths: &UpdatePaths,
    tag: &str,
    downloaded_bytes: u64,
    total_bytes: Option<u64>,
) -> Result<(), String> {
    let percent = total_bytes
        .filter(|total| *total > 0)
        .map(|total| (downloaded_bytes.saturating_mul(100) / total).min(100));
    let progress = percent
        .map(|value| 15 + (value.saturating_mul(9) / 100) as u8)
        .unwrap_or(15);
    let message = match total_bytes {
        Some(total) => format!(
            "Downloading desktop application ({:.1} / {:.1} MiB, {}%)",
            downloaded_bytes as f64 / 1024.0 / 1024.0,
            total as f64 / 1024.0 / 1024.0,
            percent.unwrap_or(0)
        ),
        None => format!(
            "Downloading desktop application ({:.1} MiB)",
            downloaded_bytes as f64 / 1024.0 / 1024.0
        ),
    };
    print!("\r[{progress:>3}%] {message}");
    io::stdout()
        .flush()
        .map_err(display_io("flush download progress"))?;
    if percent == Some(100) {
        println!();
    }
    write_status_details(
        paths,
        "download",
        progress,
        &message,
        tag,
        Some(downloaded_bytes),
        total_bytes,
    )
}

#[allow(clippy::too_many_arguments)]
fn write_status_details(
    paths: &UpdatePaths,
    phase: &str,
    progress: u8,
    message: &str,
    tag: &str,
    downloaded_bytes: Option<u64>,
    total_bytes: Option<u64>,
) -> Result<(), String> {
    let now = now_epoch_millis();
    let previous = fs::read(&paths.status)
        .ok()
        .and_then(|bytes| serde_json::from_slice::<UpdateStatus>(&bytes).ok());
    let same_transaction = previous
        .as_ref()
        .filter(|status| status.target_version == tag);
    let mut phase_durations_ms = same_transaction
        .map(|status| status.phase_durations_ms.clone())
        .unwrap_or_default();
    if let Some(status) = same_transaction {
        if status.phase != phase {
            let started_at = status
                .phase_started_at
                .max(status.updated_at.saturating_mul(1_000));
            phase_durations_ms.insert(status.phase.clone(), now.saturating_sub(started_at));
        }
    }
    let phase_started_at = same_transaction
        .filter(|status| status.phase == phase)
        .map(|status| {
            status
                .phase_started_at
                .max(status.updated_at.saturating_mul(1_000))
        })
        .unwrap_or(now);
    let payload = UpdateStatus {
        phase: phase.to_string(),
        progress,
        message: message.to_string(),
        target_version: tag.to_string(),
        updated_at: now / 1_000,
        phase_started_at,
        phase_durations_ms,
        downloaded_bytes,
        total_bytes,
    };
    write_json_atomic(&paths.status, &payload, "write update status")
}

fn write_journal(paths: &UpdatePaths, transaction: &UpdateTransaction) -> Result<(), String> {
    write_json_atomic(&paths.journal, transaction, "write update transaction")
}

fn write_json_atomic<T: Serialize>(
    path: &Path,
    value: &T,
    action: &'static str,
) -> Result<(), String> {
    let temporary = path.with_extension("tmp");
    let bytes = serde_json::to_vec_pretty(value).map_err(|error| format!("{action}: {error}"))?;
    fs::write(&temporary, bytes).map_err(display_io(action))?;
    if path.exists() {
        fs::remove_file(path).map_err(display_io(action))?;
    }
    fs::rename(temporary, path).map_err(display_io(action))
}

fn cleanup_transaction_files(paths: &UpdatePaths) {
    let _ = fs::remove_file(&paths.journal);
    let _ = fs::remove_dir_all(&paths.staging_dir);
    let _ = fs::remove_dir_all(&paths.backup_dir);
}

fn has_local_changes(root: &Path) -> Result<bool, String> {
    Ok(!git_text(root, &["status", "--porcelain"])?
        .trim()
        .is_empty())
}

fn git_text(root: &Path, args: &[&str]) -> Result<String, String> {
    let output = Command::new("git")
        .args(args)
        .current_dir(root)
        .output()
        .map_err(|error| format!("failed to run git {}: {error}", args.join(" ")))?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_string());
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn run_checked(command: &mut Command, action: &str) -> Result<(), String> {
    let status = command
        .status()
        .map_err(|error| format!("failed to {action}: {error}"))?;
    if status.success() {
        Ok(())
    } else {
        Err(format!(
            "failed to {action} (exit {})",
            status.code().unwrap_or(1)
        ))
    }
}

fn launch_app(executable: &Path, root: &Path) -> Result<(), String> {
    Command::new(executable)
        .current_dir(root)
        .spawn()
        .map_err(|error| format!("failed to relaunch Suzent: {error}"))?;
    Ok(())
}

fn flag_value(args: &[String], flag: &str) -> Option<String> {
    args.iter()
        .position(|arg| arg == flag)
        .and_then(|index| args.get(index + 1))
        .cloned()
}

fn is_release_tag(value: &str) -> bool {
    let Some(version) = value.strip_prefix('v') else {
        return false;
    };
    let parts: Vec<_> = version.split('.').collect();
    parts.len() == 3
        && parts
            .iter()
            .all(|part| !part.is_empty() && part.chars().all(|c| c.is_ascii_digit()))
}

fn read_trimmed(path: impl AsRef<Path>) -> Option<String> {
    fs::read_to_string(path)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn now_epoch_millis() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

fn display_io(action: &'static str) -> impl Fn(io::Error) -> String {
    move |error| format!("failed to {action}: {error}")
}

#[cfg(unix)]
fn set_executable(path: &Path) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt;
    let mut permissions = fs::metadata(path)
        .map_err(display_io("read asset permissions"))?
        .permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(path, permissions).map_err(display_io("set asset permissions"))
}

#[cfg(windows)]
fn set_executable(_path: &Path) -> Result<(), String> {
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{
        acquire_lock, backup_current_ui, is_release_tag, parse_release_checksum, restore_ui_backup,
        write_download_status, write_status, UpdatePaths, UpdateStatus,
    };
    use std::fs;
    use std::thread;
    use std::time::Duration;

    #[test]
    fn validates_release_tags() {
        assert!(is_release_tag("v0.7.8"));
        assert!(!is_release_tag("0.7.8"));
        assert!(!is_release_tag("v0.7"));
        assert!(!is_release_tag("v0.7.8-rc1"));
    }

    #[test]
    fn selects_exact_release_checksum() {
        let digest = "a".repeat(64);
        let contents = format!("{}  other\n{} *suzent.exe\n", "b".repeat(64), digest);
        assert_eq!(
            parse_release_checksum(&contents, "suzent.exe").expect("checksum"),
            digest
        );
    }

    #[test]
    fn restores_desktop_files_from_transaction_backup() {
        let temp = tempfile::tempdir().expect("temp dir");
        let paths = UpdatePaths::new(temp.path().to_path_buf(), "v1.2.3");
        fs::create_dir_all(temp.path().join("bin")).expect("bin dir");
        fs::write(paths.ui(), b"old-ui").expect("old ui");
        fs::write(paths.ui_version(), "v1.2.2").expect("old version");

        backup_current_ui(&paths).expect("backup");
        fs::write(paths.ui(), b"broken-ui").expect("broken ui");
        fs::write(paths.ui_version(), "v1.2.3").expect("broken version");
        restore_ui_backup(&paths, "v1.2.2").expect("restore");

        assert_eq!(fs::read(paths.ui()).expect("restored ui"), b"old-ui");
        assert_eq!(
            fs::read_to_string(paths.ui_version()).expect("restored version"),
            "v1.2.2"
        );
    }

    #[test]
    fn update_lock_rejects_a_second_live_updater() {
        let temp = tempfile::tempdir().expect("temp dir");
        let first = acquire_lock(temp.path()).expect("first lock");
        let second = acquire_lock(temp.path());
        assert!(second.is_err());
        drop(first);
        assert!(acquire_lock(temp.path()).is_ok());
    }

    #[test]
    fn records_completed_phase_durations_in_status() {
        let temp = tempfile::tempdir().expect("temp dir");
        let paths = UpdatePaths::new(temp.path().to_path_buf(), "v1.2.3");
        fs::create_dir_all(&paths.state_dir).expect("state dir");

        write_status(&paths, "preflight", 5, "Preparing", "v1.2.3").expect("first status");
        thread::sleep(Duration::from_millis(2));
        write_status(&paths, "download", 15, "Downloading", "v1.2.3").expect("second status");

        let status: UpdateStatus =
            serde_json::from_slice(&fs::read(&paths.status).expect("status file"))
                .expect("valid status");
        assert_eq!(status.phase, "download");
        assert!(status.phase_durations_ms.contains_key("preflight"));
        assert!(status.phase_started_at > 0);
    }

    #[test]
    fn records_download_byte_progress_in_status() {
        let temp = tempfile::tempdir().expect("temp dir");
        let paths = UpdatePaths::new(temp.path().to_path_buf(), "v1.2.3");
        fs::create_dir_all(&paths.state_dir).expect("state dir");

        write_download_status(&paths, "v1.2.3", 5 * 1024 * 1024, Some(10 * 1024 * 1024))
            .expect("download status");

        let status: UpdateStatus =
            serde_json::from_slice(&fs::read(&paths.status).expect("status file"))
                .expect("valid status");
        assert_eq!(status.phase, "download");
        assert_eq!(status.downloaded_bytes, Some(5 * 1024 * 1024));
        assert_eq!(status.total_bytes, Some(10 * 1024 * 1024));
        assert_eq!(status.progress, 19);
    }
}
