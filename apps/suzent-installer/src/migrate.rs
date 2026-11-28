//! Moves a Git-checkout install onto the standard desktop installer.
//!
//! A release opts in by publishing `installer-migration.json`. The update
//! then downloads that release's installer, checks it against SHA256SUMS,
//! stops the old install, removes its launchers and `suzent` command, runs
//! the installer, and moves the background service onto the new runtime.
//! The data in `~/.suzent` is shared, so chats, memory and settings carry
//! over. The checkout itself is left in place for the user to delete.

use super::*;

/// Present on a release that moves Git installs to the standard installer.
pub(super) const MARKER: &str = "installer-migration.json";

/// The installers live on GitHub only; npm packages carry the old assets.
fn installer_bases(tag: &str) -> Vec<String> {
    network::release_bases(network::resolved_china_mode(), tag)
        .into_iter()
        .filter(|base| !network::is_npm_base(base))
        .collect()
}

/// The release opts in and has an installer for this platform (there is no
/// Intel Mac build).
pub(super) fn offered(tag: &str) -> bool {
    let bases = installer_bases(tag);
    network::fetch_release_file(&bases, MARKER).is_ok()
        && release_checksum(&bases, &installer_asset(tag)).is_ok()
}

pub(super) fn installer_asset(tag: &str) -> String {
    let version = tag.trim_start_matches('v');
    if cfg!(windows) {
        format!("Suzent-{version}-win-x64.exe")
    } else if cfg!(target_os = "macos") {
        let arch = if network::is_apple_silicon_macos() {
            "arm64"
        } else {
            "x64"
        };
        format!("Suzent-{version}-mac-{arch}.dmg")
    } else {
        format!("Suzent-{version}-linux-x86_64.AppImage")
    }
}

#[derive(Serialize)]
struct Migrated<'a> {
    target_tag: &'a str,
    app: String,
    migrated_at: u64,
}

/// Downloads and checks the installer ahead of time, so the move itself
/// only has to install.
pub(super) fn prefetch(paths: &UpdatePaths, tag: &str) -> Result<PathBuf, String> {
    let bases = installer_bases(tag);
    let asset = installer_asset(tag);
    write_status(
        paths,
        "download",
        10,
        "Downloading the Suzent installer",
        tag,
    )?;
    let expected = release_checksum(&bases, &asset)?;
    fs::create_dir_all(&paths.staging_dir)
        .map_err(display_io("create update staging directory"))?;
    let installer = paths.staging_dir.join(&asset);
    if file_sha256(&installer).ok().as_deref() != Some(expected.as_str()) {
        let _ = fs::remove_file(&installer);
        let mut errors = Vec::new();
        let downloaded = bases.iter().any(|base| {
            let url = format!("{}/{}", base.trim_end_matches('/'), asset);
            download_file(&url, &installer, paths, tag)
                .map_err(|error| errors.push(error))
                .is_ok()
        });
        if !downloaded {
            return Err(errors.join("; "));
        }
        let actual = file_sha256(&installer)?;
        if actual != expected {
            let _ = fs::remove_file(&installer);
            return Err(format!(
                "checksum mismatch for {asset}: expected {expected}, found {actual}"
            ));
        }
    }
    Ok(installer)
}

