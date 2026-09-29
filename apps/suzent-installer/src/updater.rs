use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::env;
use std::fs::{self, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const LATEST_RELEASE_API: &str = "https://api.github.com/repos/cyzus/suzent/releases/latest";
const RELEASE_BASE_URL: &str = "https://github.com/cyzus/suzent/releases/download";
/// Keeps a captured failure reason short enough to stay readable in the UI.
const FAILURE_DETAIL_LIMIT: usize = 600;

fn background_command(program: impl AsRef<std::ffi::OsStr>) -> Command {
    let mut command = Command::new(program);
    crate::hide_command_window(&mut command);
    command
}

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
    #[serde(default, skip_serializing_if = "is_false")]
    failed: bool,
    #[serde(default)]
    warnings: Vec<String>,
}

fn is_false(value: &bool) -> bool {
    !*value
}

#[derive(Serialize, Deserialize)]
struct UpdateTransaction {
    target_tag: String,
    #[serde(default)]
    target_commit: String,
    old_commit: String,
    old_branch: String,
    old_release_tag: String,
    old_ui_version: String,
    stashed_changes: bool,
    #[serde(default)]
    stash_commit: Option<String>,
    #[serde(default)]
    recovery_dir: Option<String>,
    phase: String,
}

#[derive(Serialize, Deserialize)]
struct RecoveryManifest {
    created_at: u64,
    reason: String,
    old_commit: String,
    old_branch: String,
    tracked_files: Vec<String>,
    untracked_files: Vec<String>,
    conflict_stages: Vec<String>,
}

struct UpdateLock {
    path: PathBuf,
}

impl Drop for UpdateLock {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

struct ServiceRestartGuard {
    root: PathBuf,
    enabled: bool,
    stopped: bool,
}

impl ServiceRestartGuard {
    fn detect(root: &Path) -> Self {
        Self {
            root: root.to_path_buf(),
            enabled: service_definition_exists(),
            stopped: false,
        }
    }

    fn stop(&mut self) -> Result<(), String> {
        if !self.enabled || self.stopped {
            return Ok(());
        }
        run_service_command(&self.root, "stop")?;
        self.stopped = true;
        Ok(())
    }

