//! Runs the electron-builder package silently into the chosen folder and
//! reports progress by how much of the app has landed there.

use std::collections::HashSet;
use std::io;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

use serde::Serialize;

pub const APP_EXE: &str = if cfg!(windows) {
    "SUZENT.exe"
} else {
    "suzent-desktop"
};
/// Where electron-builder's own one-click install goes; reused so running
/// setup again updates that install in place.
const PACKAGE_DIR_NAME: &str = "suzent-desktop";
const DIR_NAME: &str = "Suzent";

#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    Copying,
    Finishing,
    Checking,
}

#[derive(Debug, Clone, Serialize)]
pub struct Progress {
    pub phase: Phase,
    /// 0 to 100.
    pub percent: u8,
}

/// `%LOCALAPPDATA%\Programs\Suzent`, or an existing install's folder.
pub fn default_dir() -> PathBuf {
    let programs = dirs::data_local_dir()
        .unwrap_or_else(std::env::temp_dir)
        .join("Programs");
    let existing = programs.join(PACKAGE_DIR_NAME);
    if existing.join(APP_EXE).is_file() {
        return existing;
    }
    programs.join(DIR_NAME)
}

/// Why `dir` cannot hold the app, in words for the user, or None.
pub fn problem_with(dir: &Path) -> Option<&'static str> {
    if !dir.is_absolute() {
        return Some("not_absolute");
    }
    let lower = dir.to_string_lossy().to_lowercase();
    if lower.contains(r"\program files")
        || lower.contains(r"\windows\")
        || lower.ends_with(r"\windows")
    {
        return Some("needs_admin");
    }
    if std::fs::create_dir_all(dir).is_err() {
        return Some("not_writable");
    }
    let probe = dir.join(".suzent-setup-probe");
    match std::fs::write(&probe, b"") {
        Ok(()) => {
            let _ = std::fs::remove_file(probe);
            None
        }
        Err(_) => Some("not_writable"),
    }
}

pub fn dir_size(dir: &Path) -> u64 {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return 0;
    };
    entries
        .flatten()
        .map(|entry| match entry.file_type() {
            Ok(kind) if kind.is_dir() => dir_size(&entry.path()),
            Ok(_) => entry.metadata().map(|meta| meta.len()).unwrap_or(0),
            Err(_) => 0,
        })
        .sum()
}

/// The electron-builder package unpacks its 7z into `%TEMP%\nsXXXX.tmp\7z-out`
/// first (most of the time), then copies that into the install folder.
/// Unpacking fills 0 to 70%, the copy 70 to 92%; the package's last steps
/// (PATH, shortcuts) and our check take the rest.
pub fn install_percent(unpacked: u64, copied: u64, total: u64) -> u8 {
    if total == 0 {
        return 0;
    }
    let share = |done: u64| done.min(total) as f64 / total as f64;
    if copied > 0 {
        (70.0 + share(copied) * 22.0) as u8
    } else {
        (share(unpacked) * 70.0) as u8
    }
}

/// NSIS staging folders (`ns*.tmp`) in `temp`.
fn staging_dirs(temp: &Path) -> HashSet<PathBuf> {
    let Ok(entries) = std::fs::read_dir(temp) else {
        return HashSet::new();
    };
    entries
        .flatten()
        .filter(|entry| {
            let name = entry.file_name().to_string_lossy().to_lowercase();
            name.starts_with("ns") && name.ends_with(".tmp") && entry.path().is_dir()
        })
        .map(|entry| entry.path())
        .collect()
}

/// Tracks how far the package has got by what it has written so far.
pub struct Watch {
    temp: PathBuf,
    dir: PathBuf,
    total: u64,
    before: HashSet<PathBuf>,
    /// Smallest size the install folder has had: an older install there is
    /// uninstalled first, and only what lands after that counts.
    floor: u64,
}

impl Watch {
    pub fn new(temp: &Path, dir: &Path, total: u64) -> Self {
        Self {
            temp: temp.to_path_buf(),
            dir: dir.to_path_buf(),
            total,
            before: staging_dirs(temp),
            floor: dir_size(dir),
        }
    }

    pub fn percent(&mut self) -> u8 {
        let unpacked = staging_dirs(&self.temp)
            .difference(&self.before)
            .map(|staging| dir_size(&staging.join("7z-out")))
            .max()
            .unwrap_or(0);
        let size = dir_size(&self.dir);
        self.floor = self.floor.min(size);
        // A few small files (the uninstaller) land before the copy starts.
        let copied = size.saturating_sub(self.floor);
        let copied = if copied * 50 < self.total { 0 } else { copied };
        install_percent(unpacked, copied, self.total)
    }
}

fn package_command(package: &Path, dir: &Path) -> Command {
    let mut command = Command::new(package);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        // NSIS reads /D= raw: last, unquoted, spaces and all.
        command
            .raw_arg("/S")
            .raw_arg(format!("/D={}", dir.display()))
            .creation_flags(CREATE_NO_WINDOW);
    }
    #[cfg(not(windows))]
    command.arg("/S").arg(format!("/D={}", dir.display()));
    command
}