/// Returns the installed app's executable, for the caller to launch.
pub(super) fn run(paths: &UpdatePaths, tag: &str) -> Result<PathBuf, String> {
    let installer = prefetch(paths, tag)?;

    write_status(paths, "stop", 45, "Stopping Suzent", tag)?;
    let service_was_installed = service_definition_exists();
    if service_was_installed {
        if let Err(error) = run_service_command(&paths.root, "uninstall") {
            push_status_warning(
                paths,
                format!("Old background service not removed: {error}"),
            )?;
        }
    }
    stop_suzent_processes(&paths.root)?;

    // Before installing: on macOS the old launcher is a wrapper app at
    // ~/Applications/SUZENT.app, where the new app may go.
    write_status(paths, "cleanup", 60, "Removing the old launchers", tag)?;
    remove_old_launchers(paths)?;

    write_status(paths, "install", 75, "Installing Suzent", tag)?;
    let app = install(&installer)?;

    if service_was_installed {
        write_status(paths, "service", 90, "Moving the background service", tag)?;
        if let Err(error) = install_service(&app) {
            push_status_warning(
                paths,
                format!("Turn the background service on again in Settings: {error}"),
            )?;
        }
    }

    write_json_atomic(
        &paths.state_dir.join("migrated-to-installer.json"),
        &Migrated {
            target_tag: tag,
            app: app.display().to_string(),
            migrated_at: now_epoch_millis(),
        },
        "record the move to the standard installer",
    )?;
    let _ = fs::remove_file(&installer);
    write_status(
        paths,
        "complete",
        100,
        "Suzent now runs from the standard app",
        tag,
    )?;
    Ok(app)
}

