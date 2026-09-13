use super::{find_executable, find_git_after_install, print_human, run_command, StageOutcome};
use std::io::{self, IsTerminal};
use std::path::Path;
use std::process::{Command, Stdio};

pub(super) fn usable_git(path: &Path) -> bool {
    let mut command = Command::new(path);
    command
        .arg("--version")
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    // Apple's Git shim exists even before Command Line Tools are installed.
    command.env("GIT_TERMINAL_PROMPT", "0");
    if cfg!(target_os = "macos")
        && path == Path::new("/usr/bin/git")
        && !Command::new("/usr/bin/xcode-select")
            .arg("-p")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .is_ok_and(|status| status.success())
    {
        return false;
    }
    super::hide_command_window(&mut command);
    command.status().is_ok_and(|status| status.success())
}

pub(super) fn install_macos() -> StageOutcome {
    print_human("Opening Apple's Command Line Tools installer (includes Git)...");
    let requested = run_command(Command::new("/usr/bin/xcode-select").arg("--install"));
    if find_git_after_install().is_some() {
        return StageOutcome::ok();
    }
    if requested {
        StageOutcome::fail("Complete the Command Line Tools installation in the macOS dialog, then retry Suzent installation. Git setup has been started.")
    } else {
        StageOutcome::fail("Could not start Command Line Tools installation. If its dialog is already open, complete it and retry. Otherwise run xcode-select --install in Terminal and retry.")
    }
}

fn linux_commands(manager: &str) -> Vec<Vec<&'static str>> {
    match manager {
        "apt-get" => vec![vec!["update"], vec!["install", "-y", "git"]],
        "dnf" | "yum" => vec![vec!["install", "-y", "git"]],
        "pacman" => vec![vec!["-S", "--needed", "--noconfirm", "git"]],
        "zypper" => vec![vec!["--non-interactive", "install", "git"]],
        "apk" => vec![vec!["add", "--no-cache", "git"]],
        _ => vec![],
    }
}

pub(super) fn install_linux(non_interactive: bool) -> StageOutcome {
    let Some((manager, executable)) = ["apt-get", "dnf", "yum", "pacman", "zypper", "apk"]
        .into_iter()
        .find_map(|name| find_executable(name).map(|path| (name, path)))
    else {
        return StageOutcome::fail("No supported package manager found. Install Git with your distribution's package manager, then retry.");
    };
    let root = Command::new("id").arg("-u").output().is_ok_and(|output| {
        output.status.success() && String::from_utf8_lossy(&output.stdout).trim() == "0"
    });
    let terminal = io::stdin().is_terminal();
    let elevation = if root {
        None
    } else if !terminal && !non_interactive && find_executable("pkexec").is_some() {
        find_executable("pkexec")
    } else {
        find_executable("sudo")
    };
    if !root && elevation.is_none() {
        return StageOutcome::fail("Installing Git requires administrator authorization. Install sudo or a desktop PolicyKit agent, or install Git as root, then retry.");
    }
    print_human(format!(
        "Installing Git via {manager}; administrator authorization may be requested..."
    ));
    for args in linux_commands(manager) {
        let mut command = if let Some(helper) = &elevation {
            let mut command = Command::new(helper);
            if helper.file_name().is_some_and(|name| name == "sudo")
                && (non_interactive || !terminal)
            {
                command.arg("-n");
            }
            command.arg(&executable);
            command
        } else {
            Command::new(&executable)
        };
        command.args(args);
        if non_interactive || !terminal {
            command.stdin(Stdio::null());
        }
        if !run_command(&mut command) {
            return StageOutcome::fail(format!("Git installation via {manager} failed or authorization was cancelled. Check the installation details and retry. For unattended runs, provide administrator access first."));
        }
    }
    if find_git_after_install().is_some() {
        print_human("[OK] Git installed");
        StageOutcome::ok()
    } else {
        StageOutcome::fail("The package manager finished, but git --version still fails. Check Git installation and retry.")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn debian_refreshes_indexes_before_installing_git() {
        assert_eq!(
            linux_commands("apt-get"),
            vec![vec!["update"], vec!["install", "-y", "git"]]
        );
    }

    #[test]
    fn supported_managers_install_git_without_removing_packages() {
        for manager in ["dnf", "yum", "pacman", "zypper", "apk"] {
            let commands = linux_commands(manager);
            assert_eq!(commands.len(), 1);
            assert_eq!(commands[0].last(), Some(&"git"));
        }
        assert!(linux_commands("unknown").is_empty());
    }

    #[test]
    fn nonexistent_git_is_not_usable() {
        assert!(!usable_git(Path::new("/nonexistent/suzent-test/git")));
    }

    #[cfg(unix)]
    #[test]
    fn existing_but_broken_git_is_not_usable() {
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        let git = dir.path().join("git");
        std::fs::write(&git, "#!/bin/sh\nexit 1\n").unwrap();
        std::fs::set_permissions(&git, std::fs::Permissions::from_mode(0o755)).unwrap();
        assert!(!usable_git(&git));
        std::fs::write(&git, "#!/bin/sh\nexit 0\n").unwrap();
        assert!(usable_git(&git));
    }
}