/// Installs `package` into `dir`, calling `report` as it goes.
pub fn run(
    package: &Path,
    dir: &Path,
    unpacked_bytes: u64,
    report: impl Fn(Progress) + Send + Sync + 'static,
) -> io::Result<()> {
    let report = Arc::new(report);
    let finished = Arc::new(AtomicBool::new(false));
    let mut child = package_command(package, dir).spawn()?;
    let watcher = {
        let (finished, report, dir) = (finished.clone(), report.clone(), dir.to_path_buf());
        thread::spawn(move || {
            let mut watch = Watch::new(&std::env::temp_dir(), &dir, unpacked_bytes.max(1));
            while !finished.load(Ordering::Relaxed) {
                let percent = watch.percent();
                let phase = if percent >= 92 {
                    Phase::Finishing
                } else {
                    Phase::Copying
                };
                report(Progress { phase, percent });
                thread::sleep(Duration::from_millis(700));
            }
        })
    };
    let status = child.wait();
    finished.store(true, Ordering::Relaxed);
    let _ = watcher.join();
    check_status(status?)?;
    report(Progress {
        phase: Phase::Checking,
        percent: 96,
    });
    verify(dir)?;
    report(Progress {
        phase: Phase::Checking,
        percent: 100,
    });
    Ok(())
}

fn check_status(status: ExitStatus) -> io::Result<()> {
    if status.success() {
        Ok(())
    } else {
        Err(io::Error::other(format!(
            "the installer exited with {status}"
        )))
    }
}

/// The app is there and its bundled Suzent answers.
pub fn verify(dir: &Path) -> io::Result<()> {
    if !dir.join(APP_EXE).is_file() {
        return Err(io::Error::other(format!(
            "{APP_EXE} is missing from {}",
            dir.display()
        )));
    }
    let cli = dir.join("resources").join("bin").join(if cfg!(windows) {
        "suzent.cmd"
    } else {
        "suzent"
    });
    if !cli.is_file() {
        return Err(io::Error::other("the suzent command is missing"));
    }
    let mut command = Command::new(&cli);
    command.arg("--version");
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x0800_0000);
    }
    let output = command.output()?;
    if !output.status.success() {
        return Err(io::Error::other("Suzent did not start after installing"));
    }
    Ok(())
}

pub fn launch(dir: &Path) -> io::Result<()> {
    Command::new(dir.join(APP_EXE))
        .current_dir(dir)
        .spawn()
        .map(|_| ())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unpacking_then_copying_never_claims_to_be_done() {
        assert_eq!(install_percent(0, 0, 100), 0);
        assert_eq!(install_percent(50, 0, 100), 35);
        assert_eq!(install_percent(100, 0, 100), 70);
        assert_eq!(install_percent(100, 50, 100), 81);
        assert_eq!(install_percent(100, 500, 100), 92);
        assert_eq!(install_percent(5, 5, 0), 0);
    }

    #[test]
    fn follows_the_staging_folder_then_the_install_folder() {
        let work = tempfile::tempdir().unwrap();
        let (temp, dir) = (work.path().join("temp"), work.path().join("Suzent"));
        std::fs::create_dir_all(temp.join("nsOLD.tmp").join("7z-out")).unwrap();
        std::fs::write(
            temp.join("nsOLD.tmp").join("7z-out").join("x"),
            vec![0u8; 90],
        )
        .unwrap();
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("old"), vec![0u8; 80]).unwrap();
        let mut watch = Watch::new(&temp, &dir, 100);
        assert_eq!(watch.percent(), 0);

        std::fs::remove_file(dir.join("old")).unwrap();
        let out = temp.join("nsA1B2.tmp").join("7z-out");
        std::fs::create_dir_all(&out).unwrap();
        std::fs::write(out.join("a"), vec![0u8; 50]).unwrap();
        assert_eq!(watch.percent(), 35);

        std::fs::write(dir.join("a"), vec![0u8; 50]).unwrap();
        assert_eq!(watch.percent(), 81);
    }

    #[test]
    fn sizes_add_up_recursively() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("a"), vec![0u8; 10]).unwrap();
        std::fs::create_dir(dir.path().join("sub")).unwrap();
        std::fs::write(dir.path().join("sub").join("b"), vec![0u8; 5]).unwrap();
        assert_eq!(dir_size(dir.path()), 15);
        assert_eq!(dir_size(&dir.path().join("missing")), 0);
    }

    #[test]
    fn writable_folder_has_no_problem() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(problem_with(&dir.path().join("Suzent")), None);
        assert_eq!(problem_with(Path::new("relative")), Some("not_absolute"));
    }

    #[cfg(windows)]
    #[test]
    fn program_files_needs_admin() {
        assert_eq!(
            problem_with(Path::new(r"C:\Program Files\Suzent")),
            Some("needs_admin")
        );
    }

    #[cfg(unix)]
    #[test]
    fn runs_the_package_and_checks_the_result() {
        use std::os::unix::fs::PermissionsExt;
        use std::sync::Mutex;

        let work = tempfile::tempdir().unwrap();
        let dir = work.path().join("Suzent");
        let package = work.path().join("package.sh");
        // Stands in for NSIS: reads /D= and lays out the app.
        std::fs::write(
            &package,
            "#!/bin/sh\nfor a; do case $a in /D=*) d=${a#/D=};; esac; done\n\
             mkdir -p \"$d/resources/bin\"\nhead -c 2048 /dev/zero > \"$d/suzent-desktop\"\n\
             printf '#!/bin/sh\\necho 1.0\\n' > \"$d/resources/bin/suzent\"\n\
             chmod +x \"$d/resources/bin/suzent\"\n",
        )
        .unwrap();
        std::fs::set_permissions(&package, std::fs::Permissions::from_mode(0o755)).unwrap();
        let seen = Arc::new(Mutex::new(Vec::new()));
        let sink = seen.clone();
        run(&package, &dir, 2048, move |p| {
            sink.lock().unwrap().push(p.percent)
        })
        .unwrap();
        let seen = seen.lock().unwrap();
        assert_eq!(seen.last(), Some(&100));
        assert!(dir.join("suzent-desktop").is_file());
    }
}
