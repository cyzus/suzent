# Suzent Installer

The installer runs independently of an existing Suzent installation. It needs internet access to download prerequisites and Suzent.

## Git setup

The installer verifies `git --version` before continuing. If Git is unavailable:

- **Windows:** installs Git through `winget`, when available.
- **macOS:** starts Apple's Command Line Tools installer, which includes Git. Complete the system dialog, then choose **Retry safely** in Suzent (or rerun the CLI). The installer does not report Git as ready until it works.
- **Linux:** installs Git through `apt-get`, `dnf`, `yum`, `pacman`, `zypper`, or `apk`. Debian/Ubuntu refresh package indexes first. Root installs directly; terminal users authorize through `sudo`, and desktop users can authorize through `pkexec`/PolicyKit. If desktop authorization is unavailable, passwordless sudo is attempted. Unattended CLI runs never prompt for a password and need administrator access prepared in advance.

If authorization is cancelled, installation fails, or the distribution has no supported package manager, the installer stops with retry instructions. It does not continue without a working Git executable.

## Conflicted release updates

The standalone release updater stops on an unresolved merge, rebase, cherry-pick,
or revert. **Back up and update…** opens a native confirmation dialog showing
the directory and target release. Cancel leaves the source and index unchanged.
Headless users must explicitly pass `--backup-conflicts` to authorize this path;
ordinary retries do not imply consent.

After download/fetch preparation and stopping the installation, the updater saves
changed tracked files (including staged-only changes), untracked files, index
stages, and Git operation metadata under the existing
`<installation>/.suzent/update-recovery/` location. It retains recovery Git refs,
verifies file copies and checks for changes since the snapshot before cleanup.
See the snapshot's `README.txt` and `manifest.json` for manual recovery. Local
changes are never automatically reapplied. A failed backup leaves the checkout
untouched; failures after cleanup retain the snapshot and transaction journal.

Ignored data and untracked originals are not cleaned. Obstructing files can still
stop checkout safely. Non-regular changed files, unsupported filename encodings,
or a Git-tracked `.suzent` directory require manual recovery. Git snapshots do
not back up or roll back databases. Rollback restores versioned source and
dependencies, not the original conflicted working state.

This confirmation applies to the release update/repair transaction. The initial
installer's development-workspace route still provides manual upstream-update
instructions; it does not yet provide a transactional branch update.

## Development and validation

From this directory, run `npm ci` and `npm run dev` to open the installer, or `npm run build` to package it. Building requires the repository's shared icons and the platform's Tauri prerequisites.

Run `cargo test` for installer tests. Tests do not install system packages.

Also run `node --test tests/installer-ui.test.mjs`. Before shipping, verify the
native confirmation and cancellation flow on both macOS and Windows, using a
disposable conflicted checkout and an explicit target release. Build with the
lockfile. Test real old-version upgrades, process shutdown, dependency failures,
and recovery separately; a successful build or cancelled dialog does not prove
end-to-end upgrade success. macOS signing/notarization and Intel compatibility
also require release-artifact validation.
