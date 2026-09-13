# Suzent Installer

The installer runs independently of an existing Suzent installation. It needs internet access to download prerequisites and Suzent.

## Git setup

The installer verifies `git --version` before continuing. If Git is unavailable:

- **Windows:** installs Git through `winget`, when available.
- **macOS:** starts Apple's Command Line Tools installer, which includes Git. Complete the system dialog, then choose **Retry safely** in Suzent (or rerun the CLI). The installer does not report Git as ready until it works.
- **Linux:** installs Git through `apt-get`, `dnf`, `yum`, `pacman`, `zypper`, or `apk`. Debian/Ubuntu refresh package indexes first. Root installs directly; terminal users authorize through `sudo`, and desktop users can authorize through `pkexec`/PolicyKit. If desktop authorization is unavailable, passwordless sudo is attempted. Unattended CLI runs never prompt for a password and need administrator access prepared in advance.

If authorization is cancelled, installation fails, or the distribution has no supported package manager, the installer stops with retry instructions. It does not continue without a working Git executable.

## Development

From this directory, run `npm ci` and `npm run dev` to open the installer, or `npm run build` to package it. Building requires the repository's shared icons and the platform's Tauri prerequisites.

Run `cargo test` for installer tests. Tests do not install system packages.