fn file_sha256(path: &Path) -> Result<String, String> {
    let mut file = fs::File::open(path).map_err(display_io("read downloaded installer"))?;
    let mut hasher = Sha256::new();
    // On the heap: Windows gives the main thread a 1 MiB stack.
    let mut buffer = vec![0_u8; 1024 * 1024];
    loop {
        let count = file
            .read(&mut buffer)
            .map_err(display_io("read downloaded installer"))?;
        if count == 0 {
            break;
        }
        hasher.update(&buffer[..count]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

fn remove_old_launchers(paths: &UpdatePaths) -> Result<(), String> {
    let python = service_python(&paths.root);
    if python.exists() {
        if let Err(error) = run_checked(
            background_command(&python)
                .args(["-m", "suzent.cli", "shortcuts", "--remove"])
                .current_dir(&paths.root),
            "remove old shortcuts",
        ) {
            push_status_warning(paths, format!("Old shortcuts not removed: {error}"))?;
        }
    }
    if let Err(error) = remove_windows_shortcuts(&paths.root) {
        push_status_warning(paths, format!("Old shortcuts not removed: {error}"))?;
    }
    let home = home_dir().ok_or("could not find the home directory")?;
    let bin = home.join(".local").join("bin");
    for name in ["suzent", "suzent.cmd"] {
        let shim = bin.join(name);
        if is_checkout_shim(&shim, &paths.root) {
            fs::remove_file(&shim).map_err(display_io("remove the old suzent command"))?;
        }
    }
    Ok(())
}

/// Older CLIs decoded PowerShell's output in the ANSI code page, so on a
/// Chinese Windows a redirected desktop such as `OneDrive\桌面` was recorded
/// as mojibake and `shortcuts --remove` could not find it. Ask Windows for
/// the folders again and drop any shortcut that still opens the old UI.
#[cfg(windows)]
fn remove_windows_shortcuts(root: &Path) -> Result<(), String> {
    const SCRIPT: &str = "$ErrorActionPreference = 'Stop'; \
        $shell = New-Object -ComObject WScript.Shell; \
        foreach ($folder in 'Programs', 'DesktopDirectory') { \
          $dir = [Environment]::GetFolderPath($folder); \
          if ([string]::IsNullOrWhiteSpace($dir)) { continue }; \
          Get-ChildItem -LiteralPath $dir -Filter '*.lnk' -File -ErrorAction SilentlyContinue | \
            Where-Object { $shell.CreateShortcut($_.FullName).TargetPath -eq $env:SUZENT_OLD_UI } | \
            Remove-Item -Force }";
    run_checked(
        background_command("powershell")
            .args([
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                SCRIPT,
            ])
            .env("SUZENT_OLD_UI", root.join("bin").join("suzent-ui.exe")),
        "remove old shortcuts",
    )
}

#[cfg(not(windows))]
fn remove_windows_shortcuts(_root: &Path) -> Result<(), String> {
    Ok(())
}

/// The setup scripts' `suzent` wrappers `cd` into the checkout they serve.
pub(super) fn is_checkout_shim(path: &Path, root: &Path) -> bool {
    let Ok(content) = fs::read_to_string(path) else {
        return false;
    };
    let root = root.display().to_string();
    content.contains("uv run suzent") && content.contains(root.trim_end_matches(['/', '\\']))
}

fn home_dir() -> Option<PathBuf> {
    let variable = if cfg!(windows) { "USERPROFILE" } else { "HOME" };
    std::env::var_os(variable).map(PathBuf::from)
}

#[cfg(windows)]
fn install(installer: &Path) -> Result<PathBuf, String> {
    run_checked(
        background_command(installer).arg("/S"),
        "run the Suzent installer",
    )?;
    let programs = std::env::var_os("LOCALAPPDATA")
        .map(|dir| PathBuf::from(dir).join("Programs"))
        .ok_or("LOCALAPPDATA is not set")?;
    ["SUZENT", "suzent-desktop", "Suzent"]
        .iter()
        .map(|dir| programs.join(dir).join("SUZENT.exe"))
        .find(|app| app.is_file())
        .ok_or_else(|| {
            format!(
                "the installer did not put SUZENT.exe in {}",
                programs.display()
            )
        })
}

#[cfg(target_os = "macos")]
fn install(installer: &Path) -> Result<PathBuf, String> {
    let mount = installer.with_extension("mount");
    let _ = fs::remove_dir_all(&mount);
    fs::create_dir_all(&mount).map_err(display_io("create disk image mount point"))?;
    run_checked(
        background_command("hdiutil")
            .args(["attach", "-nobrowse", "-readonly", "-mountpoint"])
            .arg(&mount)
            .arg(installer),
        "open the Suzent disk image",
    )?;
    let result = (|| {
        let target = applications_dir()?.join("SUZENT.app");
        if target.exists() {
            fs::remove_dir_all(&target).map_err(display_io("replace the existing Suzent app"))?;
        }
        run_checked(
            background_command("ditto")
                .arg(mount.join("SUZENT.app"))
                .arg(&target),
            "copy Suzent to Applications",
        )?;
        Ok(target.join("Contents").join("MacOS").join("SUZENT"))
    })();
    let _ = background_command("hdiutil")
        .args(["detach", "-quiet"])
        .arg(&mount)
        .status();
    let _ = fs::remove_dir(&mount);
    result
}

/// /Applications when the user may write there, else ~/Applications.
#[cfg(target_os = "macos")]
fn applications_dir() -> Result<PathBuf, String> {
    let system = PathBuf::from("/Applications");
    let probe = system.join(format!(".suzent-write-test-{}", std::process::id()));
    if fs::write(&probe, b"").is_ok() {
        let _ = fs::remove_file(&probe);
        return Ok(system);
    }
    let user = home_dir()
        .ok_or("could not find the home directory")?
        .join("Applications");
    fs::create_dir_all(&user).map_err(display_io("create ~/Applications"))?;
    Ok(user)
}

#[cfg(all(unix, not(target_os = "macos")))]
fn install(installer: &Path) -> Result<PathBuf, String> {
    use std::os::unix::fs::PermissionsExt;

    let home = home_dir().ok_or("could not find the home directory")?;
    let apps = home.join("Applications");
    fs::create_dir_all(&apps).map_err(display_io("create ~/Applications"))?;
    let app = apps.join("Suzent.AppImage");
    let temporary = apps.join("Suzent.AppImage.download");
    fs::copy(installer, &temporary).map_err(display_io("copy the Suzent AppImage"))?;
    fs::set_permissions(&temporary, fs::Permissions::from_mode(0o755))
        .map_err(display_io("make the Suzent AppImage executable"))?;
    rename_with_retry(&temporary, &app, "install the Suzent AppImage")?;
    let entries = std::env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| home.join(".local").join("share"))
        .join("applications");
    fs::create_dir_all(&entries).map_err(display_io("create the applications folder"))?;
    fs::write(
        entries.join("suzent-desktop.desktop"),
        format!(
            "[Desktop Entry]\nType=Application\nName=Suzent\nComment=Your sovereign personal AI agent\nExec=\"{}\" %U\nTerminal=false\nCategories=Utility;\nStartupWMClass=SUZENT\n",
            app.display()
        ),
    )
    .map_err(display_io("write the Suzent menu entry"))?;
    Ok(app)
}

/// Runs `suzent service install` from the new app's bundled runtime.
fn install_service(app: &Path) -> Result<(), String> {
    let resources = if cfg!(target_os = "macos") {
        app.parent()
            .and_then(Path::parent)
            .map(|contents| contents.join("Resources"))
    } else {
        app.parent().map(|dir| dir.join("resources"))
    };
    let resources = resources.ok_or("could not find the app's resources")?;
    if !resources.join("runtime").is_dir() {
        // An AppImage keeps its runtime inside the image; the app offers the
        // service again in Settings.
        return Err("this app type cannot run the service from outside".into());
    }
    let python = if cfg!(windows) {
        resources.join("runtime").join("python").join("python.exe")
    } else {
        resources
            .join("runtime")
            .join("python")
            .join("bin")
            .join("python3")
    };
    let cli = |args: &[&str]| {
        let mut command = background_command(&python);
        command
            .args(["-m", "suzent.cli", "service"])
            .args(args)
            .env("PYTHONNOUSERSITE", "1")
            .env("PYTHONDONTWRITEBYTECODE", "1");
        command
    };
    run_checked(&mut cli(&["install"]), "install the background service")?;
    // The caller opens the app next. Opened before the service answers, the
    // app finds no backend and starts its own, so two would share ~/.suzent.
    let deadline = Instant::now() + SERVICE_READY_TIMEOUT;
    while Instant::now() < deadline {
        if cli(&["doctor"])
            .output()
            .is_ok_and(|output| output.status.success())
        {
            return Ok(());
        }
        thread::sleep(Duration::from_secs(2));
    }
    Err("the background service did not become ready in time".into())
}

const SERVICE_READY_TIMEOUT: Duration = Duration::from_secs(120);

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hashing_an_installer_fits_a_small_thread_stack() {
        let dir = tempfile::tempdir().unwrap();
        let file = dir.path().join("installer");
        fs::write(&file, b"suzent").unwrap();
        let hash = std::thread::Builder::new()
            .stack_size(256 * 1024)
            .spawn(move || file_sha256(&file))
            .unwrap()
            .join()
            .unwrap()
            .unwrap();
        assert_eq!(hash, network::sha256_hex(b"suzent"));
    }

    #[test]
    fn installer_names_match_electron_builder() {
        let name = installer_asset("v1.2.3");
        if cfg!(windows) {
            assert_eq!(name, "Suzent-1.2.3-win-x64.exe");
        } else if cfg!(target_os = "macos") {
            assert!(name == "Suzent-1.2.3-mac-arm64.dmg" || name == "Suzent-1.2.3-mac-x64.dmg");
        } else {
            assert_eq!(name, "Suzent-1.2.3-linux-x86_64.AppImage");
        }
    }

    #[test]
    fn only_setup_script_shims_for_this_checkout_are_removed() {
        let dir = std::env::temp_dir().join(format!("suzent-shim-test-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let root = Path::new("/home/me/suzent");
        let ours = dir.join("ours");
        fs::write(
            &ours,
            "#!/usr/bin/env bash\ncd \"/home/me/suzent\"\nexec uv run suzent \"$@\"\n",
        )
        .unwrap();
        let other = dir.join("other");
        fs::write(
            &other,
            "#!/bin/sh\ncd \"/home/me/elsewhere\"\nexec uv run suzent \"$@\"\n",
        )
        .unwrap();
        let managed = dir.join("managed");
        fs::write(&managed, "#!/bin/sh\n# managed-by: suzent-desktop\n").unwrap();
        assert!(is_checkout_shim(&ours, root));
        assert!(!is_checkout_shim(&other, root));
        assert!(!is_checkout_shim(&managed, root));
        assert!(!is_checkout_shim(&dir.join("missing"), root));
        fs::remove_dir_all(&dir).unwrap();
    }
}