    fn restart(&mut self) -> Result<(), String> {
        if !self.stopped {
            return Ok(());
        }
        run_service_command(&self.root, "start")?;
        self.stopped = false;
        Ok(())
    }
}

impl Drop for ServiceRestartGuard {
    fn drop(&mut self) {
        if self.stopped {
            if let Err(error) = run_service_command(&self.root, "start") {
                eprintln!("failed to restore Suzent service after update: {error}");
            }
        }
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

pub(crate) fn run_inner(args: &[String], repair: bool) -> Result<(), String> {
    let root = flag_value(args, "--dir")
        .map(PathBuf::from)
        .ok_or_else(|| "--dir is required for update and repair".to_string())?;
    if !root.join(".git").exists() {
        return Err(format!("{} is not a Suzent Git checkout", root.display()));
    }

    if let Some(pid) = flag_value(args, "--wait-pid").and_then(|value| value.parse().ok()) {
        wait_for_process_exit(pid, Duration::from_secs(120))?;
    }

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
    recover_legacy_journal(&paths)?;

    if paths.journal.exists() {
        if !repair {
            return Err(format!(
                "an interrupted update is recorded in {}; run 'suzent repair' before updating again",
                paths.journal.display()
            ));
        }
        recover_interrupted_update(&paths)?;
    }

    if let Err(error) = run_transaction(
        &paths,
        &target_tag,
        args.iter().any(|arg| arg == "--backup-conflicts"),
    ) {
        record_failure(&paths, &target_tag, &error);
        return Err(error);
    }

    if let Some(relaunch) = flag_value(args, "--relaunch") {
        launch_app(&PathBuf::from(relaunch), &paths.root)?;
    }
    println!("Suzent is ready on {target_tag}");
    Ok(())
}

/// Runs the whole update transaction so a failure at any phase can be
/// recorded on the status document by the caller.
fn run_transaction(
    paths: &UpdatePaths,
    target_tag: &str,
    backup_conflicts: bool,
) -> Result<(), String> {
    let mut service_guard = ServiceRestartGuard::detect(&paths.root);
    write_status(paths, "preflight", 5, "Preparing update", target_tag)?;
    let repository_hazard = repository_hazard(&paths.root)?;
    let old_commit = git_text(&paths.root, &["rev-parse", "HEAD"])?;
    let old_branch = git_text(&paths.root, &["branch", "--show-current"])?;
    if let Some(reason) = &repository_hazard {
        if !backup_conflicts {
            return Err(format!("CONFIRM_GIT_RECOVERY: {reason}\nDirectory: {}\nSource: {old_branch} ({old_commit})\nTarget: {target_tag}\nBack up local changes and Git operation state before continuing. Local changes will not be reapplied automatically. No source files have been changed.", paths.root.display()));
        }
    }

    let old_release_tag = read_trimmed(paths.state_dir.join("release-tag")).unwrap_or_default();
    let old_ui_version = read_trimmed(paths.ui_version()).unwrap_or_default();
    let mut transaction = UpdateTransaction {
        target_tag: target_tag.to_string(),
        target_commit: String::new(),
        old_commit,
        old_branch,
        old_release_tag,
        old_ui_version,
        stashed_changes: false,
        stash_commit: None,
        recovery_dir: None,
        phase: "preflight".to_string(),
    };

    transaction.target_commit = prepare_target(paths, target_tag)?;
    transaction.phase = "prepared".to_string();
    write_journal(paths, &transaction)?;

    write_status(
        paths,
        "stopping",
        28,
        "Stopping Suzent processes",
        target_tag,
    )?;
    service_guard.stop()?;
    stop_suzent_processes(&paths.root)?;

    if let Some(reason) = repository_hazard {
        write_status(
            paths,
            "preserve",
            30,
            "Saving conflicted Git checkout",
            target_tag,
        )?;
        let recovery_dir = paths
            .state_dir
            .join("update-recovery")
            .join(format!("{}-{target_tag}", now_epoch_millis()));
        transaction.recovery_dir = Some(recovery_dir.display().to_string());
        transaction.phase = "preserving".to_string();
        write_journal(paths, &transaction)?;
        preserve_conflicted_checkout(
            &paths.root,
            &recovery_dir,
            &reason,
            &transaction.old_commit,
            &transaction.old_branch,
        ).map_err(|error| format!("{error}; conflict backup location: {}. Source cleanup was not started; run suzent repair after inspecting the journal.", recovery_dir.display()))?;
        println!(
            "Local source changes were saved in {}",
            recovery_dir.display()
        );
        transaction.phase = "preserved".to_string();
        write_journal(paths, &transaction)?;
        clear_preserved_conflicts(&paths.root, &recovery_dir, &transaction.old_commit)
            .map_err(|error| format!("{error}; local source snapshot: {}. Run suzent repair after inspecting the recovery instructions.", recovery_dir.display()))?;
    } else if has_local_changes(&paths.root)? {
        write_status(
            paths,
            "preserve",
            30,
            "Preserving local changes",
            target_tag,
        )?;
        run_checked(
            background_command("git")
                .args([
                    "-c",
                    "user.name=Suzent Updater",
                    "-c",
                    "user.email=updater@suzent.invalid",
                    "stash",
                    "push",
                    "--include-untracked",
                    "-m",
                ])
                .arg(format!("suzent-update-{target_tag}"))
                .current_dir(&paths.root),
            "preserve local changes",
        )?;
        transaction.stashed_changes = true;
        transaction.stash_commit = Some(git_text(&paths.root, &["rev-parse", "refs/stash"])?);
        transaction.phase = "preserved".to_string();
        write_journal(paths, &transaction)?;
    }

    write_status(
        paths,
        "stopping",
        40,
        "Stopping Suzent processes",
        target_tag,
    )?;
    service_guard.stop()?;
    stop_suzent_processes(&paths.root)?;
    transaction.phase = "switching".to_string();
    write_journal(paths, &transaction)?;

    let result = backup_current_ui(paths).and_then(|()| install_target(paths, target_tag));
    if let Err(error) = result {
        let error = match &transaction.recovery_dir {
            Some(directory) => format!("{error}; local conflict state is saved in {directory}. Source rollback does not reapply these local changes."),
            None => error,
        };
        let rollback_result = rollback(paths, &transaction);
        if rollback_result.is_ok() {
            let _ = write_status(
                paths,
                "rolled_back",
                100,
                "Update failed; previous version restored",
                target_tag,
            );
            let _ = fs::remove_file(&paths.journal);
            return Err(error);
        }
        let rollback_error = rollback_result.unwrap_err();
        let _ = write_status(
            paths,
            "repair_required",
            100,
            "Update and rollback failed; run suzent repair",
            target_tag,
        );
        return Err(format!("{error}; rollback also failed: {rollback_error}"));
    }

    transaction.phase = "complete".to_string();
    write_journal(paths, &transaction)?;
    let completion_message = match &transaction.recovery_dir {
        Some(recovery_dir) => {
            format!("Suzent update complete; local source changes saved in {recovery_dir}")
        }
        None => "Suzent update complete".to_string(),
    };
    write_status(paths, "complete", 100, &completion_message, target_tag)?;
    cleanup_transaction_files(paths);
    service_guard.restart()?;
    Ok(())
}

fn recover_interrupted_update(paths: &UpdatePaths) -> Result<(), String> {
    let bytes = fs::read(&paths.journal).map_err(display_io("read update transaction"))?;
    let transaction: UpdateTransaction = serde_json::from_slice(&bytes)
        .map_err(|error| format!("failed to read update transaction: {error}"))?;
    if transaction.phase == "complete" {
        cleanup_transaction_files(&UpdatePaths::new(
            paths.root.clone(),
            &transaction.target_tag,
        ));
        return Ok(());
    }
    if transaction.phase == "preserving" && repository_hazard(&paths.root)?.is_some() {
        return Err(format!(
            "local-change preservation was interrupted; inspect {} and resolve Git conflicts manually before retrying; journal retained",
            transaction.recovery_dir.as_deref().unwrap_or("the recovery directory")
        ));
    }
    write_status(
        paths,
        "rollback",
        5,
        "Recovering interrupted update",
        &transaction.target_tag,
    )?;
    let recovery_result = if matches!(transaction.phase.as_str(), "switching" | "complete") {
        let mut service_guard = ServiceRestartGuard::detect(&paths.root);
        service_guard.stop()?;
        stop_suzent_processes(&paths.root)?;
        let recovery_paths = UpdatePaths::new(paths.root.clone(), &transaction.target_tag);
        let result = rollback(&recovery_paths, &transaction);
        let restart_result = service_guard.restart();
        result.and(restart_result)
    } else {
        Ok(())
    };
    recovery_result.map_err(|error| {
        format!("failed to recover interrupted update; backups and journal were preserved: {error}")
    })?;
    fs::remove_file(&paths.journal).map_err(display_io("finish interrupted update recovery"))?;
    Ok(())
}

#[cfg(windows)]
fn service_definition_exists() -> bool {
    use winreg::enums::HKEY_CURRENT_USER;
    use winreg::RegKey;

    RegKey::predef(HKEY_CURRENT_USER)
        .open_subkey(r"Software\Microsoft\Windows\CurrentVersion\Run")
        .and_then(|key| key.get_value::<String, _>("Suzent Service"))
        .is_ok()
}

#[cfg(not(windows))]
fn service_definition_exists() -> bool {
    let Some(home) = dirs::home_dir() else {
        return false;
    };
    if cfg!(target_os = "macos") {
        return home
            .join("Library/LaunchAgents/com.suzent.service.plist")
            .exists();
    }
    home.join(".config/systemd/user/suzent.service").exists()
}

fn service_python(root: &Path) -> PathBuf {
    if cfg!(windows) {
        root.join(".venv/Scripts/python.exe")
    } else {
        root.join(".venv/bin/python")
    }
}

fn run_service_command(root: &Path, action: &str) -> Result<(), String> {
    let python = service_python(root);
    if !python.exists() {
        return Err(format!(
            "service Python executable is missing: {}",
            python.display()
        ));
    }
    run_checked(
        background_command(python)
            .args(["-m", "suzent.cli", "service", action])
            .current_dir(root),
        action,
    )
}

fn prepare_target(paths: &UpdatePaths, target_tag: &str) -> Result<String, String> {
    write_status(
        paths,
        "download",
        15,
        "Downloading desktop application",
        target_tag,
    )?;
    fs::create_dir_all(&paths.staging_dir)
        .map_err(display_io("create update staging directory"))?;
    let expected = release_checksum(target_tag, ui_asset_name())?;
    prepare_ui(paths, &expected, || {
        download_file(
            &release_asset_url(target_tag),
            &paths.staged_ui(),
            paths,
            target_tag,
        )
    })?;
    set_executable(&paths.staged_ui())?;

    write_status(paths, "fetch", 25, "Fetching release source", target_tag)?;
    run_checked(
        background_command("git")
            .args(["fetch", "--force", "origin", "tag", target_tag])
            .current_dir(&paths.root),
        "fetch release source",
    )?;
    git_text(&paths.root, &["rev-list", "-n", "1", target_tag])
}

fn prepare_ui(
    paths: &UpdatePaths,
    expected: &str,
    download: impl FnOnce() -> Result<(), String>,
) -> Result<(), String> {
    if verify_asset_checksum(&paths.staged_ui(), expected).is_ok() {
        return Ok(());
    }
    if paths.staged_ui().exists() {
        fs::remove_file(paths.staged_ui())
            .map_err(display_io("remove invalid staged application"))?;
    }
    if verify_asset_checksum(&paths.ui(), expected).is_ok() {
        fs::copy(paths.ui(), paths.staged_ui())
            .map_err(display_io("stage installed desktop application"))?;
    } else {
        download()?;
    }
    verify_asset_checksum(&paths.staged_ui(), expected)
}

fn install_target(paths: &UpdatePaths, target_tag: &str) -> Result<(), String> {
    write_status(paths, "source", 50, "Switching source version", target_tag)?;
    let transaction = read_transaction(paths)?;
    let target_commit = if transaction.target_commit.is_empty() {
        target_tag
    } else {
        &transaction.target_commit
    };
    run_checked(
        background_command("git")
            .args([
                "checkout",
                "--no-overwrite-ignore",
                "--detach",
                target_commit,
            ])
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

    write_status(
        paths,
        "shortcuts",
        96,
        "Refreshing launcher shortcuts",
        target_tag,
    )?;
    if let Err(error) = refresh_shortcuts(paths) {
        let mut status: UpdateStatus = serde_json::from_slice(
            &fs::read(&paths.status).map_err(display_io("read shortcut status"))?,
        )
        .map_err(|error| error.to_string())?;
        status
            .warnings
            .push(format!("{error}; run 'suzent shortcuts' to retry"));
        write_json_atomic(&paths.status, &status, "record shortcut warning")?;
    }
    Ok(())
}

fn read_transaction(paths: &UpdatePaths) -> Result<UpdateTransaction, String> {
    let bytes = fs::read(&paths.journal).map_err(display_io("read update transaction"))?;
    serde_json::from_slice(&bytes)
        .map_err(|error| format!("failed to read update transaction: {error}"))
}

/// Repairs the launcher entries through `suzent.cli.shortcuts`, the same code
/// the installer and the setup scripts run, so entries the user deleted or that
/// point at a moved install come back on every update.
///
/// Deliberately not fatal: a missing desktop icon is no reason to roll back an
/// otherwise working update, so a failure is reported and the update completes.
fn refresh_shortcuts(paths: &UpdatePaths) -> Result<(), String> {
    let python = service_python(&paths.root);
    if !python.exists() {
        return Err(format!(
            "skipped launcher shortcut repair: {} is missing",
            python.display()
        ));
    }
    run_checked(
        background_command(python)
            .args(["-m", "suzent.cli", "shortcuts"])
            .current_dir(&paths.root),
        "refresh launcher shortcuts",
    )
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
            background_command("git")
                .args(["checkout", "--detach", &transaction.old_commit])
                .current_dir(&paths.root),
            "restore previous source",
        )
    } else {
        run_checked(
            background_command("git")
                .args(["checkout", &transaction.old_branch])
                .current_dir(&paths.root),
            "restore previous branch",
        )
        .and_then(|()| {
            run_checked(
                background_command("git")
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
        rename_with_retry(
            &paths.ui(),
            &paths.backup_ui(),
            "back up desktop application",
        )?;
    }
    if paths.ui_version().exists() {
        rename_with_retry(
            &paths.ui_version(),
            &paths.backup_ui_version(),
            "back up desktop version marker",
        )?;
    }
    Ok(())
}

fn install_staged_ui(paths: &UpdatePaths, target_tag: &str) -> Result<(), String> {
    let bin = paths.root.join("bin");
    fs::create_dir_all(&bin).map_err(display_io("create desktop binary directory"))?;
    rename_with_retry(
        &paths.staged_ui(),
        &paths.ui(),
        "install desktop application",
    )?;
    fs::write(paths.ui_version(), target_tag)
        .map_err(display_io("write desktop version marker"))?;
    Ok(())
}

fn restore_ui_backup(paths: &UpdatePaths, old_version: &str) -> Result<(), String> {
    // A consumed backup means restoration already ran (or backup never started).
    // Never move the installed binary again when resuming an interrupted rollback.
    if paths.backup_ui().exists() && paths.ui().exists() {
        if paths.staged_ui().exists() {
            fs::remove_file(paths.ui()).map_err(display_io("remove failed desktop application"))?;
        } else {
            // Return the candidate for retries without allocating another binary-sized copy.
            fs::create_dir_all(&paths.staging_dir)
                .map_err(display_io("create update staging directory"))?;
            rename_with_retry(
                &paths.ui(),
                &paths.staged_ui(),
                "preserve desktop application for retry",
            )?;
        }
    }
    if paths.backup_ui().exists() {
        rename_with_retry(
            &paths.backup_ui(),
            &paths.ui(),
            "restore desktop application",
        )?;
    }
    if !paths.ui().exists() && !old_version.is_empty() {
        return Err(
            "cannot restore desktop application: installed binary and backup are missing"
                .to_string(),
        );
    }
    if paths.ui_version().exists() {
        fs::remove_file(paths.ui_version()).map_err(display_io("remove failed version marker"))?;
    }
    if paths.backup_ui_version().exists() {
        rename_with_retry(
            &paths.backup_ui_version(),
            &paths.ui_version(),
            "restore desktop version marker",
        )?;
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
    let output = background_command(&python)
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
            background_command("uv")
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
    let mut pids = Vec::new();
    if cfg!(windows) {
        let escaped = root_text.replace('\'', "''");
        let script = format!(
            "$root='{escaped}'; $self={current_pid}; Get-CimInstance Win32_Process | Where-Object {{ $_.ProcessId -ne $self -and $_.Name -notlike 'suzent-installer*' -and (($_.ExecutablePath -like \"$root*\") -or ($_.CommandLine -like \"*$root*\")) }} | ForEach-Object {{ $_.ProcessId; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}"
        );
        let output = background_command("powershell")
            .args(["-NoProfile", "-Command", &script])
            .output()
            .map_err(|error| format!("failed to inspect running Suzent processes: {error}"))?;
        if !output.status.success() {
            return Err(format!(
                "failed to stop running Suzent processes{}",
                command_failure_detail(&output.stdout, &output.stderr)
                    .map(|detail| format!(": {detail}"))
                    .unwrap_or_default()
            ));
        }
        pids.extend(parse_pids(&output.stdout));
    } else {
        let output = background_command("ps")
            .args(["-axo", "pid=,command="])
            .output()
            .map_err(|error| format!("failed to inspect Suzent processes: {error}"))?;
        if !output.status.success() {
            return Err("failed to inspect Suzent processes".into());
        }
        for line in String::from_utf8_lossy(&output.stdout).lines() {
            let line = line.trim();
            if let Some((pid, command)) = line.split_once(char::is_whitespace) {
                if let Ok(pid) = pid.parse::<u32>() {
                    if pid != current_pid && is_unix_install_process(command.trim(), root) {
                        pids.push(pid);
                        let _ = background_command("kill")
                            .args(["-TERM", &pid.to_string()])
                            .status();
                    }
                }
            }
        }
    }
    wait_for_processes_exit(&pids, Duration::from_secs(15))
}

fn is_unix_install_process(command: &str, root: &Path) -> bool {
    let ui = root.join("bin/suzent-ui");
    let python = root.join(".venv/bin/python");
    if let Some(rest) = command.strip_prefix(ui.to_string_lossy().as_ref()) {
        return rest.is_empty() || rest.starts_with(char::is_whitespace);
    }
    if let Some(rest) = command.strip_prefix(python.to_string_lossy().as_ref()) {
        let boundary = rest.find(char::is_whitespace).unwrap_or(rest.len());
        let (suffix, arguments) = rest.split_at(boundary);
        if !suffix.chars().all(|ch| ch.is_ascii_digit() || ch == '.') {
            return false;
        }
        let args: Vec<_> = arguments.split_whitespace().collect();
        return args.starts_with(&["-m", "suzent.server"])
            || (args.starts_with(&["-m", "suzent.cli"])
                && args
                    .get(2)
                    .is_some_and(|action| matches!(*action, "serve" | "start" | "web")));
    }
    false
}

fn parse_pids(output: &[u8]) -> Vec<u32> {
    String::from_utf8_lossy(output)
        .lines()
        .filter_map(|line| line.trim().parse().ok())
        .collect()
}

fn wait_for_process_exit(pid: u32, timeout: Duration) -> Result<(), String> {
    let started = Instant::now();
    while process_exists(pid) {
        if started.elapsed() >= timeout {
            return Err(format!(
                "process {pid} did not exit within {} seconds; close it and retry",
                timeout.as_secs()
            ));
        }
        thread::sleep(Duration::from_millis(200));
    }
    Ok(())
}

fn wait_for_processes_exit(pids: &[u32], timeout: Duration) -> Result<(), String> {
    let started = Instant::now();
    loop {
        let running: Vec<_> = pids
            .iter()
            .copied()
            .filter(|pid| process_exists(*pid))
            .collect();
        if running.is_empty() {
            return Ok(());
        }
        if started.elapsed() >= timeout {
            return Err(format!(
                "Suzent processes are still running after {} seconds (PIDs: {}); close them and retry",
                timeout.as_secs(),
                running
                    .iter()
                    .map(u32::to_string)
                    .collect::<Vec<_>>()
                    .join(", ")
            ));
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
    background_command("kill")
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
        rename_with_retry(&temporary, destination, "finish downloaded asset")
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

fn release_checksum(tag: &str, asset_name: &str) -> Result<String, String> {
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
    parse_release_checksum(&checksums, asset_name)
}

fn verify_asset_checksum(path: &Path, expected: &str) -> Result<(), String> {
    let bytes = fs::read(path).map_err(display_io("read downloaded asset"))?;
    let actual = format!("{:x}", Sha256::digest(bytes));
    if actual != expected {
        return Err(format!(
            "checksum mismatch for {}: expected {expected}, found {actual}",
            path.display()
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

/// Records why an update stopped so the UI shows the real reason instead of the
/// last progress message. Terminal statuses written by the rollback path win.
fn record_failure(paths: &UpdatePaths, tag: &str, error: &str) {
    let previous = fs::read(&paths.status)
        .ok()
        .and_then(|bytes| serde_json::from_slice::<UpdateStatus>(&bytes).ok())
        .filter(|status| status.target_version == tag);
    if previous
        .as_ref()
        .is_some_and(|status| is_terminal_phase(&status.phase))
    {
        return;
    }
    let (phase, progress) = previous
        .as_ref()
        .map(|status| (status.phase.clone(), status.progress))
        .unwrap_or_else(|| ("preflight".to_string(), 0));
    let _ = write_status_details(paths, &phase, progress, error, tag, None, None, true);
}

fn is_terminal_phase(phase: &str) -> bool {
    matches!(phase, "complete" | "rolled_back" | "repair_required")
}

fn write_status(
    paths: &UpdatePaths,
    phase: &str,
    progress: u8,
    message: &str,
    tag: &str,
) -> Result<(), String> {
    println!("[{progress:>3}%] {message}");
    write_status_details(paths, phase, progress, message, tag, None, None, false)
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
        false,
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
    failed: bool,
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
        failed,
        warnings: if phase == "preflight" {
            Vec::new()
        } else {
            same_transaction
                .map(|status| status.warnings.clone())
                .unwrap_or_default()
        },
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
    let mut file = fs::File::create(&temporary).map_err(display_io(action))?;
    file.write_all(&bytes).map_err(display_io(action))?;
    file.sync_all().map_err(display_io(action))?;
    drop(file);
    replace_state_file(&temporary, path).map_err(display_io(action))?;
    Ok(())
}

#[cfg(not(windows))]
fn replace_state_file(source: &Path, destination: &Path) -> io::Result<()> {
    fs::rename(source, destination)?;
    fs::File::open(destination.parent().expect("state file parent"))?.sync_all()
}

#[cfg(windows)]
fn replace_state_file(source: &Path, destination: &Path) -> io::Result<()> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{
        MoveFileExW, MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH,
    };
    let source: Vec<u16> = source.as_os_str().encode_wide().chain(Some(0)).collect();
    let destination: Vec<u16> = destination
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect();
    // Both files are on the same volume; never remove the previous journal first.
    if unsafe {
        MoveFileExW(
            source.as_ptr(),
            destination.as_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

fn recover_legacy_journal(paths: &UpdatePaths) -> Result<(), String> {
    let backup = paths.journal.with_extension("bak");
    if !backup.exists() {
        return Ok(());
    }
    let authoritative = if paths.journal.exists() {
        &paths.journal
    } else {
        &backup
    };
    let bytes = fs::read(authoritative).map_err(display_io("read legacy transaction"))?;
    serde_json::from_slice::<UpdateTransaction>(&bytes).map_err(|error| {
        format!("invalid legacy transaction; preserve files and repair manually: {error}")
    })?;
    if !paths.journal.exists() {
        replace_state_file(&backup, &paths.journal)
            .map_err(display_io("restore legacy transaction"))?;
    } else {
        fs::remove_file(backup).map_err(display_io("remove superseded transaction"))?;
    }
    Ok(())
}

fn rename_with_retry(source: &Path, destination: &Path, action: &str) -> Result<(), String> {
    let mut delay = Duration::from_millis(150);
    let mut last_error = None;
    for attempt in 1..=5 {
        match fs::rename(source, destination) {
            Ok(()) => return Ok(()),
            Err(error)
                if attempt < 5
                    && matches!(
                        error.kind(),
                        io::ErrorKind::PermissionDenied | io::ErrorKind::WouldBlock
                    ) =>
            {
                last_error = Some(error);
                thread::sleep(delay);
                delay = delay.saturating_mul(2);
            }
            Err(error) => return Err(format!("failed to {action}: {error}")),
        }
    }
    Err(format!(
        "failed to {action} after 5 attempts: {}",
        last_error.expect("retry loop records an error")
    ))
}

fn cleanup_transaction_files(paths: &UpdatePaths) {
    let _ = fs::remove_file(&paths.journal);
    let _ = fs::remove_dir_all(&paths.staging_dir);
    let _ = fs::remove_dir_all(&paths.backup_dir);
}

fn repository_hazard(root: &Path) -> Result<Option<String>, String> {
    let unmerged = git_text(root, &["diff", "--name-only", "--diff-filter=U"])?;
    if !unmerged.is_empty() {
        return Ok(Some(format!(
            "unresolved conflicts: {}",
            unmerged.lines().collect::<Vec<_>>().join(", ")
        )));
    }

    for (name, marker) in [
        ("merge", "MERGE_HEAD"),
        ("rebase", "rebase-merge"),
        ("rebase", "rebase-apply"),
        ("cherry-pick", "CHERRY_PICK_HEAD"),
        ("revert", "REVERT_HEAD"),
    ] {
        let marker_path = PathBuf::from(git_text(root, &["rev-parse", "--git-path", marker])?);
        let marker_path = if marker_path.is_absolute() {
            marker_path
        } else {
            root.join(marker_path)
        };
        if marker_path.exists() {
            return Ok(Some(format!("Git {name} in progress")));
        }
    }
    Ok(None)
}

fn preserve_conflicted_checkout(
    root: &Path,
    recovery_dir: &Path,
    reason: &str,
    old_commit: &str,
    old_branch: &str,
) -> Result<(), String> {
    if !git_bytes(root, &["ls-files", "-z", "--", ".suzent"])?.is_empty() {
        return Err(
            "The update state directory is tracked by Git; manual recovery is required".into(),
        );
    }
    if let Some(parent) = recovery_dir.parent() {
        fs::create_dir_all(parent).map_err(display_io("create recovery parent"))?;
    }
    fs::create_dir(recovery_dir).map_err(display_io("create unique update recovery directory"))?;

    let staged_patch = git_bytes(root, &["diff", "--cached", "--binary"])?;
    let unstaged_patch = git_bytes(root, &["diff", "--binary"])?;
    fs::write(recovery_dir.join("staged.patch"), staged_patch)
        .map_err(display_io("save staged changes"))?;
    fs::write(recovery_dir.join("unstaged.patch"), unstaged_patch)
        .map_err(display_io("save unstaged changes"))?;

    let mut tracked_files = git_paths(root, &["diff", "HEAD", "--name-only", "-z"])?;
    tracked_files.extend(git_paths(
        root,
        &["ls-files", "-z", "--modified", "--deleted"],
    )?);
    tracked_files.sort();
    tracked_files.dedup();
    for path in git_paths(root, &["diff", "-z", "--name-only", "--diff-filter=U"])? {
        if !tracked_files.contains(&path) {
            tracked_files.push(path);
        }
    }
    for relative in &tracked_files {
        let source = root.join(relative);
        if source.symlink_metadata().is_ok() {
            copy_recovery_file(&source, &recovery_dir.join("tracked").join(relative))?;
        }
    }

    let untracked_files = git_paths(root, &["ls-files", "-z", "--others", "--exclude-standard"])?;
    if tracked_files
        .iter()
        .chain(&untracked_files)
        .any(|path| path.to_str().is_none())
    {
        return Err(
            "Non-UTF-8 paths require manual conflict recovery; source was not changed".into(),
        );
    }
    for relative in &untracked_files {
        let source = root.join(relative);
        if source.symlink_metadata().is_ok() {
            let destination = recovery_dir.join("untracked").join(relative);
            if let Some(parent) = destination.parent() {
                fs::create_dir_all(parent)
                    .map_err(display_io("prepare untracked recovery path"))?;
            }
            copy_recovery_file(&source, &destination)?;
        }
    }

    let conflict_stages = preserve_conflict_stages(root, recovery_dir)?;
    for marker in [
        "HEAD",
        "index",
        "ORIG_HEAD",
        "MERGE_HEAD",
        "MERGE_MSG",
        "MERGE_MODE",
        "AUTO_MERGE",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "REBASE_HEAD",
        "rebase-merge",
        "rebase-apply",
        "sequencer",
    ] {
        let source = git_metadata_path(root, marker)?;
        if source.symlink_metadata().is_ok() {
            copy_recovery_tree(&source, &recovery_dir.join("git-state").join(marker))?;
        }
    }
    let recovery_ref = format!(
        "refs/suzent-recovery/{}",
        recovery_dir
            .file_name()
            .ok_or("missing recovery name")?
            .to_string_lossy()
    );
    run_checked(
        background_command("git")
            .args(["update-ref", &recovery_ref, old_commit])
            .current_dir(root),
        "retain original commit",
    )?;
    for name in ["ORIG_HEAD", "REBASE_HEAD", "MERGE_HEAD"] {
        if let Ok(commit) = git_text(
            root,
            &["rev-parse", "--verify", &format!("{name}^{{commit}}")],
        ) {
            run_checked(
                background_command("git")
                    .args(["update-ref", &format!("{recovery_ref}-{name}"), &commit])
                    .current_dir(root),
                "retain operation commit",
            )?;
        }
    }
    let manifest = RecoveryManifest {
        created_at: now_epoch_millis(),
        reason: reason.to_string(),
        old_commit: old_commit.to_string(),
        old_branch: old_branch.to_string(),
        tracked_files: display_paths(&tracked_files),
        untracked_files: display_paths(&untracked_files),
        conflict_stages,
    };
    write_json_atomic(
        &recovery_dir.join("manifest.json"),
        &manifest,
        "write recovery manifest",
    )?;

    fs::write(recovery_dir.join("README.txt"), format!("Original commit: {old_commit}\nOriginal branch: {old_branch}\nRecovery ref: {recovery_ref}\ntracked/ and untracked/ contain original working files; git-state/ contains the index and Git operation state; manifest.json lists paths, including deleted files. Do not apply these files to a running installation. Git state is a diagnostic recovery snapshot, not a portable automatic restore. Keep this directory until local changes have been recovered. Databases and ignored user data are not rolled back.\n")).map_err(display_io("write recovery instructions"))?;
    Ok(())
}

fn git_metadata_path(root: &Path, marker: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(git_text(root, &["rev-parse", "--git-path", marker])?);
    Ok(if path.is_absolute() {
        path
    } else {
        root.join(path)
    })
}

fn copy_recovery_tree(source: &Path, destination: &Path) -> Result<(), String> {
    let metadata =
        fs::symlink_metadata(source).map_err(display_io("inspect Git operation state"))?;
    if metadata.is_dir() {
        fs::create_dir_all(destination).map_err(display_io("prepare Git state backup"))?;
        for entry in fs::read_dir(source).map_err(display_io("read Git operation state"))? {
            let entry = entry.map_err(display_io("read Git state entry"))?;
            copy_recovery_tree(&entry.path(), &destination.join(entry.file_name()))?;
        }
        Ok(())
    } else {
        copy_recovery_file(source, destination)
    }
}

fn clear_preserved_conflicts(
    root: &Path,
    recovery_dir: &Path,
    old_commit: &str,
) -> Result<(), String> {
    if !recovery_dir.join("manifest.json").is_file()
        || !recovery_dir.join("git-state/index").is_file()
    {
        return Err("Verified conflict backup is missing; checkout was not changed".into());
    }
    let manifest: RecoveryManifest = serde_json::from_slice(
        &fs::read(recovery_dir.join("manifest.json"))
            .map_err(display_io("read recovery manifest"))?,
    )
    .map_err(|error| error.to_string())?;
    let mut current_tracked = git_paths(root, &["diff", "HEAD", "--name-only", "-z"])?;
    current_tracked.extend(git_paths(
        root,
        &["ls-files", "-z", "--modified", "--deleted"],
    )?);
    current_tracked.sort();
    current_tracked.dedup();
    if display_paths(&current_tracked) != manifest.tracked_files
        || display_paths(&git_paths(
            root,
            &["ls-files", "-z", "--others", "--exclude-standard"],
        )?) != manifest.untracked_files
    {
        return Err("Changed paths differ from the backup; no conflict cleanup performed".into());
    }
    for (folder, paths) in [
        ("tracked", &manifest.tracked_files),
        ("untracked", &manifest.untracked_files),
    ] {
        for path in paths {
            let relative = validated_git_path(path.as_bytes())?;
            let original = root.join(&relative);
            let saved = recovery_dir.join(folder).join(&relative);
            if original.symlink_metadata().is_ok() || saved.exists() {
                if !fs::symlink_metadata(&original)
                    .map_err(display_io("verify source type"))?
                    .file_type()
                    .is_file()
                {
                    return Err(
                        "Source file type changed after backup; no conflict cleanup performed"
                            .into(),
                    );
                }
                if fs::read(&original).map_err(display_io("verify current source"))?
                    != fs::read(&saved).map_err(display_io("verify saved source"))?
                {
                    return Err("Source changed after backup; no conflict cleanup performed".into());
                }
            }
        }
    }
    if fs::read(git_metadata_path(root, "index")?).map_err(display_io("verify current index"))?
        != fs::read(recovery_dir.join("git-state/index"))
            .map_err(display_io("verify saved index"))?
        || git_text(root, &["rev-parse", "HEAD"])? != old_commit
    {
        return Err("Git state changed after backup; no conflict cleanup performed".into());
    }
    for (marker, operation) in [
        ("rebase-merge", "rebase"),
        ("rebase-apply", "rebase"),
        ("sequencer", "cherry-pick"),
        ("CHERRY_PICK_HEAD", "cherry-pick"),
        ("REVERT_HEAD", "revert"),
    ] {
        if git_metadata_path(root, marker)?.exists() {
            run_checked(
                background_command("git")
                    .args([operation, "--quit"])
                    .current_dir(root),
                "quit preserved Git operation",
            )?;
        }
    }
    // Unlike --hard, --merge refuses to overwrite obstructing untracked files.
    run_checked(
        background_command("git")
            .args(["reset", "--merge", old_commit])
            .current_dir(root),
        "clear preserved conflict index",
    )?;
    run_checked(
        background_command("git")
            .args([
                "restore",
                "--source",
                old_commit,
                "--staged",
                "--worktree",
                "--",
                ".",
            ])
            .current_dir(root),
        "restore preserved tracked source",
    )?;
    // Untracked and ignored files stay in place. A target collision stops checkout.
    Ok(())
}

fn preserve_conflict_stages(root: &Path, recovery_dir: &Path) -> Result<Vec<String>, String> {
    let entries = git_bytes(root, &["ls-files", "-u", "-z"])?;
    let mut saved = Vec::new();
    for entry in entries
        .split(|byte| *byte == 0)
        .filter(|entry| !entry.is_empty())
    {
        let Some(tab) = entry.iter().position(|byte| *byte == b'\t') else {
            return Err("invalid unmerged index entry from Git".to_string());
        };
        let metadata = String::from_utf8_lossy(&entry[..tab]);
        let fields: Vec<_> = metadata.split_whitespace().collect();
        if fields.len() != 3 {
            return Err("invalid unmerged index metadata from Git".to_string());
        }
        let relative = validated_git_path(&entry[tab + 1..])?;
        let stage = fields[2];
        let blob = git_bytes(root, &["cat-file", "blob", fields[1]])?;
        let destination = recovery_dir
            .join("conflict-stages")
            .join(stage)
            .join(&relative);
        if let Some(parent) = destination.parent() {
            fs::create_dir_all(parent)
                .map_err(display_io("prepare conflict-stage recovery path"))?;
        }
        fs::write(&destination, blob).map_err(display_io("save conflict-stage content"))?;
        saved.push(format!("{stage}:{}", relative.display()));
    }
    Ok(saved)
}

fn copy_recovery_file(source: &Path, destination: &Path) -> Result<(), String> {
    let metadata = fs::symlink_metadata(source).map_err(display_io("inspect recovery file"))?;
    if !metadata.file_type().is_file() {
        return Err(format!(
            "cannot safely preserve non-regular path {}; resolve it manually",
            source.display()
        ));
    }
    if let Some(parent) = destination.parent() {
        fs::create_dir_all(parent).map_err(display_io("prepare recovery path"))?;
    }
    fs::copy(source, destination).map_err(display_io("copy file into recovery"))?;
    let original = fs::read(source).map_err(display_io("verify original recovery file"))?;
    let saved = fs::read(destination).map_err(display_io("verify recovery copy"))?;
    if original != saved {
        return Err(format!(
            "Recovery verification failed: {}",
            source.display()
        ));
    }
    OpenOptions::new()
        .write(true)
        .open(destination)
        .and_then(|file| file.sync_all())
        .map_err(display_io("flush recovery copy"))?;
    Ok(())
}

fn git_paths(root: &Path, args: &[&str]) -> Result<Vec<PathBuf>, String> {
    let paths: Vec<_> = git_bytes(root, args)?
        .split(|byte| *byte == 0)
        .filter(|entry| !entry.is_empty())
        .map(validated_git_path)
        .collect::<Result<_, _>>()?;
    Ok(paths
        .into_iter()
        .filter(|path| {
            path.components()
                .next()
                .is_none_or(|part| part.as_os_str() != ".suzent")
        })
        .collect())
}

fn validated_git_path(bytes: &[u8]) -> Result<PathBuf, String> {
    let path = git_path_from_bytes(bytes)?;
    if path.is_absolute()
        || path
            .components()
            .any(|component| !matches!(component, std::path::Component::Normal(_)))
    {
        return Err(format!("Git returned an unsafe path: {}", path.display()));
    }
    Ok(path)
}

#[cfg(unix)]
fn git_path_from_bytes(bytes: &[u8]) -> Result<PathBuf, String> {
    use std::ffi::OsString;
    use std::os::unix::ffi::OsStringExt;
    Ok(PathBuf::from(OsString::from_vec(bytes.to_vec())))
}

#[cfg(not(unix))]
fn git_path_from_bytes(bytes: &[u8]) -> Result<PathBuf, String> {
    String::from_utf8(bytes.to_vec())
        .map(PathBuf::from)
        .map_err(|_| "Git returned a path that is not valid UTF-8".to_string())
}

fn display_paths(paths: &[PathBuf]) -> Vec<String> {
    paths
        .iter()
        .map(|path| path.to_string_lossy().into_owned())
        .collect()
}

fn has_local_changes(root: &Path) -> Result<bool, String> {
    Ok(!git_text(root, &["status", "--porcelain"])?
        .trim()
        .is_empty())
}

fn git_text(root: &Path, args: &[&str]) -> Result<String, String> {
    let output = git_output(root, args)?;
    Ok(String::from_utf8_lossy(&output).trim().to_string())
}

fn git_bytes(root: &Path, args: &[&str]) -> Result<Vec<u8>, String> {
    git_output(root, args)
}

fn git_output(root: &Path, args: &[&str]) -> Result<Vec<u8>, String> {
    let output = background_command("git")
        .args(args)
        .current_dir(root)
        .output()
        .map_err(|error| format!("failed to run git {}: {error}", args.join(" ")))?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_string());
    }
    Ok(output.stdout)
}

fn run_checked(command: &mut Command, action: &str) -> Result<(), String> {
    let output = command
        .output()
        .map_err(|error| format!("failed to {action}: {error}"))?;
    if output.status.success() {
        return Ok(());
    }
    let code = output.status.code().unwrap_or(1);
    match command_failure_detail(&output.stdout, &output.stderr) {
        Some(detail) => Err(format!("failed to {action} (exit {code}): {detail}")),
        None => Err(format!("failed to {action} (exit {code})")),
    }
}

/// Collapses a failed command's stderr (or stdout when stderr is empty) into a
/// single line so the reason survives into `update-status.json` and the UI.
fn command_failure_detail(stdout: &[u8], stderr: &[u8]) -> Option<String> {
    let stderr = String::from_utf8_lossy(stderr);
    let stdout = String::from_utf8_lossy(stdout);
    let source = if stderr.trim().is_empty() {
        stdout
    } else {
        stderr
    };
    let mut detail = source
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .collect::<Vec<_>>()
        .join("; ");
    if detail.is_empty() {
        return None;
    }
    if detail.chars().count() > FAILURE_DETAIL_LIMIT {
        detail = detail
            .chars()
            .take(FAILURE_DETAIL_LIMIT)
            .collect::<String>()
            + "\u{2026}";
    }
    Some(detail)
}

fn launch_app(executable: &Path, root: &Path) -> Result<(), String> {
    background_command(executable)
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
    use super::background_command;
    use super::{
        acquire_lock, backup_current_ui, command_failure_detail, is_release_tag, parse_pids,
        parse_release_checksum, record_failure, restore_ui_backup, wait_for_process_exit,
        write_download_status, write_status, UpdatePaths, UpdateStatus, UpdateTransaction,
        FAILURE_DETAIL_LIMIT,
    };
    use std::fs;
    use std::thread;
    use std::time::Duration;

    #[test]
    fn atomic_state_replacement_keeps_previous_document_until_commit() {
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("state.json");
        super::write_json_atomic(&path, &"old", "test").unwrap();
        fs::write(path.with_extension("tmp"), b"partial").unwrap();
        assert_eq!(fs::read_to_string(&path).unwrap(), "\"old\"");
        super::write_json_atomic(&path, &"new", "test").unwrap();
        assert_eq!(fs::read_to_string(&path).unwrap(), "\"new\"");
        assert!(!path.with_extension("bak").exists());
        assert!(!path.with_extension("tmp").exists());
        assert!(super::replace_state_file(&temp.path().join("missing"), &path).is_err());
        assert_eq!(fs::read_to_string(&path).unwrap(), "\"new\"");
    }

    #[test]
    fn legacy_journal_gap_is_recovered_without_trusting_partial_temp() {
        let temp = tempfile::tempdir().unwrap();
        let paths = UpdatePaths::new(temp.path().to_path_buf(), "v1.2.3");
        fs::create_dir_all(&paths.state_dir).unwrap();
        let journal = serde_json::json!({
            "target_tag": "v1.2.3", "old_commit": "abc", "old_branch": "",
            "old_release_tag": "v1.2.2", "old_ui_version": "v1.2.2",
            "stashed_changes": false, "phase": "switching"
        });
        let bytes = serde_json::to_vec(&journal).unwrap();
        fs::write(paths.journal.with_extension("bak"), &bytes).unwrap();
        fs::write(paths.journal.with_extension("tmp"), b"partial").unwrap();
        super::recover_legacy_journal(&paths).unwrap();
        assert_eq!(fs::read(&paths.journal).unwrap(), bytes);
        assert!(!paths.journal.with_extension("bak").exists());
        fs::write(paths.journal.with_extension("bak"), b"stale").unwrap();
        super::recover_legacy_journal(&paths).unwrap();
        assert!(!paths.journal.with_extension("bak").exists());
        fs::remove_file(&paths.journal).unwrap();
        fs::write(paths.journal.with_extension("bak"), b"corrupt").unwrap();
        assert!(super::recover_legacy_journal(&paths).is_err());
        assert!(paths.journal.with_extension("bak").exists());
    }

    #[test]
    fn completed_transaction_recovery_keeps_verified_installation() {
        let temp = tempfile::tempdir().unwrap();
        let paths = UpdatePaths::new(temp.path().to_path_buf(), "v1.2.3");
        fs::create_dir_all(&paths.state_dir).unwrap();
        fs::create_dir_all(paths.root.join("bin")).unwrap();
        fs::write(paths.ui(), "verified-new-ui").unwrap();
        let journal = serde_json::json!({
            "target_tag": "v1.2.3", "old_commit": "abc", "old_branch": "",
            "old_release_tag": "v1.2.2", "old_ui_version": "v1.2.2",
            "stashed_changes": false, "phase": "complete"
        });
        fs::write(&paths.journal, serde_json::to_vec(&journal).unwrap()).unwrap();
        // No Git repository or Python exists: completed recovery must not run rollback.
        super::recover_interrupted_update(&paths).unwrap();
        assert_eq!(fs::read_to_string(paths.ui()).unwrap(), "verified-new-ui");
        assert!(!paths.journal.exists());
    }

    #[cfg(windows)]
    #[test]
    fn background_process_has_no_console_and_keeps_diagnostics() {
        let output = background_command("powershell.exe")
            .args([
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Add-Type -Name ConsoleProbe -Namespace Suzent -MemberDefinition '[DllImport(\"kernel32.dll\")] public static extern System.IntPtr GetConsoleWindow();'; [Console]::Out.WriteLine([Suzent.ConsoleProbe]::GetConsoleWindow().ToInt64()); [Console]::Error.WriteLine('diagnostic'); exit 7",
            ])
            .output()
            .unwrap();
        assert_eq!(output.status.code(), Some(7));
        assert_eq!(String::from_utf8_lossy(&output.stdout).trim(), "0");
        assert!(String::from_utf8_lossy(&output.stderr).contains("diagnostic"));
    }

    #[test]
    fn reuses_download_after_install_and_rollback() {
        let temp = tempfile::tempdir().unwrap();
        let paths = UpdatePaths::new(temp.path().to_path_buf(), "v1.2.3");
        fs::create_dir_all(&paths.staging_dir).unwrap();
        fs::create_dir_all(paths.root.join("bin")).unwrap();
        fs::write(paths.ui(), b"old-ui").unwrap();
        let expected = format!("{:x}", <sha2::Sha256 as sha2::Digest>::digest(b"new-ui"));
        super::prepare_ui(&paths, &expected, || {
            fs::write(paths.staged_ui(), b"new-ui").unwrap();
            Ok(())
        })
        .unwrap();
        backup_current_ui(&paths).unwrap();
        super::install_staged_ui(&paths, "v1.2.3").unwrap();
        assert!(!paths.staged_ui().exists());
        assert_eq!(fs::read(paths.ui()).unwrap(), b"new-ui");
        restore_ui_backup(&paths, "v1.2.2").unwrap();
        assert_eq!(fs::read(paths.ui()).unwrap(), b"old-ui");
        super::prepare_ui(&paths, &expected, || panic!("downloaded again")).unwrap();
        assert_eq!(fs::read(paths.staged_ui()).unwrap(), b"new-ui");
    }

    #[test]
    fn rollback_before_install_preserves_staged_download() {
        let temp = tempfile::tempdir().unwrap();
        let paths = UpdatePaths::new(temp.path().to_path_buf(), "v1.2.3");
        fs::create_dir_all(&paths.staging_dir).unwrap();
        fs::create_dir_all(paths.root.join("bin")).unwrap();
        fs::write(paths.ui(), b"old-ui").unwrap();
        fs::write(paths.staged_ui(), b"new-ui").unwrap();
        backup_current_ui(&paths).unwrap();
        restore_ui_backup(&paths, "v1.2.2").unwrap();
        assert_eq!(fs::read(paths.ui()).unwrap(), b"old-ui");
        assert_eq!(fs::read(paths.staged_ui()).unwrap(), b"new-ui");
    }

    #[test]
    fn repeated_rollback_preserves_restored_binary_and_candidate() {
        for interrupted_before_marker in [false, true] {
            let temp = tempfile::tempdir().unwrap();
            let paths = UpdatePaths::new(temp.path().to_path_buf(), "v1.2.3");
            fs::create_dir_all(paths.root.join("bin")).unwrap();
            fs::create_dir_all(&paths.staging_dir).unwrap();
            fs::write(paths.ui(), b"old-ui").unwrap();
            fs::write(paths.ui_version(), "v1.2.2").unwrap();
            backup_current_ui(&paths).unwrap();
            fs::write(paths.staged_ui(), b"new-ui").unwrap();
            super::install_staged_ui(&paths, "v1.2.3").unwrap();
            if interrupted_before_marker {
                fs::rename(paths.ui(), paths.staged_ui()).unwrap();
                fs::rename(paths.backup_ui(), paths.ui()).unwrap();
            } else {
                restore_ui_backup(&paths, "v1.2.2").unwrap();
            }
            for _ in 0..2 {
                restore_ui_backup(&paths, "v1.2.2").unwrap();
                assert_eq!(fs::read(paths.ui()).unwrap(), b"old-ui");
                assert_eq!(fs::read(paths.staged_ui()).unwrap(), b"new-ui");
                assert_eq!(fs::read_to_string(paths.ui_version()).unwrap(), "v1.2.2");
            }
        }
    }

    #[test]
    fn rollback_without_backup_keeps_existing_binary() {
        let temp = tempfile::tempdir().unwrap();
        let paths = UpdatePaths::new(temp.path().to_path_buf(), "v1.2.3");
        fs::create_dir_all(paths.root.join("bin")).unwrap();
        fs::write(paths.ui(), b"old-ui").unwrap();
        restore_ui_backup(&paths, "v1.2.2").unwrap();
        assert_eq!(fs::read(paths.ui()).unwrap(), b"old-ui");
        assert!(!paths.staged_ui().exists());
        fs::remove_file(paths.ui()).unwrap();
        assert!(restore_ui_backup(&paths, "v1.2.2").is_err());
    }

    #[test]
    fn reuses_installed_binary_after_successful_cleanup() {
        let temp = tempfile::tempdir().unwrap();
        let paths = UpdatePaths::new(temp.path().to_path_buf(), "v1.2.3");
        fs::create_dir_all(&paths.staging_dir).unwrap();
        fs::write(paths.staged_ui(), b"new-ui").unwrap();
        let expected = format!("{:x}", <sha2::Sha256 as sha2::Digest>::digest(b"new-ui"));
        super::install_staged_ui(&paths, "v1.2.3").unwrap();
        super::cleanup_transaction_files(&paths);
        fs::create_dir_all(&paths.staging_dir).unwrap();
        super::prepare_ui(&paths, &expected, || panic!("downloaded installed binary")).unwrap();
        assert_eq!(fs::read(paths.staged_ui()).unwrap(), b"new-ui");
    }

    #[test]
    fn replaces_invalid_binary_and_rejects_corrupt_downloads() {
        let temp = tempfile::tempdir().unwrap();
        let paths = UpdatePaths::new(temp.path().to_path_buf(), "v1.2.3");
        fs::create_dir_all(&paths.staging_dir).unwrap();
        fs::write(paths.staged_ui(), b"partial").unwrap();
        let expected = format!("{:x}", <sha2::Sha256 as sha2::Digest>::digest(b"new-ui"));
        assert!(super::prepare_ui(&paths, &expected, || {
            fs::write(paths.staged_ui(), b"corrupt").unwrap();
            Ok(())
        })
        .is_err());
        super::prepare_ui(&paths, &expected, || {
            fs::write(paths.staged_ui(), b"new-ui").unwrap();
            Ok(())
        })
        .unwrap();
        super::prepare_ui(&paths, &expected, || panic!("downloaded again")).unwrap();
    }

    #[test]
    fn shortcut_warning_survives_completion_but_not_a_new_attempt() {
        let temp = tempfile::tempdir().unwrap();
        let paths = UpdatePaths::new(temp.path().to_path_buf(), "v1.2.3");
        fs::create_dir_all(&paths.state_dir).unwrap();
        super::write_status(&paths, "shortcuts", 96, "Shortcuts", "v1.2.3").unwrap();
        let mut status: super::UpdateStatus =
            serde_json::from_slice(&fs::read(&paths.status).unwrap()).unwrap();
        status.warnings.push("Shortcut access denied".into());
        super::write_json_atomic(&paths.status, &status, "test warning").unwrap();
        super::write_status(&paths, "complete", 100, "Done", "v1.2.3").unwrap();
        let completed: super::UpdateStatus =
            serde_json::from_slice(&fs::read(&paths.status).unwrap()).unwrap();
        assert_eq!(completed.warnings, vec!["Shortcut access denied"]);
        super::write_status(&paths, "preflight", 0, "Retry", "v1.2.3").unwrap();
        let retry: super::UpdateStatus =
            serde_json::from_slice(&fs::read(&paths.status).unwrap()).unwrap();
        assert!(retry.warnings.is_empty());
    }

    #[test]
    fn reports_command_stderr_as_failure_detail() {
        let stderr = b"From https://github.com/cyzus/suzent\n ! [rejected] v0.9.0 (would clobber existing tag)\n";
        let detail = command_failure_detail(b"", stderr).expect("detail");
        assert_eq!(
            detail,
            "From https://github.com/cyzus/suzent; ! [rejected] v0.9.0 (would clobber existing tag)"
        );
    }

    #[test]
    fn falls_back_to_stdout_and_truncates_long_failure_detail() {
        assert_eq!(
            command_failure_detail(b"  only on stdout  ", b"   \n").expect("detail"),
            "only on stdout"
        );
        assert_eq!(command_failure_detail(b"", b""), None);

        let long = "x".repeat(FAILURE_DETAIL_LIMIT + 40);
        let detail = command_failure_detail(b"", long.as_bytes()).expect("detail");
        assert_eq!(detail.chars().count(), FAILURE_DETAIL_LIMIT + 1);
        assert!(detail.ends_with('\u{2026}'));
    }

    #[test]
    fn records_failure_reason_on_the_current_phase() {
        let temp = tempfile::tempdir().expect("temp dir");
        let paths = UpdatePaths::new(temp.path().to_path_buf(), "v1.2.3");
        fs::create_dir_all(&paths.state_dir).expect("state dir");
        write_status(&paths, "fetch", 25, "Fetching release source", "v1.2.3").expect("status");

        record_failure(
            &paths,
            "v1.2.3",
            "failed to fetch release source (exit 1): would clobber",
        );

        let status: UpdateStatus =
            serde_json::from_slice(&fs::read(&paths.status).expect("read")).expect("parse");
        assert_eq!(status.phase, "fetch");
        assert_eq!(status.progress, 25);
        assert!(status.failed);
        assert!(status.message.contains("would clobber"));
    }

    #[test]
    fn keeps_rollback_status_after_a_failure() {
        let temp = tempfile::tempdir().expect("temp dir");
        let paths = UpdatePaths::new(temp.path().to_path_buf(), "v1.2.3");
        fs::create_dir_all(&paths.state_dir).expect("state dir");
        write_status(
            &paths,
            "rolled_back",
            100,
            "Update failed; previous version restored",
            "v1.2.3",
        )
        .expect("status");

        record_failure(&paths, "v1.2.3", "failed to synchronize Python environment");

        let status: UpdateStatus =
            serde_json::from_slice(&fs::read(&paths.status).expect("read")).expect("parse");
        assert_eq!(status.phase, "rolled_back");
        assert!(!status.failed);
    }

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

    #[test]
    fn parses_only_valid_process_ids() {
        assert_eq!(parse_pids(b"123\r\nwarning\r\n456\r\n"), vec![123, 456]);
    }

    #[test]
    fn process_wait_reports_a_live_process_after_timeout() {
        let result = wait_for_process_exit(std::process::id(), Duration::ZERO);
        assert!(result.unwrap_err().contains("did not exit"));
    }

    #[test]
    fn reads_journals_written_before_exact_stash_and_target_tracking() {
        let transaction: UpdateTransaction = serde_json::from_str(
            r#"{
                "target_tag":"v1.2.3",
                "old_commit":"abc",
                "old_branch":"main",
                "old_release_tag":"v1.2.2",
                "old_ui_version":"v1.2.2",
                "stashed_changes":true,
                "phase":"switching"
            }"#,
        )
        .expect("legacy journal");

        assert_eq!(transaction.stash_commit, None);
        assert_eq!(transaction.recovery_dir, None);
        assert!(transaction.target_commit.is_empty());
    }

    #[test]
    fn detects_a_checkout_with_a_git_operation_in_progress() {
        let temp = tempfile::tempdir().expect("temp dir");
        assert!(background_command("git")
            .args(["init", "--quiet"])
            .current_dir(temp.path())
            .status()
            .expect("git init")
            .success());
        fs::write(temp.path().join(".git/MERGE_HEAD"), "deadbeef").expect("merge marker");

        let hazard = super::repository_hazard(temp.path())
            .expect("inspect repository")
            .expect("hazard");

        assert!(hazard.contains("Git merge in progress"));
    }

    #[test]
    fn conflict_snapshot_never_changes_the_checkout() {
        conflict_recovery_case("merge");
    }

    #[test]
    #[cfg(unix)]
    fn unix_process_matching_does_not_stop_terminals_or_other_installations() {
        let root = std::path::Path::new("/Users/test/Suzent folder");
        for command in [
            "/Users/test/Suzent folder/bin/suzent-ui",
            "/Users/test/Suzent folder/.venv/bin/python -m suzent.cli serve",
            "/Users/test/Suzent folder/.venv/bin/python3.12 -m suzent.cli serve",
        ] {
            assert!(super::is_unix_install_process(command, root));
        }
        for command in [
            "/bin/zsh -c cd /Users/test/Suzent folder",
            "/usr/bin/pgrep -f /Users/test/Suzent folder",
            "/Users/test/Suzent folder/apps/suzent-installer/target/debug/suzent-installer",
            "/Users/test/Suzent folder-other/.venv/bin/python",
            "/Users/test/Suzent folder/bin/suzent-ui-old",
            "/Users/test/Suzent folder/.venv/bin/python-helper",
        ] {
            assert!(!super::is_unix_install_process(command, root));
        }
    }

    #[test]
    fn rebase_conflict_can_be_preserved_and_cleared() {
        conflict_recovery_case("rebase");
    }

    #[test]
    fn cherry_pick_conflict_can_be_preserved_and_cleared() {
        conflict_recovery_case("cherry-pick");
    }

    fn conflict_recovery_case(operation: &str) {
        let temp = tempfile::tempdir().expect("temp dir");
        let root = temp.path();
        let git = |args: &[&str]| {
            background_command("git")
                .args(args)
                .current_dir(root)
                .status()
                .expect("run git")
        };
        assert!(git(&["init", "--quiet"]).success());
        assert!(git(&["config", "core.autocrlf", "false"]).success());
        assert!(git(&["config", "user.name", "Suzent Test"]).success());
        assert!(git(&["config", "user.email", "suzent@example.invalid"]).success());
        fs::write(root.join("conflicted.txt"), "base\n").expect("base file");
        assert!(git(&["add", "conflicted.txt"]).success());
        assert!(git(&["commit", "--quiet", "-m", "base"]).success());
        let base = super::git_text(root, &["rev-parse", "HEAD"]).expect("base commit");

        assert!(git(&["checkout", "--quiet", "-b", "incoming"]).success());
        fs::write(root.join("conflicted.txt"), "incoming\n").expect("incoming file");
        assert!(git(&["commit", "--quiet", "-am", "incoming"]).success());
        assert!(git(&["checkout", "--quiet", "-b", "installed", &base]).success());
        fs::write(root.join("conflicted.txt"), "installed\n").expect("installed file");
        assert!(git(&["commit", "--quiet", "-am", "installed"]).success());
        assert!(!git(&[operation, "incoming"]).success());
        let old_commit = super::git_text(root, &["rev-parse", "HEAD"]).expect("old commit");
        let old_content = super::git_bytes(root, &["show", "HEAD:conflicted.txt"]).unwrap();
        fs::write(root.join("staged-only.txt"), "staged content\n").unwrap();
        assert!(git(&["add", "staged-only.txt"]).success());
        fs::write(root.join(".git/info/exclude"), ".env\n.suzent/\n").unwrap();
        fs::write(root.join(".env"), "PRIVATE=keep\n").unwrap();
        fs::write(root.join("local-note.txt"), "keep me\n").expect("untracked file");
        let conflicted = fs::read(root.join("conflicted.txt")).unwrap();
        let index = fs::read(root.join(".git/index")).unwrap();

        let recovery = root.join(".suzent/update-recovery/test");
        super::preserve_conflicted_checkout(
            root,
            &recovery,
            "test conflict",
            &old_commit,
            "installed",
        )
        .expect("verified snapshot");

        assert_eq!(fs::read(root.join("conflicted.txt")).unwrap(), conflicted);
        assert_eq!(fs::read(root.join(".git/index")).unwrap(), index);
        assert!(super::repository_hazard(root).unwrap().is_some());
        assert_eq!(
            fs::read_to_string(root.join("local-note.txt")).unwrap(),
            "keep me\n"
        );
        assert_eq!(
            fs::read_to_string(recovery.join("untracked/local-note.txt"))
                .expect("recovered untracked file"),
            "keep me\n"
        );
        assert!(recovery.join("tracked/conflicted.txt").exists());
        assert!(recovery.join("conflict-stages/1/conflicted.txt").exists());
        assert!(recovery.join("conflict-stages/2/conflicted.txt").exists());
        assert!(recovery.join("conflict-stages/3/conflicted.txt").exists());
        assert!(recovery.join("manifest.json").exists());
        assert_eq!(fs::read(recovery.join("git-state/index")).unwrap(), index);
        assert_eq!(
            fs::read(recovery.join("tracked/staged-only.txt")).unwrap(),
            b"staged content\n"
        );
        assert!(super::repository_hazard(root)
            .expect("inspect recovered repository")
            .is_some());

        // A failed snapshot must leave originals untouched as well.
        let failed = root.join(".suzent/update-recovery/failed");
        fs::create_dir_all(failed.join("untracked/local-note.txt")).unwrap();
        assert!(super::preserve_conflicted_checkout(
            root,
            &failed,
            "conflict",
            &old_commit,
            "installed"
        )
        .is_err());
        assert_eq!(fs::read(root.join("conflicted.txt")).unwrap(), conflicted);
        assert_eq!(fs::read(root.join(".git/index")).unwrap(), index);
        assert_eq!(
            fs::read_to_string(root.join("local-note.txt")).unwrap(),
            "keep me\n"
        );
        fs::write(root.join("local-note.txt"), "changed after snapshot\n").unwrap();
        assert!(super::clear_preserved_conflicts(root, &recovery, &old_commit).is_err());
        assert_eq!(fs::read(root.join(".git/index")).unwrap(), index);
        fs::write(root.join("local-note.txt"), "keep me\n").unwrap();
        let paths = super::UpdatePaths::new(root.to_path_buf(), "v1.2.3");
        assert!(super::run_transaction(&paths, "v1.2.3", false)
            .unwrap_err()
            .starts_with("CONFIRM_GIT_RECOVERY:"));
        assert!(!paths.journal.exists());
        assert_eq!(fs::read(root.join(".git/index")).unwrap(), index);
        super::clear_preserved_conflicts(root, &recovery, &old_commit)
            .expect("clear backed-up conflict");
        assert!(super::repository_hazard(root).unwrap().is_none());
        assert_eq!(fs::read(root.join("conflicted.txt")).unwrap(), old_content);
        assert_eq!(fs::read(root.join("local-note.txt")).unwrap(), b"keep me\n");
        assert_eq!(fs::read(root.join(".env")).unwrap(), b"PRIVATE=keep\n");
    }
}
