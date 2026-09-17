"""
Top-level CLI commands: start, serve, stop, doctor, update, upgrade, setup-build-tools.
"""

import hashlib
import io
import json
import os
import platform
import plistlib
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
import urllib.error
import urllib.request
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import psutil
import typer
from suzent.config import DEFAULT_PORT, RUNTIME_DIR
from suzent.version import (
    UNKNOWN,
    get_backend_commit,
    read_project_version,
    short_commit,
)

IS_WINDOWS = sys.platform == "win32"

_REPO = "cyzus/suzent"
_BIN_DIR = "bin"
_UPDATE_CHECK_TTL_SECONDS = 24 * 60 * 60
_UPDATE_CHANNEL_FILE = ".suzent/update-channel"
_STABLE_CHANNEL = "stable"
# How long a detached start waits for the backend before reporting readiness.
_READY_TIMEOUT = 30.0
# Port the Tauri/Vite dev frontend serves on.
DEV_FRONTEND_PORT = 18080
_DEV_CHANNEL = "dev"
_UPDATE_HELPER_ENV = "SUZENT_UPDATE_HELPER"
_MACOS_UI_BUNDLE = "SUZENT.app"


def _is_development_workspace(root: Path) -> bool:
    """Return True for source checkouts that are not bootstrapped installs."""
    return not (root / ".suzent-bootstrap-complete").exists()


def _backend_sync_args(root: Path) -> list[str]:
    args = ["uv", "sync", "--frozen", "--extra", "social"]
    if _is_development_workspace(root):
        args.extend(["--extra", "dev"])
    return args


def _interrupted_update_message(root: Path) -> str | None:
    journal = root / ".suzent" / "update-transaction.json"
    if not journal.exists():
        return None
    try:
        transaction = json.loads(journal.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        transaction = {}
    target = transaction.get("target_tag", "the selected release")
    phase = transaction.get("phase", "unknown")
    return (
        f"An update to {target} was interrupted during {phase}. "
        "Run 'suzent repair' before starting Suzent."
    )


def _get_ui_binary(root: Path) -> Path | None:
    """Return the managed release UI, falling back to a local release build."""
    name = "suzent-ui.exe" if IS_WINDOWS else "suzent-ui"
    release_name = "suzent.exe" if IS_WINDOWS else "suzent"
    managed_release = root / _BIN_DIR / name

    # `suzent update` installs the UI and its version marker atomically. Prefer
    # that managed pair over a locally-built executable whose newer mtime does
    # not imply compatibility with the checked-out backend.
    if managed_release.exists() and (root / _BIN_DIR / "version.txt").exists():
        return managed_release

    candidates = [
        managed_release,
        root / "src-tauri" / "target" / "release" / release_name,
    ]
    existing = [p for p in candidates if p.exists() and _is_ui_binary_current(root, p)]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def _update_channel_path(root: Path) -> Path:
    return root / _UPDATE_CHANNEL_FILE


def _read_update_channel(root: Path) -> str:
    try:
        channel = _update_channel_path(root).read_text(encoding="utf-8").strip()
    except OSError:
        return _STABLE_CHANNEL
    return channel if channel in {_STABLE_CHANNEL, _DEV_CHANNEL} else _STABLE_CHANNEL


def _write_update_channel(root: Path, channel: str) -> None:
    path = _update_channel_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(channel, encoding="utf-8")


def _refresh_shortcuts(root: Path) -> None:
    """Repair launcher entries after an update, never failing the update itself."""
    from suzent.cli import shortcuts as shortcut_manager

    typer.echo("  • Refreshing launcher shortcuts...")
    try:
        report = shortcut_manager.install_or_repair(root)
    except Exception as error:  # pragma: no cover - defensive, never fatal
        typer.echo(f"  ⚠️  Launcher shortcut repair failed: {error}")
        return
    if report.ok:
        typer.echo(f"  ✅ Launcher shortcuts: {report.summary()}")
        return
    typer.echo(
        "  ⚠️  Launcher shortcuts need attention: "
        f"{'; '.join(report.notes) or 'unknown issue'}"
    )


def _is_ui_binary_current(root: Path, binary: Path) -> bool:
    """Return True when a discovered UI binary can be launched."""
    return binary.exists()


def _macos_bundle_plist(executable: str, version: str) -> bytes:
    info: dict[str, object] = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleExecutable": executable,
        "CFBundleIconFile": "icon.icns",
        "CFBundleIdentifier": "com.suzent.app",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": "SUZENT",
        "CFBundlePackageType": "APPL",
        "CFBundleSignature": "????",
        "LSMinimumSystemVersion": "10.13",
        "NSHighResolutionCapable": True,
    }
    if re.fullmatch(r"\d+(\.\d+){0,2}", version):
        info["CFBundleShortVersionString"] = version
        info["CFBundleVersion"] = version
    return plistlib.dumps(info, sort_keys=True)


def _write_bundle_file(path: Path, data: bytes) -> None:
    """Write bundle metadata, leaving the mtime alone when nothing changed."""
    if path.exists() and path.read_bytes() == data:
        return
    path.write_bytes(data)


def _link_bundle_executable(binary: Path, executable: Path) -> None:
    """Point the bundle at the current binary, refreshing it after an update."""
    if executable.exists() and executable.stat().st_ino == binary.stat().st_ino:
        return
    executable.unlink(missing_ok=True)
    try:
        os.link(binary, executable)
    except OSError:
        shutil.copy2(binary, executable)
        executable.chmod(0o755)


def _macos_launch_target(root: Path, binary: Path) -> Path:
    """Return a path that launches the UI with the Suzent icon and name.

    Releases publish a bare Mach-O executable, but macOS reads an app's icon,
    name and activation policy from the enclosing bundle — a loose binary only
    ever gets the generic executable icon. Generating the bundle around the
    downloaded binary keeps the single-file release format intact.
    """
    if sys.platform != "darwin" or not binary.exists():
        return binary
    if any(part.endswith(".app") for part in binary.parts):
        return binary

    try:
        bundle = binary.parent / _MACOS_UI_BUNDLE
        contents = bundle / "Contents"
        macos_dir = contents / "MacOS"
        resources = contents / "Resources"
        macos_dir.mkdir(parents=True, exist_ok=True)
        resources.mkdir(parents=True, exist_ok=True)

        _write_bundle_file(
            contents / "Info.plist",
            _macos_bundle_plist(
                binary.name, _normalize_version_tag(_current_version(root))
            ),
        )
        icon = root / "src-tauri" / "icons" / "icon.icns"
        if icon.exists():
            _write_bundle_file(resources / "icon.icns", icon.read_bytes())

        executable = macos_dir / binary.name
        _link_bundle_executable(binary, executable)
    except OSError:
        return binary
    return executable


def _ui_launch_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    if extra:
        env.update(extra)

    bypass_hosts = ["127.0.0.1", "localhost", "::1"]
    for key in ("NO_PROXY", "no_proxy"):
        existing = [
            item.strip() for item in env.get(key, "").split(",") if item.strip()
        ]
        merged = existing + [host for host in bypass_hosts if host not in existing]
        env[key] = ",".join(merged)
    return env


def _has_unreleased_ui_changes(root: Path) -> bool:
    """Return True when local backend/Tauri changes are not represented by releases."""
    if not (root / ".git").exists():
        return False

    watched_paths = [
        "src-tauri",
    ]

    commands = [
        ["git", "diff", "--name-only", "--", *watched_paths],
        ["git", "diff", "--name-only", "main...HEAD", "--", *watched_paths],
    ]
    for command in commands:
        try:
            result = subprocess.run(
                command,
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            continue
        if result.returncode == 0 and result.stdout.strip():
            return True

    return False


def _is_suzent_server_running(
    host: str, port: int, timeout: float = 1.0, attempts: int = 1
) -> bool:
    """Return True when a Suzent backend responds on host:port.

    A backend that is busy -- discovering models, draining a shutdown -- can
    miss a single probe's deadline. Callers that decide whether a server exists
    at all pass `attempts` > 1, so a loaded server is not mistaken for an absent
    one: `restart` used to announce "No Suzent server running" and then have
    `start` immediately find that very server and kill it.
    """
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{probe_host}:{port}/health"
    for attempt in range(attempts):
        if attempt:
            time.sleep(0.25)
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                if response.status != 200:
                    continue
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, json.JSONDecodeError, urllib.error.URLError):
            continue
        if payload.get("app") == "suzent" and payload.get("status") == "ok":
            return True
    return False


def _platform_asset_name() -> str:
    machine = platform.machine().lower()
    if IS_WINDOWS:
        return "suzent-windows-x86_64.exe"
    if sys.platform == "darwin":
        return (
            "suzent-macos-aarch64"
            if machine in ("arm64", "aarch64")
            else "suzent-macos-x86_64"
        )
    return "suzent-linux-x86_64"


def _platform_installer_asset_name() -> str:
    machine = platform.machine().lower()
    if IS_WINDOWS:
        return "suzent-installer-windows-x86_64.exe"
    if sys.platform == "darwin":
        return (
            "suzent-installer-macos-aarch64"
            if machine in ("arm64", "aarch64")
            else "suzent-installer-macos-x86_64"
        )
    return "suzent-installer-linux-x86_64"


def _persistent_updater_path() -> Path:
    name = "suzent-installer.exe" if IS_WINDOWS else "suzent-installer"
    return Path.home() / ".suzent" / "updater" / name


def _graphical_update_available() -> bool:
    """Return whether the current session can show the updater window."""
    if IS_WINDOWS or sys.platform == "darwin":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _fetch_latest_release(timeout: float = 10.0) -> dict:
    url = f"https://api.github.com/repos/{_REPO}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": "suzent-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _release_asset_url(asset_name: str, version: str) -> str:
    if version == "latest":
        return f"https://github.com/{_REPO}/releases/latest/download/{asset_name}"
    return f"https://github.com/{_REPO}/releases/download/{version}/{asset_name}"


def _parse_release_checksum(contents: str, asset_name: str) -> str:
    for line in contents.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2:
            continue
        digest, filename = parts
        if filename.lstrip("*") == asset_name and re.fullmatch(
            r"[0-9a-fA-F]{64}", digest
        ):
            return digest.lower()
    raise ValueError(f"SHA256SUMS has no valid entry for {asset_name}")


def _verify_release_asset(path: Path, asset_name: str, release_tag: str) -> None:
    checksum_url = _release_asset_url("SHA256SUMS", release_tag)
    request = urllib.request.Request(
        checksum_url,
        headers={"User-Agent": "suzent-updater"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        expected = _parse_release_checksum(
            response.read().decode("utf-8"),
            asset_name,
        )
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        raise ValueError(
            f"Checksum mismatch for {asset_name}: expected {expected}, found {actual}"
        )


def _local_ui_version(root: Path) -> str:
    f = root / _BIN_DIR / "version.txt"
    return f.read_text().strip() if f.exists() else ""


def _current_version(root: Path) -> str:
    """Return the version declared by `root`, then installed package metadata.

    Root-relative on purpose: `suzent update` asks about the workspace being
    updated, which is not always the tree the running code was imported from.
    """
    declared = read_project_version(root / "pyproject.toml")
    if declared:
        return declared

    try:
        return version("suzent")
    except PackageNotFoundError:
        return ""


def _normalize_version_tag(value: str) -> str:
    return value.strip().lstrip("vV")


def _ui_version_detail(root: Path) -> str | None:
    """Describe the installed UI binary, or None when there is nothing to say.

    Developer and branch installs record the literal marker "latest" rather
    than a resolved tag (`scripts/setup.sh`), which identifies nothing, so a
    recorded value carrying no digits is reported as unknown rather than quoted
    back as if it were a version.
    """
    recorded = _local_ui_version(root)
    if not recorded:
        return None
    ui = _normalize_version_tag(recorded)
    return f"ui {ui if _version_key(ui) else 'unknown'}"


def format_version_line(root: Path) -> str:
    """Render the one-line version banner shown by `suzent --version`.

    The declared version alone does not identify a development install -- the
    checked-out branch carries whatever version its pyproject happens to hold --
    so the commit goes alongside it whenever it can be resolved.

    On the dev channel `start` builds the UI from source and never launches the
    downloaded binary, so reporting that binary's version there would describe
    something that does not run; the channel is named instead.
    """
    backend = _normalize_version_tag(_current_version(root)) or "unknown"

    details = []
    commit = get_backend_commit()
    if commit != UNKNOWN:
        details.append(short_commit(commit))

    if _read_update_channel(root) == _DEV_CHANNEL:
        details.append(_DEV_CHANNEL)
    elif ui_detail := _ui_version_detail(root):
        details.append(ui_detail)

    return (
        f"suzent {backend} ({', '.join(details)})" if details else f"suzent {backend}"
    )


def _version_key(value: str) -> tuple[int, ...]:
    """Build a simple comparable key for release tags like v0.6.2."""
    parts = re.findall(r"\d+", _normalize_version_tag(value))
    return tuple(int(part) for part in parts)


def _is_newer_version(latest: str, current: str) -> bool:
    latest_key = _version_key(latest)
    current_key = _version_key(current)
    return bool(latest_key and current_key and latest_key > current_key)


def _update_check_cache_path(root: Path) -> Path:
    return root / ".suzent" / "update-check.json"


def _read_update_check_cache(root: Path) -> dict | None:
    path = _update_check_cache_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    checked_at = data.get("checked_at")
    if not isinstance(checked_at, (int, float)):
        return None
    if time.time() - checked_at > _UPDATE_CHECK_TTL_SECONDS:
        return None
    return data


def _write_update_check_cache(root: Path, data: dict) -> None:
    path = _update_check_cache_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    # Written through a private temporary file because the refresh can run on a
    # daemon thread the interpreter may kill mid-write. The name is unique per
    # writer: overlapping `suzent` processes can refresh the same stale cache,
    # and a shared temporary name lets one writer's replace pull the file out
    # from under another's still-open handle.
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
    except OSError:
        return

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        os.replace(tmp_name, path)
    except OSError:
        Path(tmp_name).unlink(missing_ok=True)


def _check_for_update(root: Path, *, use_cache: bool = True) -> dict:
    """Return update metadata. Network failures are reported as unavailable."""
    current = _current_version(root)
    if use_cache:
        cached = _read_update_check_cache(root)
        if cached:
            cached["current_version"] = current
            latest_cached = str(cached.get("latest_version", ""))
            cached["update_available"] = _is_newer_version(latest_cached, current)
            return cached

    try:
        release = _fetch_latest_release(timeout=2.0)
    except Exception as error:
        return {
            "checked_at": time.time(),
            "current_version": current,
            "latest_version": "",
            "html_url": "",
            "update_available": False,
            "error": str(error),
        }

    latest = str(release.get("tag_name", ""))
    data = {
        "checked_at": time.time(),
        "current_version": current,
        "latest_version": latest,
        "html_url": str(release.get("html_url", "")),
        "update_available": _is_newer_version(latest, current),
        "error": "",
    }
    _write_update_check_cache(root, data)
    return data


def _refresh_update_check_cache_async(root: Path) -> None:
    """Warm the update-check cache for the next run, off the startup path."""

    def _refresh() -> None:
        try:
            _check_for_update(root, use_cache=False)
        except Exception:
            pass

    threading.Thread(target=_refresh, name="suzent-update-check", daemon=True).start()


def _notify_update_available(root: Path) -> None:
    if os.environ.get("SUZENT_SKIP_UPDATE_CHECK") == "1":
        return

    cached = _read_update_check_cache(root)
    if cached is None:
        # A cold or expired cache means a GitHub round-trip, and startup must not
        # block on advisory information. Refresh for the next run instead; the
        # explicit `suzent check-update` still answers synchronously.
        _refresh_update_check_cache_async(root)
        return

    current = _current_version(root)
    latest = str(cached.get("latest_version", ""))
    if not _is_newer_version(latest, current):
        return

    typer.echo(
        f"  • Update available: {current or 'unknown'} -> {latest}. "
        "Run 'suzent update'."
    )


def _download_file_atomic(
    url: str,
    dest: Path,
    *,
    inactivity_timeout: float = 300.0,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{dest.name}.", suffix=".tmp", dir=dest.parent
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as file:
            req = urllib.request.Request(url, headers={"User-Agent": "suzent-updater"})
            with urllib.request.urlopen(req, timeout=inactivity_timeout) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                downloaded = 0
                last_report = 0.0
                while chunk := resp.read(256 * 1024):
                    file.write(chunk)
                    downloaded += len(chunk)
                    now = time.monotonic()
                    if now - last_report >= 0.25 or (total and downloaded >= total):
                        if total:
                            percent = min(100, round(downloaded * 100 / total))
                            detail = (
                                f"{downloaded / 1024 / 1024:.1f} / "
                                f"{total / 1024 / 1024:.1f} MiB ({percent}%)"
                            )
                        else:
                            detail = f"{downloaded / 1024 / 1024:.1f} MiB"
                        typer.echo(f"\r  • Downloading {detail}", nl=False)
                        last_report = now
                if downloaded:
                    typer.echo()
        tmp_path.replace(dest)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def _install_release_updater(release_tag: str) -> Path:
    updater = _persistent_updater_path()
    version_file = updater.with_name("version.txt")
    installed_version = (
        version_file.read_text(encoding="utf-8").strip()
        if version_file.exists()
        else ""
    )
    if updater.exists() and installed_version == release_tag:
        return updater

    asset = _platform_installer_asset_name()
    staged = updater.with_name(f".{updater.name}.{release_tag}.new")
    try:
        _download_file_atomic(_release_asset_url(asset, release_tag), staged)
        _verify_release_asset(staged, asset, release_tag)
        if not IS_WINDOWS:
            staged.chmod(0o755)
        staged.replace(updater)
        version_file.write_text(release_tag, encoding="utf-8")
    finally:
        staged.unlink(missing_ok=True)
    return updater


def _delegate_installer_update(
    root: Path,
    *,
    release_tag: str,
    relaunch: Path | None,
    repair: bool = False,
    headless: bool = False,
) -> None:
    typer.echo("  • Preparing standalone updater...")
    try:
        updater = _install_release_updater(release_tag)
    except Exception as error:
        typer.echo(f"  ❌ Could not prepare standalone updater: {error}")
        raise typer.Exit(code=1)

    command = [
        str(updater),
        "--repair" if repair else "--update",
        "--dir",
        str(root),
        "--target",
        release_tag,
        "--wait-pid",
        str(os.getpid()),
        "--keep-open-on-error",
    ]
    if relaunch is not None:
        command.extend(["--relaunch", str(relaunch)])

    use_headless = headless or not _graphical_update_available()
    if use_headless:
        command.append("--headless")

    kwargs: dict = {"cwd": root, "env": os.environ.copy()}
    if IS_WINDOWS:
        kwargs["creationflags"] = getattr(
            subprocess, "CREATE_NEW_CONSOLE", 0
        ) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)
    if not use_headless and process is not None:
        time.sleep(0.75)
        if process.poll() is not None:
            typer.echo("  ⚠️  Updater window unavailable; continuing in the terminal.")
            subprocess.Popen([*command, "--headless"], **kwargs)
    action = "Repair" if repair else "Update"
    destination = "terminal" if use_headless else "standalone Suzent Installer"
    typer.echo(f"  • {action} continues in the {destination}.")


def _replace_ui_files(
    dest: Path,
    version_file: Path,
    staged_binary: Path,
    staged_version: Path,
) -> None:
    """Replace the UI binary and metadata as one recoverable operation."""
    binary_backup = dest.with_name(f".{dest.name}.previous")
    version_backup = version_file.with_name(f".{version_file.name}.previous")
    for backup in (binary_backup, version_backup):
        backup.unlink(missing_ok=True)

    binary_backed_up = False
    version_backed_up = False
    binary_installed = False
    version_installed = False
    try:
        if dest.exists():
            dest.replace(binary_backup)
            binary_backed_up = True
        if version_file.exists():
            version_file.replace(version_backup)
            version_backed_up = True

        staged_binary.replace(dest)
        binary_installed = True
        staged_version.replace(version_file)
        version_installed = True
    except Exception:
        if version_installed:
            version_file.unlink(missing_ok=True)
        if binary_installed:
            dest.unlink(missing_ok=True)
        if version_backed_up:
            version_backup.replace(version_file)
        if binary_backed_up:
            binary_backup.replace(dest)
        raise
    else:
        binary_backup.unlink(missing_ok=True)
        version_backup.unlink(missing_ok=True)


def download_ui_binary(root: Path, *, version: str = "latest") -> bool:
    """Download the pre-built UI binary from GitHub Releases. Returns True on success."""
    asset_name = _platform_asset_name()
    staged_binary: Path | None = None
    staged_version: Path | None = None
    try:
        bin_dir = root / _BIN_DIR
        dest = bin_dir / ("suzent-ui.exe" if IS_WINDOWS else "suzent-ui")
        version_file = bin_dir / "version.txt"
        staged_binary = dest.with_name(f".{dest.name}.{version}.new")
        staged_version = version_file.with_name(f".{version_file.name}.{version}.new")

        typer.echo("  • Downloading UI binary...")
        _download_file_atomic(_release_asset_url(asset_name, version), staged_binary)
        if not IS_WINDOWS:
            staged_binary.chmod(0o755)
        staged_version.write_text(version, encoding="utf-8")
        _replace_ui_files(dest, version_file, staged_binary, staged_version)
        staged_binary = None
        staged_version = None
        typer.echo(f"  ✅ UI binary ready at {dest}")
        return True
    except Exception as e:
        typer.echo(f"  ⚠️  Binary download failed: {e}")
        return False
    finally:
        for staged_path in (staged_binary, staged_version):
            if staged_path is not None:
                try:
                    staged_path.unlink(missing_ok=True)
                except OSError:
                    pass


def _update_ui_binary(root: Path, release_tag: str) -> bool:
    """Install the UI asset built from the exact backend release tag."""
    local = _local_ui_version(root)
    if release_tag == local and _get_ui_binary(root):
        typer.echo(f"  • UI binary up to date ({local})")
        return True
    typer.echo(f"  • UI binary: {local or 'none'} → {release_tag}")
    return download_ui_binary(root, version=release_tag)


def _configure_console_encoding():
    """Configure console encoding for Windows to handle Unicode (emoji) output.

    Windows consoles using non-UTF-8 code pages (e.g. GBK for Chinese locale)
    will raise UnicodeEncodeError when printing emoji characters. This function
    reconfigures stdout/stderr to use UTF-8 with a 'replace' error handler so
    unsupported characters degrade gracefully instead of crashing.
    """
    if not IS_WINDOWS:
        return

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if stream is None or not hasattr(stream, "buffer"):
            continue
        try:
            encoding = getattr(stream, "encoding", "") or ""
            if encoding.lower().replace("-", "") != "utf8":
                wrapped = io.TextIOWrapper(
                    stream.buffer,
                    encoding="utf-8",
                    errors="replace",
                    line_buffering=stream.line_buffering,
                )
                setattr(sys, stream_name, wrapped)
        except Exception:
            pass  # Don't crash if reconfiguration fails


def configure_logging(verbose: bool = False):
    """Configure logging for the CLI."""
    from suzent.logger import setup_logging

    log_level = "DEBUG" if verbose else "WARNING"
    setup_logging(level=log_level)

    # If not verbose, silence all other loggers or set them to WARNING
    if not verbose:
        os.environ["LOGURU_LEVEL"] = "WARNING"


def load_environment():
    """Load persisted secrets into environment variables."""
    try:
        from suzent.core.secrets import get_secret_manager

        count = get_secret_manager().inject_all_to_env()

        if count > 0:
            from suzent.logger import get_logger

            logger = get_logger(__name__)
            logger.debug(f"Loaded {count} persisted secrets into environment")

    except Exception as e:
        # Don't crash if DB fails, just log warning
        # We might be running 'setup-build-tools' or 'doctor' where DB isn't needed
        from suzent.logger import get_logger

        logger = get_logger(__name__)
        logger.debug(f"Failed to load persisted environment: {e}")


def get_project_root() -> Path:
    """Get the root directory of the project."""
    return Path(__file__).parent.parent.parent.parent


def ensure_cargo_in_path():
    """Ensure Rust's cargo is in PATH and runnable."""
    if shutil.which("cargo"):
        return

    candidates = [Path.home() / ".cargo" / "bin"]

    if os.environ.get("CARGO_HOME"):
        candidates.append(Path(os.environ["CARGO_HOME"]) / "bin")

    found_path = None
    for path in candidates:
        if path.exists() and (path / ("cargo.exe" if IS_WINDOWS else "cargo")).exists():
            found_path = path
            break

    if found_path:
        typer.echo(f"📦 Found cargo at {found_path}, adding to PATH...")
        current_path = os.environ.get("PATH", "")
        sep = ";" if IS_WINDOWS else ":"
        os.environ["PATH"] = f"{found_path}{sep}{current_path}"
        return
    else:
        typer.echo("⚠️  Could not find 'cargo' in standard locations.")
        typer.echo("   Please ensure Rust is installed and 'cargo' is in your PATH.")
        typer.echo(
            "   Normal `suzent start` uses the pre-built UI and does not need Rust."
        )
        if IS_WINDOWS:
            typer.echo("   Install Rust with:")
            typer.echo("     winget install --id Rustlang.Rustup --source winget")
            typer.echo("   Then restart PowerShell and run `suzent start --dev` again.")
        else:
            typer.echo("   Install Rust with:")
            typer.echo(
                "     curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
            )
            typer.echo("   Then restart your shell and run `suzent start --dev` again.")
        raise typer.Exit(code=1)


def ensure_msvc_linker():
    """Ensure the MSVC linker is available on Windows, or offer to install it."""
    if not IS_WINDOWS:
        return

    if shutil.which("link.exe"):
        return

    # Try to find via vswhere and add to PATH for this session
    vswhere = (
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
        / "Microsoft Visual Studio"
        / "Installer"
        / "vswhere.exe"
    )

    if vswhere.exists():
        result = subprocess.run(
            [
                str(vswhere),
                "-latest",
                "-products",
                "*",
                "-requires",
                "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                "-property",
                "installationPath",
            ],
            capture_output=True,
            text=True,
        )
        vs_path = result.stdout.strip() if result.returncode == 0 else ""
        if vs_path:
            # Try to find linker binary and add to PATH
            vc_tools = Path(vs_path) / "VC" / "Tools" / "MSVC"
            if vc_tools.exists():
                versions = sorted(vc_tools.iterdir(), reverse=True)
                for ver_dir in versions:
                    link_dir = ver_dir / "bin" / "Hostx64" / "x64"
                    if (link_dir / "link.exe").exists():
                        typer.echo(
                            f"📦 Found MSVC linker at {link_dir}, adding to PATH..."
                        )
                        os.environ["PATH"] = f"{link_dir};{os.environ.get('PATH', '')}"
                        return

            typer.echo(
                "⚠️  MSVC Build Tools are installed but 'link.exe' could not be located."
            )
            typer.echo(
                "   Try running from a Developer Command Prompt, or reinstall Build Tools."
            )
            raise typer.Exit(code=1)

    # Not installed at all
    typer.echo("❌ MSVC linker (link.exe) not found!")
    typer.echo("   This is required for compiling Tauri/Rust on Windows.")
    typer.echo(
        "   Run 'suzent setup-build-tools' to install, then restart your terminal."
    )

    if typer.confirm("   Would you like to install Build Tools now?"):
        # Delegate to the setup_build_tools command logic
        try:
            subprocess.run(["winget", "--version"], capture_output=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            typer.echo(
                "❌ 'winget' not found. Please install Build Tools manually from:"
            )
            typer.echo("   https://visualstudio.microsoft.com/visual-cpp-build-tools/")
            raise typer.Exit(code=1)

        typer.echo(
            "🛠️  Installing Visual Studio Build Tools (this may take several minutes)..."
        )
        install_result = subprocess.run(
            [
                "winget",
                "install",
                "--id",
                "Microsoft.VisualStudio.2022.BuildTools",
                "--override",
                "--passive --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended",
            ],
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        if install_result.returncode == 0:
            typer.echo(
                "✅ Build Tools installed! Please RESTART your terminal and run 'suzent start' again."
            )
        else:
            typer.echo(
                f"⚠️  Installation finished with code {install_result.returncode}."
            )
            typer.echo("   Please restart your terminal and try again.")
        raise typer.Exit(code=0)
    else:
        raise typer.Exit(code=1)


def get_pid_on_port(port: int) -> int | None:
    """Get the PID of the process *listening* on the specified port.

    Only listening sockets count. A busy server leaves dozens of accepted
    connections behind in TIME_WAIT/FIN_WAIT_2 when it dies, and those linger
    for up to a couple of minutes. `netstat` reports them with a local address
    of `127.0.0.1:<port>` and an owning PID of 0, so matching on the local
    address alone makes a long-dead backend look like it still holds the port.
    """
    try:
        if IS_WINDOWS:
            cmd = f"netstat -ano | findstr :{port}"
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            if result.returncode == 0 and result.stdout:
                for line in result.stdout.strip().splitlines():
                    parts = line.split()
                    # TCP <local> <foreign> LISTENING <pid>
                    if len(parts) < 5 or parts[3].upper() != "LISTENING":
                        continue
                    if not parts[1].endswith(f":{port}"):
                        continue
                    pid = int(parts[-1])
                    if pid:
                        return pid
        else:
            cmd = ["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout:
                return int(result.stdout.strip().split("\n")[0])
    except Exception:
        pass
    return None


def _wait_for_port_release(port: int, timeout: float = 2.0) -> bool:
    """Poll until no process owns `port`, returning False if it never frees up."""
    deadline = time.monotonic() + timeout
    while True:
        if get_pid_on_port(port) is None:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)


def _stop_backend(port: int) -> bool:
    """Stop the backend listening on `port`.

    Returns False when nothing was running. Exits with an error when a server
    responds but cannot be stopped.
    """
    if not _is_suzent_server_running("127.0.0.1", port, attempts=3):
        return False

    pid = get_pid_on_port(port)
    if not pid:
        typer.echo(
            f"⚠️  A Suzent server responded on port {port}, but no owning "
            "PID could be found to stop it."
        )
        raise typer.Exit(code=1)

    typer.echo(f"🛑 Stopping Suzent Server (PID {pid}) on port {port}...")
    try:
        kill_process(pid)
    except Exception as e:
        typer.echo(f"❌ Failed to stop server: {e}")
        raise typer.Exit(code=1)

    typer.echo("✅ Server stopped.")
    return True


def _stop_frontend() -> bool:
    """Stop the dev frontend this CLI started, if it is still running.

    Returns False when there is nothing of ours to stop. `start --dev` leaves
    the frontend running after the CLI returns, so `stop` has to end it too or
    it would outlive the backend it was serving.
    """
    process = _recorded_process("frontend")
    if process is None:
        _clear_pid("frontend")
        return False

    typer.echo(f"🛑 Stopping dev frontend (PID {process.pid})...")
    # `npm run dev` is only the launcher: Vite and the Tauri binary run as its
    # children and are what actually hold the port.
    doomed = [*_children_of(process), process]
    for victim in doomed:
        try:
            victim.kill()
        except psutil.Error:
            pass
    psutil.wait_procs(doomed, timeout=5)
    _clear_pid("frontend")
    typer.echo("✅ Dev frontend stopped.")
    return True


def kill_process(pid: int):
    """Kill a process by PID."""
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=True, shell=True)
    else:
        subprocess.run(["kill", "-9", str(pid)], check=True)


def _windows_ancestor_pids() -> set[int]:
    """Return the PID chain of the current process up to the root.

    `uv run suzent update` launches the Python interpreter under a `suzent.exe`
    shim (with `uv.exe`/`cmd.exe` above it). `os.getpid()` is the *Python* PID,
    so the `suzent.exe` that spawned this updater would otherwise be treated as a
    foreign process and killed — taking down the running update mid-flight.
    Excluding the whole ancestor chain prevents the updater from killing itself.
    """
    if not IS_WINDOWS:
        return set()
    my_pid = os.getpid()
    # Seed the walk from the *parent*: under `uv run` the leaf python.exe can be
    # missing from the WMI snapshot (PID-visibility race), but the parent is
    # reliably present, and the suzent.exe shim we must spare sits above it.
    parent_pid = os.getppid()
    pids: set[int] = {my_pid, parent_pid}
    script = (
        "$ErrorActionPreference = 'SilentlyContinue'; "
        "$map = @{}; "
        "Get-CimInstance Win32_Process | ForEach-Object { "
        "$map[$_.ProcessId] = $_.ParentProcessId }; "
        f"$pid_ = {parent_pid}; $seen = @(); "
        "while ($pid_ -and -not ($seen -contains $pid_)) { "
        "$seen += $pid_; $pid_ = $map[$pid_] }; "
        "$seen"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        try:
            pids.add(int(line.strip()))
        except ValueError:
            continue
    return pids


def _windows_app_suzent_pids(*, exclude_pids: set[int]) -> list[int]:
    """Return PIDs of running Suzent *app* processes (UI/backend), not updaters.

    Matching on the command line is race-free, unlike walking the process tree:
    `uv run suzent update` is itself a `suzent.exe`, and its `uv.exe` parents can
    drop out of a WMI snapshot, so the updater can't reliably exclude its own
    ancestors by PID alone. The app runs `suzent start`/`suzent.server`/the UI;
    the updater runs `suzent update` — so we skip any command line with 'update'.
    """
    if not IS_WINDOWS:
        return []
    script = (
        "$ErrorActionPreference = 'SilentlyContinue'; "
        "Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -eq 'suzent.exe' -and "
        "$_.CommandLine -notlike '*suzent update*' -and "
        "$_.CommandLine -notlike '* update*' "
        "} | ForEach-Object { $_.ProcessId }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
    )
    pids: list[int] = []
    for line in result.stdout.splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid not in exclude_pids:
            pids.append(pid)
    return pids


def _windows_suzent_backend_pids(root: Path, *, exclude_pids: set[int]) -> list[int]:
    if not IS_WINDOWS:
        return []
    root_text = str(root.resolve()).replace("'", "''")
    script = (
        "$ErrorActionPreference = 'SilentlyContinue'; "
        f"$root = '{root_text}'; "
        "$procs = Get-CimInstance Win32_Process | Where-Object { "
        "$_.CommandLine -like '*suzent.server*' -and "
        '$_.CommandLine -like "*$root*" '
        "}; "
        "$procs | ForEach-Object { $_.ProcessId }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
    )
    pids: list[int] = []
    for line in result.stdout.splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid not in exclude_pids:
            pids.append(pid)
    return pids


def _windows_suzent_launcher_pid(root: Path) -> int | None:
    """Return the running venv console-shim PID in our ancestor chain."""
    if not IS_WINDOWS:
        return None
    launcher = str((root / ".venv" / "Scripts" / "suzent.exe").resolve())
    escaped_launcher = launcher.replace("'", "''")
    script = (
        "$ErrorActionPreference = 'SilentlyContinue'; "
        f"$launcher = '{escaped_launcher}'; "
        "Get-CimInstance Win32_Process | Where-Object { "
        "$_.ExecutablePath -eq $launcher "
        "} | ForEach-Object { $_.ProcessId }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
    )
    ancestors = _windows_ancestor_pids()
    for line in result.stdout.splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid in ancestors:
            return pid

    try:
        invoked_as = Path(sys.argv[0]).resolve()
        expected_launcher = root / ".venv" / "Scripts" / "suzent.exe"
        if invoked_as == expected_launcher.resolve():
            return os.getpid()
    except OSError:
        pass
    return None


def _delegate_windows_update(root: Path, *, dev: bool) -> bool:
    """Relaunch updates outside the locked Windows console-script shim."""
    if not IS_WINDOWS or os.environ.get(_UPDATE_HELPER_ENV) == "1":
        return False

    launcher_pid = _windows_suzent_launcher_pid(root)
    wait_pid = launcher_pid if launcher_pid is not None else os.getpid()

    python_exe = root / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        raise RuntimeError(f"Python environment not found at {python_exe}")

    command = [
        str(python_exe),
        "-m",
        "suzent.cli.update_helper",
        "--wait-pid",
        str(wait_pid),
        "--root",
        str(root),
    ]
    if dev:
        command.append("--dev")

    helper_env = os.environ.copy()
    helper_env[_UPDATE_HELPER_ENV] = "1"
    creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    subprocess.Popen(
        command,
        cwd=root,
        env=helper_env,
        creationflags=creationflags,
    )
    typer.echo("  • Update will continue in a separate window...")
    return True


def _stop_windows_process(pid: int, label: str) -> None:
    typer.echo(f"  • Stopping running {label} (PID {pid})...")
    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)


def run_command(
    cmd: list[str], cwd: Path = None, check: bool = True, shell_on_windows: bool = False
):
    """Run a subprocess command with platform-specific adjustments."""
    use_shell = IS_WINDOWS and shell_on_windows
    subprocess.run(cmd, cwd=cwd, check=check, shell=use_shell)


def _log_path(name: str) -> Path:
    """Path of a detached process's log, alongside the service's own log."""
    return RUNTIME_DIR / f"{name}.log"


def _pid_path(name: str) -> Path:
    """Path of the record identifying a detached process."""
    return RUNTIME_DIR / f"{name}.pid"


def _record_pid(name: str, pid: int) -> None:
    """Remember a detached process so `stop` can end that exact process.

    The creation time is stored alongside the PID: the operating system reuses
    PIDs, and a stale record must never be enough to kill a stranger.
    """
    record: dict = {"pid": pid}
    try:
        record["created_at"] = psutil.Process(pid).create_time()
    except psutil.Error:
        pass
    path = _pid_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(record), encoding="utf-8")
    except OSError:
        # Losing the record only costs us the ability to stop the process by
        # name later; it must not fail the launch itself.
        pass


def _clear_pid(name: str) -> None:
    """Forget a detached process, whether or not a record exists."""
    try:
        _pid_path(name).unlink(missing_ok=True)
    except OSError:
        pass


def _recorded_process(name: str) -> psutil.Process | None:
    """Return the live process recorded for `name`, or None.

    Holding a well-known port is not proof of identity -- another project's
    dev server may be on 18080 -- so `stop` only ever ends a process this CLI
    recorded when it launched it.
    """
    try:
        record = json.loads(_pid_path(name).read_text(encoding="utf-8"))
        process = psutil.Process(int(record["pid"]))
    except (OSError, KeyError, TypeError, ValueError, psutil.Error):
        return None
    created = record.get("created_at")
    try:
        if created is not None and abs(process.create_time() - created) > 1.0:
            return None  # The PID was recycled by an unrelated process.
    except psutil.Error:
        return None
    return process


def _children_of(process: psutil.Process) -> list[psutil.Process]:
    """Every descendant of `process` that is still alive."""
    try:
        return process.children(recursive=True)
    except psutil.Error:
        return []


def _open_log(name: str):
    """Open a detached process's log for appending, creating its directory."""
    path = _log_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a", encoding="utf-8", errors="replace")
    handle.write(f"\n===== {name} started {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
    handle.flush()
    return handle


def _launch_detached(
    cmd: list[str],
    *,
    log_name: str,
    cwd: Path | None = None,
    env: dict | None = None,
) -> subprocess.Popen:
    """Start `cmd` so it outlives this CLI invocation, logging to `log_name`.

    The process gets its own session (POSIX) or its own console with no window
    (Windows), so closing the terminal -- or this command returning -- leaves it
    running, and nothing pops up on screen. Its output goes to a log file rather
    than a terminal nobody is watching; `suzent logs` reads it back.

    On Windows this is CREATE_NO_WINDOW rather than DETACHED_PROCESS: a detached
    process has no console at all, so the first console descendant (`npm`, then
    `node` and `cargo`) allocates a fresh one -- and a fresh console comes with a
    visible window. A windowless console is inherited quietly by the whole tree.
    The two flags are mutually exclusive, and this one still leaves the child
    outside this terminal's console, which is what keeps it alive afterwards.
    """
    kwargs: dict = {"cwd": cwd, "env": env, "stdin": subprocess.DEVNULL}
    if IS_WINDOWS:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        kwargs["start_new_session"] = True
    handle = _open_log(log_name)
    try:
        process = subprocess.Popen(cmd, stdout=handle, stderr=handle, **kwargs)
    finally:
        # The child holds its own duplicate of the descriptor.
        handle.close()
    _record_pid(log_name, process.pid)
    return process


_LOG_FLAGS = {"backend": "", "frontend": " --frontend", "desktop": " --desktop"}


def _report_detached(port: int, *, log_name: str) -> None:
    """Print the confirmation every detached start path ends with.

    Both the packaged desktop app and the dev pair report themselves the same
    way, so `suzent start`/`restart` reads identically whichever mode you are in.
    `log_name` is the log a failure would land in -- the one worth reading --
    which is the desktop app's own log in packaged mode and the frontend's in
    dev mode.
    """
    if _wait_until_serving(port, timeout=_READY_TIMEOUT):
        typer.echo(f"  ✅ Suzent is running at http://127.0.0.1:{port}")
    else:
        typer.echo(
            f"  ⚠️  No backend answered on port {port} within "
            f"{_READY_TIMEOUT:.0f}s; it may still be starting, or it failed."
        )
    typer.echo(f"     Logs:  suzent logs{_LOG_FLAGS[log_name]} -f")
    typer.echo("     Stop:  suzent stop")


def _wait_until_serving(port: int, timeout: float = 60.0) -> bool:
    """Block until a Suzent backend answers on ``port``, or the timeout passes."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_suzent_server_running("127.0.0.1", port):
            return True
        time.sleep(0.5)
    return False


def _open_when_ready(port: int, open_browser: bool, timeout: float = 60.0) -> bool:
    """Wait for the backend, then point the browser at it. Returns readiness."""
    url = f"http://127.0.0.1:{port}/"
    if not _wait_until_serving(port, timeout):
        typer.echo(f"WARNING  Backend did not answer on {url} within {timeout:.0f}s.")
        typer.echo("   Check it with: suzent service status")
        return False
    typer.echo(f"OK  Suzent is serving at {url}")
    if open_browser:
        webbrowser.open(url)
    return True


def _open_in_background(port: int, timeout: float = 60.0) -> None:
    """Open the browser once the server answers, without blocking the caller.

    Used by --foreground, where this process goes on to babysit the server and
    cannot sit in a wait loop. The thread is a daemon so Ctrl-C still exits.
    """

    def _wait() -> None:
        if _wait_until_serving(port, timeout):
            webbrowser.open(f"http://127.0.0.1:{port}/")

    threading.Thread(target=_wait, daemon=True).start()


def _web_foreground(port: int, host: str, debug: bool, open_browser: bool) -> None:
    """Serve the UI from a throwaway backend tied to this terminal.

    The supported path is the background service; this exists for development
    and for a one-off on a non-default port or binding, where a login-persistent
    service would be the wrong thing to install.
    """
    if host not in ("127.0.0.1", "localhost", "::1"):
        # A remote browser is a remote caller: AuthBoundaryMiddleware will
        # demand a device token for every request it makes. Say so up front
        # rather than letting the user meet a wall of 401s.
        typer.echo(
            f"WARNING  Binding {host} exposes the API beyond this machine. Remote "
            "browsers must carry a host-scope token; see "
            "docs/03-developing/web-ui.md."
        )

    env = os.environ.copy()
    env["SUZENT_PORT"] = str(port)
    env["SUZENT_HOST"] = host
    cmd = [sys.executable, "-m", "suzent.server"]
    if debug:
        cmd.append("--debug")

    typer.echo(f"Serving Suzent at http://{host}:{port}/")
    proc = subprocess.Popen(cmd, cwd=get_project_root(), env=env)
    if open_browser:
        _open_in_background(port)
    try:
        proc.wait()
    except KeyboardInterrupt:
        typer.echo("Stopping...")
        _terminate_process_gracefully(proc)


def _terminate_process_gracefully(process: subprocess.Popen, timeout: float = 5.0):
    """Attempt graceful child-process shutdown, then escalate if needed."""
    if process.poll() is not None:
        return

    # First attempt: signal for graceful shutdown
    try:
        if IS_WINDOWS:
            ctrl_break = getattr(signal, "CTRL_BREAK_EVENT", None)
            if ctrl_break is not None:
                process.send_signal(ctrl_break)
            else:
                process.terminate()
        else:
            process.send_signal(signal.SIGINT)
        process.wait(timeout=timeout)
        return
    except Exception:
        pass

    # Second attempt: terminate
    if process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=timeout)
            return
        except Exception:
            pass

    # Last attempt: hard kill
    if process.poll() is None:
        try:
            process.kill()
            process.wait(timeout=2)
        except Exception:
            pass


def _ensure_npm_deps(root: Path):
    """Install npm deps in frontend/ and src-tauri/ if node_modules is stale."""
    for npm_dir, label in [
        (root / "frontend", "frontend"),
        (root / "src-tauri", "tauri"),
    ]:
        nm = npm_dir / "node_modules"
        pkg = npm_dir / "package.json"
        needs_install = not nm.exists() or (
            pkg.exists() and pkg.stat().st_mtime > nm.stat().st_mtime
        )
        if needs_install:
            typer.echo(f"    Installing {label} dependencies...")
            run_command(["npm", "install"], cwd=npm_dir, shell_on_windows=True)


def register_commands(app: typer.Typer):
    """Register top-level commands onto the app."""

    @app.command()
    def start(
        port: int = typer.Option(DEFAULT_PORT, help="Port for the backend to run on"),
        debug: bool = typer.Option(False, "--debug", help="Run server in debug mode"),
        dev: bool = typer.Option(
            False,
            "--dev",
            help="Force developer mode (backend in debug + Tauri dev), skipping the pre-built UI binary",
        ),
        docs: bool = typer.Option(
            False, "--docs", help="Run documentation server instead of app"
        ),
    ):
        """Start the Suzent development environment."""
        root = get_project_root()

        if docs:
            typer.echo("📚 Starting Documentation Server...")
            return

        interrupted_update = _interrupted_update_message(root)
        if interrupted_update is not None:
            typer.echo(f"❌ {interrupted_update}")
            raise typer.Exit(code=1)

        typer.echo("🚀 Starting SUZENT...")
        _notify_update_available(root)

        if not dev and _read_update_channel(root) == _DEV_CHANNEL:
            typer.echo("  • Development update channel active; starting in dev mode.")
            dev = True

        # --dev implies running the backend in debug mode.
        if dev:
            debug = True

        ui_bin = None if dev else _get_ui_binary(root)
        if ui_bin:
            # Pre-built binary manages both backend and webview internally, and
            # has its own window, so nothing useful reaches this terminal --
            # launch it detached instead of holding the prompt hostage for the
            # whole life of the desktop app.
            typer.echo(f"  • Launching UI binary ({ui_bin.name})...")
            try:
                _launch_detached(
                    [str(_macos_launch_target(root, ui_bin))],
                    log_name="desktop",
                    env=_ui_launch_env(
                        {"SUZENT_DIR": str(root), "SUZENT_PORT": str(port)}
                    ),
                )
            except OSError as error:
                typer.echo(f"  ❌ Could not launch the desktop app: {error}")
                raise typer.Exit(code=1)
            _report_detached(port, log_name="desktop")
            return

        # ── Developer fallback: tauri dev ────────────────────────────────────
        if dev:
            typer.echo("  * Starting in developer mode (--dev).")
        else:
            typer.echo("  No pre-built UI binary found - starting in developer mode.")
            typer.echo("     Run 'suzent update' to download the binary.")
        ensure_cargo_in_path()
        ensure_msvc_linker()

        backend_running = _is_suzent_server_running("127.0.0.1", port, attempts=3)
        ports_to_check = [(DEV_FRONTEND_PORT, "Frontend")]
        if not backend_running:
            ports_to_check.insert(0, (port, "Backend"))
        elif not dev:
            typer.echo(
                f"  ✅ Backend already running on http://127.0.0.1:{port}; reusing it."
            )

        for busy_port, name in ports_to_check:
            pid = get_pid_on_port(busy_port)
            if pid:
                typer.echo(
                    f"\n⚠️  {name} Port {busy_port} is already in use by PID {pid}."
                )
                if typer.confirm("   Do you want to kill this process to continue?"):
                    typer.echo(f"   🔪 Killing PID {pid}...")
                    try:
                        kill_process(pid)
                        typer.echo("   ✅ Process killed.")
                    except Exception as e:
                        typer.echo(f"   ❌ Failed to kill process: {e}")
                        raise typer.Exit(code=1)
                else:
                    typer.echo("   ❌ Startup aborted.")
                    raise typer.Exit(code=1)

        if dev and backend_running:
            pid = get_pid_on_port(port)
            if not pid:
                typer.echo(
                    "  ❌ Dev mode found an existing Suzent backend but could not "
                    "identify its PID. Run 'suzent stop' and retry."
                )
                raise typer.Exit(code=1)
            typer.echo(
                f"  • Restarting existing backend (PID {pid}) for a clean dev session..."
            )
            try:
                kill_process(pid)
            except Exception as error:
                typer.echo(f"  ❌ Failed to restart existing backend: {error}")
                raise typer.Exit(code=1)
            if not _wait_for_port_release(port):
                typer.echo("  ❌ Existing backend did not release its port.")
                raise typer.Exit(code=1)
            backend_running = False

        backend_env = os.environ.copy()
        backend_env["SUZENT_PORT"] = str(port)
        if dev:
            backend_env["SUZENT_DEV_MODE"] = "1"

        if backend_running:
            typer.echo("  • Skipping backend startup.")
        else:
            typer.echo("  • Starting backend...")
            backend_cmd = [sys.executable, "-m", "suzent.server"]
            if debug:
                backend_cmd.append("--debug")
            _launch_detached(backend_cmd, log_name="backend", cwd=root, env=backend_env)

        typer.echo("  • Starting frontend (Tauri dev)...")
        _ensure_npm_deps(root)
        # The frontend is detached too, so a Tauri or Vite crash no longer takes
        # the backend down with it -- the failure lands in the frontend log and
        # the backend keeps serving.
        frontend_cmd = ["npm", "run", "dev"]
        if IS_WINDOWS:
            # `npm` is a shell script; without a console it needs cmd to resolve.
            frontend_cmd = ["cmd", "/c", *frontend_cmd]
        _launch_detached(frontend_cmd, log_name="frontend", cwd=root / "src-tauri")
        _report_detached(port, log_name="frontend")

    @app.command()
    def serve(
        host: str = typer.Option("127.0.0.1", help="Host to bind to"),
        port: int = typer.Option(DEFAULT_PORT, help="Port to bind to"),
        debug: bool = typer.Option(False, "--debug", help="Run in debug mode"),
        dev: bool = typer.Option(
            False,
            "--dev",
            help="Compatibility flag; capability discovery still writes to "
            "the local user-data overlay",
        ),
    ):
        """Start the Suzent backend server (headless/standalone mode)."""
        if _is_suzent_server_running(host, port):
            typer.echo(
                f"✅ Suzent Server is already running on http://{host}:{port}; "
                "reusing it."
            )
            return

        typer.echo(f"🚀 Starting Suzent Server on {host}:{port}...")

        env = os.environ.copy()
        env["SUZENT_HOST"] = host
        env["SUZENT_PORT"] = str(port)
        env["SUZENT_DEV_MODE"] = "1"

        # Launch the server module using the same python interpreter
        cmd = [sys.executable, "-m", "suzent.server"]
        if debug:
            cmd.append("--debug")

        try:
            # Keep a process handle so Ctrl+C can shut down the child reliably.
            # NOTE: Do NOT use CREATE_NEW_PROCESS_GROUP on Windows here.
            # It can prevent Ctrl+C from propagating naturally from the console,
            # leaving the backend process alive after the CLI is interrupted.
            process = subprocess.Popen(cmd, env=env)
            return_code = process.wait()

            # 130 = terminated via SIGINT/Ctrl+C on many platforms.
            if return_code not in (0, 130):
                typer.echo(f"❌ Server failed with exit code {return_code}")
                raise typer.Exit(code=1)
        except KeyboardInterrupt:
            typer.echo("\n🛑 Stopping server...")
            try:
                _terminate_process_gracefully(process)
            except Exception:
                pass
            typer.echo("🛑 Server stopped.")
        except Exception as e:
            typer.echo(f"❌ Server failed: {e}")
            raise typer.Exit(code=1)

    @app.command()
    def web(
        open_browser: bool = typer.Option(
            True, "--open/--no-open", help="Open the UI in the default browser"
        ),
        install: bool = typer.Option(
            None,
            "--install/--no-install",
            help="Install the background service when it is not installed yet",
        ),
        foreground: bool = typer.Option(
            False,
            "--foreground",
            help="Run a throwaway server in this terminal instead of using the service",
        ),
        port: int = typer.Option(
            DEFAULT_PORT, "--port", "-p", help="Port to serve on (--foreground only)"
        ),
        host: str = typer.Option(
            "127.0.0.1",
            "--host",
            help="Address to bind (--foreground only). Anything but loopback "
            "exposes the API to the network",
        ),
        debug: bool = typer.Option(
            False, "--debug", help="Run the server in debug mode (--foreground only)"
        ),
    ):
        """Open Suzent in the browser.

        The web UI is a route set on the ordinary Suzent backend, so there is no
        separate web server to run: whatever already serves the API serves the
        UI too. This command only makes sure *something* is serving -- preferring
        the background service, which outlives this terminal and starts at login
        -- and then hands the browser a URL.
        """
        from suzent.webui import webui_available

        if not webui_available():
            typer.echo("ERROR  No web UI is built into this install.")
            typer.echo("   Build it with: python scripts/build_webui.py")
            raise typer.Exit(code=1)

        if foreground:
            _web_foreground(port, host, debug, open_browser)
            return

        from suzent.service import get_service_controller

        controller = get_service_controller()
        status = controller.status()

        if status.running:
            if not status.ready:
                typer.echo("The Suzent service is still starting...")
            ready = _open_when_ready(status.port or DEFAULT_PORT, open_browser)
            raise typer.Exit(code=0 if ready else 1)

        # The service is not up, but something else may already be serving --
        # `suzent serve`, or the backend the desktop app launched. Reuse it
        # rather than starting a second backend that would lose the port race.
        if _is_suzent_server_running("127.0.0.1", port):
            typer.echo(f"OK  Suzent is already serving at http://127.0.0.1:{port}/")
            if open_browser:
                webbrowser.open(f"http://127.0.0.1:{port}/")
            return

        if status.installed:
            typer.echo("Starting the Suzent background service...")
            try:
                controller.start()
            except Exception as exc:
                typer.echo(f"ERROR  Could not start the service: {exc}")
                raise typer.Exit(code=1) from exc
            ready = _open_when_ready(status.port or DEFAULT_PORT, open_browser)
            raise typer.Exit(code=0 if ready else 1)

        # Nothing is installed and nothing is running.
        if install is None:
            install = sys.stdin.isatty() and typer.confirm(
                "No Suzent background service is installed. Install it now so the "
                f"UI is always available at http://127.0.0.1:{DEFAULT_PORT}/ ?",
                default=True,
            )
        if not install:
            typer.echo("No Suzent backend is running. Either:")
            typer.echo("  suzent service install   # start at login, always available")
            typer.echo("  suzent web --foreground  # one-off server in this terminal")
            raise typer.Exit(code=1)

        typer.echo("Installing the Suzent background service...")
        try:
            controller.install(start=True)
        except Exception as exc:
            typer.echo(f"ERROR  Could not install the service: {exc}")
            raise typer.Exit(code=1) from exc
        typer.echo("OK  Service installed; it will start automatically at login.")
        ready = _open_when_ready(DEFAULT_PORT, open_browser)
        raise typer.Exit(code=0 if ready else 1)

    @app.command()
    def stop(
        port: int = typer.Option(DEFAULT_PORT, help="Port the backend is running on"),
    ):
        """Stop a running Suzent backend server and any detached dev frontend."""
        stopped_backend = _stop_backend(port)
        stopped_frontend = _stop_frontend()
        if not stopped_backend and not stopped_frontend:
            typer.echo(f"No Suzent server running on http://127.0.0.1:{port}.")

    @app.command()
    def logs(
        frontend: bool = typer.Option(
            False, "--frontend", help="Read the dev frontend log instead."
        ),
        desktop: bool = typer.Option(
            False, "--desktop", help="Read the packaged desktop app log instead."
        ),
        follow: bool = typer.Option(
            False, "--follow", "-f", help="Stream new lines as they are written."
        ),
        lines: int = typer.Option(200, "--lines", "-n", help="Lines to show first."),
    ):
        """Show the log of a detached Suzent process."""
        if frontend and desktop:
            typer.echo("❌ Pick one of --frontend or --desktop.")
            raise typer.Exit(code=1)
        name = "frontend" if frontend else "desktop" if desktop else "backend"
        path = _log_path(name)
        if not path.exists():
            typer.echo(f"No {name} log yet at {path}.")
            raise typer.Exit(code=1)

        typer.echo(f"── {path} ──")
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            tail = handle.readlines()[-lines:] if lines > 0 else []
            for line in tail:
                typer.echo(line.rstrip("\n"))
            if not follow:
                return
            handle.seek(0, io.SEEK_END)
            try:
                while True:
                    line = handle.readline()
                    if line:
                        typer.echo(line.rstrip("\n"))
                    else:
                        time.sleep(0.25)
            except KeyboardInterrupt:
                pass

    @app.command()
    def restart(
        port: int = typer.Option(DEFAULT_PORT, help="Port the backend is running on"),
        debug: bool = typer.Option(False, "--debug", help="Run server in debug mode"),
        dev: bool = typer.Option(
            False,
            "--dev",
            help="Force developer mode (backend in debug + Tauri dev), skipping the pre-built UI binary",
        ),
    ):
        """Stop a running Suzent backend and dev frontend, then start again."""
        if _stop_backend(port):
            if not _wait_for_port_release(port):
                typer.echo(f"❌ Port {port} was not released; restart aborted.")
                raise typer.Exit(code=1)
        else:
            typer.echo(
                f"No Suzent server running on http://127.0.0.1:{port}; starting one."
            )

        # A dev frontend from the previous session still holds its port, and
        # `start` would stop to ask about it -- which a restart should never
        # need to do about a process Suzent itself left running.
        _stop_frontend()

        start(port=port, debug=debug, dev=dev, docs=False)

    @app.command()
    def ui(
        port: int = typer.Option(
            DEFAULT_PORT, "--port", "-p", help="Backend port to connect to"
        ),
    ):
        """Start only the Tauri frontend (assumes backend is already running)."""
        root = get_project_root()

        typer.echo(f"🖥️  Starting SUZENT UI (connecting to backend on port {port})...")
        _notify_update_available(root)

        ui_bin = _get_ui_binary(root)
        if ui_bin:
            env = _ui_launch_env({"SUZENT_DIR": str(root), "SUZENT_PORT": str(port)})
            try:
                _launch_detached(
                    [str(_macos_launch_target(root, ui_bin))],
                    log_name="desktop",
                    env=env,
                )
            except OSError as error:
                typer.echo(f"  ❌ Could not launch the desktop app: {error}")
                raise typer.Exit(code=1)
            _report_detached(port, log_name="desktop")
            return

        ensure_cargo_in_path()
        ensure_msvc_linker()
        _ensure_npm_deps(root)

        env = os.environ.copy()
        env["SUZENT_PORT"] = str(port)

        frontend_cmd = ["npm", "run", "dev"]
        if IS_WINDOWS:
            frontend_cmd = ["cmd", "/c", *frontend_cmd]
        _launch_detached(
            frontend_cmd, log_name="frontend", cwd=root / "src-tauri", env=env
        )
        _report_detached(port, log_name="frontend")

    @app.command()
    def doctor():
        """Check if all requirements are installed and configured correctly."""
        typer.echo("🩺 QA Checking System Health...")

        # Refresh PATH from registry so newly-installed tools are found
        if IS_WINDOWS:
            machine_path = os.environ.get("Path", "")
            try:
                import winreg

                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                ) as key:
                    machine_path = winreg.QueryValueEx(key, "Path")[0]
            except Exception:
                pass

            user_path = ""
            try:
                import winreg

                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                    user_path = winreg.QueryValueEx(key, "Path")[0]
            except Exception:
                pass

            if machine_path or user_path:
                os.environ["PATH"] = f"{machine_path};{user_path}"

        ensure_cargo_in_path()

        checks = {
            "git": ["git", "--version"],
            "node": ["node", "--version"],
            "npm": ["npm", "--version"],
            "cargo": ["cargo", "--version"],
            "rustc": ["rustc", "--version"],
            "uv": ["uv", "--version"],
        }

        if IS_WINDOWS:
            checks["linker"] = ["where", "link.exe"]

        def _check_vswhere() -> bool:
            """Try to find VC tools via vswhere as a fallback for missing linker."""
            vswhere = (
                Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
                / "Microsoft Visual Studio/Installer/vswhere.exe"
            )
            if not vswhere.exists():
                return False
            vw_res = subprocess.run(
                [
                    str(vswhere),
                    "-latest",
                    "-products",
                    "*",
                    "-requires",
                    "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                    "-property",
                    "installationPath",
                ],
                capture_output=True,
                text=True,
            )
            return vw_res.returncode == 0 and bool(vw_res.stdout.strip())

        all_ok = True
        for name, cmd in checks.items():
            try:
                is_script = name in ["npm", "uv"]
                use_shell = IS_WINDOWS and is_script
                res = subprocess.run(
                    cmd, capture_output=True, text=True, shell=use_shell
                )

                if res.returncode == 0:
                    typer.echo(
                        f"  ✅ {name:<10} : {res.stdout.strip().splitlines()[0]}"
                    )
                elif name == "linker" and IS_WINDOWS and _check_vswhere():
                    typer.echo(f"  ✅ {name:<10} : Found via vswhere (PATH missing)")
                else:
                    typer.echo(f"  ❌ {name:<10} : Not found or error")
                    all_ok = False
            except FileNotFoundError:
                if name == "linker" and IS_WINDOWS and _check_vswhere():
                    typer.echo(f"  ✅ {name:<10} : Found via vswhere (PATH missing)")
                else:
                    typer.echo(f"  ❌ {name:<10} : Not installed")
                    all_ok = False

        try:
            ripgrep = subprocess.run(
                ["rg", "--version"], capture_output=True, text=True
            )
            if ripgrep.returncode == 0:
                typer.echo(
                    f"  ✅ {'ripgrep':<10} : "
                    f"{ripgrep.stdout.strip().splitlines()[0]} (optional accelerator)"
                )
            else:
                raise FileNotFoundError
        except (FileNotFoundError, OSError):
            if IS_WINDOWS:
                install_hint = "winget install --id BurntSushi.ripgrep.MSVC"
            elif sys.platform == "darwin":
                install_hint = "brew install ripgrep"
            else:
                install_hint = "install ripgrep with your system package manager"
            typer.echo(
                f"  ⚠️  {'ripgrep':<10} : Optional accelerator not installed; "
                f"grep_search will use Python fallback. To enable it: {install_hint}"
            )

        if all_ok:
            typer.echo("\n✨ System is ready for Suzent!")
        else:
            typer.echo("\n⚠️  Some tools are missing. Please install them.")

    def _kill_other_suzent_processes(root: Path) -> None:
        """Terminate running Suzent UI/backend processes before dependency sync."""
        if not IS_WINDOWS:
            return
        # Exclude the whole ancestor chain, not just our PID: the running updater
        # is the Python interpreter, but its parent suzent.exe shim would
        # otherwise be killed as a "foreign" suzent process — terminating us.
        exclude_pids = _windows_ancestor_pids()
        exclude_pids.add(os.getpid())

        try:
            for pid in _windows_app_suzent_pids(exclude_pids=exclude_pids):
                _stop_windows_process(pid, "suzent process")
        except Exception:
            pass

        try:
            backend_pids = _windows_suzent_backend_pids(root, exclude_pids=exclude_pids)
            for pid in backend_pids:
                _stop_windows_process(pid, "suzent backend")
            if backend_pids:
                time.sleep(1)
        except Exception:
            pass

    def _git_text(root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def _restore_checkout(root: Path, branch: str, commit: str) -> None:
        if not commit:
            return
        try:
            typer.echo(f"  • Rolling source back to {commit}...")
            if branch:
                run_command(["git", "checkout", branch], cwd=root)
                run_command(["git", "reset", "--hard", commit], cwd=root)
            else:
                run_command(["git", "checkout", "--detach", commit], cwd=root)
            run_command(_backend_sync_args(root), cwd=root, shell_on_windows=True)
        except subprocess.CalledProcessError:
            typer.echo("  ⚠️  Automatic rollback was incomplete; inspect the checkout.")

    def _checkout_update_target(root: Path, *, dev: bool, release_tag: str) -> None:
        if dev:
            run_command(["git", "fetch", "origin", "main"], cwd=root)
            run_command(["git", "switch", "main"], cwd=root)
            run_command(["git", "merge", "--ff-only", "origin/main"], cwd=root)
            return
        run_command(["git", "fetch", "origin", "tag", release_tag], cwd=root)
        run_command(["git", "checkout", "--detach", release_tag], cwd=root)

    def _restore_stashed_changes(root: Path, stashed: bool) -> None:
        if not stashed:
            return
        try:
            run_command(["git", "stash", "pop"], cwd=root)
        except subprocess.CalledProcessError:
            typer.echo("  ⚠️  Stashed changes need manual conflict resolution.")

    def _run_update(
        *,
        dev: bool = False,
        relaunch: Path | None = None,
        headless: bool = False,
    ) -> None:
        root = get_project_root()

        if not dev and _is_development_workspace(root):
            typer.echo(
                "  • Source checkout detected; using the development update channel."
            )
            dev = True

        channel = _DEV_CHANNEL if dev else _STABLE_CHANNEL
        typer.echo(f"🔄 Updating Suzent ({channel} channel)...")

        if dev and _delegate_windows_update(root, dev=True):
            return

        release_tag = ""
        if not dev:
            try:
                release_tag = str(_fetch_latest_release().get("tag_name", ""))
            except Exception as error:
                typer.echo(f"  ❌ Could not resolve the latest stable release: {error}")
                raise typer.Exit(code=1)
            if not re.fullmatch(r"v\d+\.\d+\.\d+", release_tag):
                typer.echo(
                    f"  ❌ Invalid stable release tag: {release_tag or 'missing'}"
                )
                raise typer.Exit(code=1)
            _delegate_installer_update(
                root,
                release_tag=release_tag,
                relaunch=relaunch,
                headless=headless,
            )
            return

        try:
            old_commit = _git_text(root, "rev-parse", "HEAD")
            old_branch = _git_text(root, "branch", "--show-current")
        except subprocess.CalledProcessError:
            typer.echo("  ❌ Suzent installation is not a valid Git checkout.")
            raise typer.Exit(code=1)

        # Self-heal installs dirtied by the old behavior, where runtime model
        # discovery wrote into the tracked config/capabilities/ files and made
        # every `git pull` conflict. Those writes now go to the user data dir,
        # so any local change here is stale runtime noise — discard it so the
        # pull is clean. Curated updates ship from the repo and land normally.
        try:
            run_command(
                ["git", "checkout", "--", "config/capabilities"],
                cwd=root,
            )
        except subprocess.CalledProcessError:
            pass  # No such path / nothing to discard — fine.

        target_label = "origin/main" if dev else release_tag
        typer.echo(f"  • Updating source to {target_label}...")
        stashed_changes = False
        if not dev:
            try:
                has_local_changes = bool(_git_text(root, "status", "--porcelain"))
            except subprocess.CalledProcessError:
                has_local_changes = False
            if has_local_changes:
                if not typer.confirm(
                    "  Stable updates require a clean checkout. Stash local changes?"
                ):
                    typer.echo("  ❌ Update aborted.")
                    raise typer.Exit(code=1)
                run_command(["git", "stash", "--include-untracked"], cwd=root)
                stashed_changes = True
        try:
            _checkout_update_target(root, dev=dev, release_tag=release_tag)
        except subprocess.CalledProcessError:
            if stashed_changes:
                typer.echo("  ❌ Source update failed. Restoring local changes...")
                _restore_stashed_changes(root, stashed_changes)
                raise typer.Exit(code=1)
            typer.echo(
                "  ⚠️  Source update failed. This is usually due to local file changes."
            )
            if typer.confirm("  Stash local changes and retry?"):
                typer.echo("  🔄 Stashing local changes...")
                run_command(["git", "stash", "--include-untracked"], cwd=root)
                stashed_changes = True
                try:
                    _checkout_update_target(
                        root,
                        dev=dev,
                        release_tag=release_tag,
                    )
                except subprocess.CalledProcessError:
                    typer.echo("  ❌ Source update still failed. Restoring stash...")
                    _restore_stashed_changes(root, stashed_changes)
                    raise typer.Exit(code=1)
            else:
                typer.echo("  ❌ Update aborted.")
                raise typer.Exit(code=1)

        if not dev:
            checked_out_version = _normalize_version_tag(_current_version(root))
            expected_version = _normalize_version_tag(release_tag)
            if checked_out_version != expected_version:
                typer.echo(
                    "  ❌ Stable source/version mismatch: "
                    f"expected {expected_version}, found {checked_out_version}."
                )
                _restore_checkout(root, old_branch, old_commit)
                _restore_stashed_changes(root, stashed_changes)
                raise typer.Exit(code=1)

        # Restore tracked resource placeholders (may be missing from stale clones)
        typer.echo("  • Ensuring resource files...")
        try:
            run_command(
                [
                    "git",
                    "checkout",
                    "HEAD",
                    "--",
                    "src-tauri/resources/suzent.cmd",
                    "src-tauri/resources/suzent",
                ],
                cwd=root,
            )
        except subprocess.CalledProcessError:
            # Files may not exist in this branch — create placeholders
            resources_dir = root / "src-tauri" / "resources"
            resources_dir.mkdir(parents=True, exist_ok=True)
            cmd_shim = resources_dir / "suzent.cmd"
            if not cmd_shim.exists():
                cmd_shim.write_text("@echo off\r\nREM Placeholder\r\n")
            sh_shim = resources_dir / "suzent"
            if not sh_shim.exists():
                sh_shim.write_text("#!/bin/sh\n# Placeholder\n")

        sync_args = _backend_sync_args(root)
        sync_label = " ".join(sync_args)
        typer.echo(f"  • Updating backend dependencies ({sync_label})...")
        # On Windows, the running suzent.exe in .venv/Scripts/ is locked by the OS.
        # uv sync will fail trying to remove it. Workaround: kill other suzent
        # processes first, then rename the exe out of the way — Windows allows
        # renaming a running executable even though it can't delete it.
        # Retry the rename a few times to handle transient AV scanner locks (error 32).
        _renamed_exe: Path | None = None
        _kill_other_suzent_processes(root)
        if IS_WINDOWS:
            venv_exe = root / ".venv" / "Scripts" / "suzent.exe"
            bak_exe = root / ".venv" / "Scripts" / "suzent.exe.bak"
            if venv_exe.exists():
                # Remove any previous leftover .bak
                if bak_exe.exists():
                    try:
                        bak_exe.unlink()
                    except OSError:
                        pass
                for attempt in range(4):
                    try:
                        venv_exe.rename(bak_exe)
                        _renamed_exe = bak_exe
                        break
                    except OSError:
                        if attempt < 3:
                            time.sleep(1)

        try:
            run_command(sync_args, cwd=root, shell_on_windows=True)
        except subprocess.CalledProcessError:
            typer.echo(f"  ❌ Backend dependency update failed ({sync_label}).")
            # Try to restore the renamed exe so the CLI still works
            if _renamed_exe and _renamed_exe.exists():
                try:
                    target = root / ".venv" / "Scripts" / "suzent.exe"
                    if not target.exists():
                        _renamed_exe.rename(target)
                except OSError:
                    pass
            _restore_checkout(root, old_branch, old_commit)
            _restore_stashed_changes(root, stashed_changes)
            raise typer.Exit(code=1)

        # Clean up the .bak file (may still be locked until this process exits)
        if _renamed_exe and _renamed_exe.exists():
            try:
                _renamed_exe.unlink()
            except OSError:
                pass  # Will be cleaned up on next update

        # Update Playwright browser (non-fatal)
        typer.echo("  • Updating Playwright browser...")
        try:
            run_command(
                ["uv", "run", "playwright", "install", "chromium"],
                cwd=root,
                shell_on_windows=True,
            )
        except subprocess.CalledProcessError:
            typer.echo(
                "  ⚠️  Playwright browser update failed (will retry on first use)."
            )

        if dev:
            typer.echo("  • Updating frontend dependencies from lockfiles...")
            try:
                run_command(
                    ["npm", "ci"],
                    cwd=root / "frontend",
                    shell_on_windows=True,
                )
                run_command(
                    ["npm", "ci"],
                    cwd=root / "src-tauri",
                    shell_on_windows=True,
                )
            except subprocess.CalledProcessError:
                typer.echo("  ❌ Development frontend dependency update failed.")
                _restore_checkout(root, old_branch, old_commit)
                _restore_stashed_changes(root, stashed_changes)
                raise typer.Exit(code=1)
        else:
            typer.echo("  • Installing matching release UI binary...")
            if not _update_ui_binary(root, release_tag):
                typer.echo("  ❌ Matching release UI download failed; update aborted.")
                _restore_checkout(root, old_branch, old_commit)
                _restore_stashed_changes(root, stashed_changes)
                raise typer.Exit(code=1)

        _write_update_channel(root, channel)
        # The stable path returns earlier and lets the standalone updater repair
        # shortcuts; this is the development channel's equivalent.
        _refresh_shortcuts(root)
        if dev:
            _restore_stashed_changes(root, stashed_changes)
        elif stashed_changes:
            typer.echo(
                "  • Local changes remain safely stored in Git stash; "
                "reapply them only in a development checkout."
            )
        typer.echo(f"\n✨ Suzent successfully updated on the {channel} channel!")

    @app.command()
    def update(
        dev: bool = typer.Option(
            False,
            "--dev",
            help="Update to origin/main and run the matching development frontend.",
        ),
        relaunch: Path | None = typer.Option(
            None,
            "--relaunch",
            hidden=True,
        ),
        headless: bool = typer.Option(
            False,
            "--headless",
            help="Run the standalone updater in the terminal without a window.",
        ),
    ):
        """Update Suzent to the latest version."""
        _run_update(dev=dev, relaunch=relaunch, headless=headless)

    @app.command()
    def upgrade(
        dev: bool = typer.Option(
            False,
            "--dev",
            help="Update to origin/main and run the matching development frontend.",
        ),
        headless: bool = typer.Option(
            False,
            "--headless",
            help="Run the standalone updater in the terminal without a window.",
        ),
    ):
        """Alias for `update`."""
        typer.echo(
            "`suzent upgrade` is supported; `suzent update` is the primary command."
        )
        _run_update(dev=dev, headless=headless)

    @app.command()
    def repair(
        headless: bool = typer.Option(
            False,
            "--headless",
            help="Run the standalone updater in the terminal without a window.",
        ),
    ) -> None:
        """Repair the installed stable release with the standalone updater."""
        root = get_project_root()
        release_file = root / ".suzent" / "release-tag"
        release_tag = (
            release_file.read_text(encoding="utf-8").strip()
            if release_file.exists()
            else ""
        )
        if not re.fullmatch(r"v\d+\.\d+\.\d+", release_tag):
            try:
                release_tag = str(_fetch_latest_release().get("tag_name", ""))
            except Exception as error:
                typer.echo(f"  ❌ Could not resolve repair version: {error}")
                raise typer.Exit(code=1)
        typer.echo(f"🛠️  Repairing Suzent {release_tag}...")
        _delegate_installer_update(
            root,
            release_tag=release_tag,
            relaunch=None,
            repair=True,
            headless=headless,
        )

    @app.command()
    def shortcuts(
        menu: bool | None = typer.Option(
            None,
            "--menu/--no-menu",
            help="Create or drop the application menu entry.",
        ),
        desktop: bool | None = typer.Option(
            None,
            "--desktop/--no-desktop",
            help="Create or drop the desktop shortcut.",
        ),
        remove: bool = typer.Option(
            False, "--remove", help="Delete the shortcuts Suzent created."
        ),
        json_output: bool = typer.Option(
            False, "--json", help="Print machine-readable JSON."
        ),
    ) -> None:
        """Create or repair the launcher shortcuts for this installation.

        Runs automatically during install and update; call it directly to fix
        shortcuts that were deleted or to change which ones you want.
        """
        from suzent.cli import shortcuts as shortcut_manager

        root = get_project_root()
        if remove:
            report = shortcut_manager.remove(root)
        else:
            report = shortcut_manager.install_or_repair(
                root, application_menu=menu, desktop=desktop
            )

        if json_output:
            typer.echo(json.dumps(report.as_dict()))
        else:
            for label, paths in (
                ("Created", report.created),
                ("Repaired", report.repaired),
                ("Removed", report.removed),
                ("Unchanged", report.kept),
            ):
                for path in paths:
                    typer.echo(f"  • {label}: {path}")
            for note in report.notes:
                typer.echo(f"  ⚠️  {note}")
            typer.echo(f"🔗 Launcher shortcuts: {report.summary()}")

        if not report.ok:
            raise typer.Exit(code=1)

    @app.command("check-update")
    def check_update(
        json_output: bool = typer.Option(
            False, "--json", help="Print machine-readable JSON."
        ),
        cached: bool = typer.Option(
            False, "--cached", help="Use the 24-hour update-check cache if available."
        ),
    ):
        """Check whether a newer Suzent release is available."""
        root = get_project_root()
        result = _check_for_update(root, use_cache=cached)
        current = result.get("current_version") or "unknown"
        latest = result.get("latest_version") or "unknown"

        if json_output:
            typer.echo(json.dumps(result))
            if result.get("error"):
                raise typer.Exit(code=1)
            return

        if result.get("error"):
            typer.echo(f"⚠️  Could not check for updates: {result['error']}")
            raise typer.Exit(code=1)

        if result.get("update_available"):
            typer.echo(f"Update available: {current} -> {latest}")
            typer.echo("Run `suzent update` to install it.")
            return

        typer.echo(f"Suzent is up to date ({current}).")

    @app.command()
    def setup_build_tools():
        """Install Visual Studio Build Tools (Windows Only)."""
        if not IS_WINDOWS:
            typer.echo("❌ This command is only for Windows.")
            raise typer.Exit(code=1)

        typer.echo("🛠️  Installing Visual Studio Build Tools...")
        typer.echo("   (This will open a UAC prompt and may take a while)")

        try:
            subprocess.run(["winget", "--version"], capture_output=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            typer.echo(
                "❌ 'winget' not found. Please update App Installer from Microsoft Store."
            )
            raise typer.Exit(code=1)

        cmd = [
            "winget",
            "install",
            "--id",
            "Microsoft.VisualStudio.2022.BuildTools",
            "--override",
            "--passive --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode == 0:
                typer.echo(
                    "\n✅ Build Tools installed successfully! Please RESTART your terminal."
                )
            elif (
                "No available upgrade found" in result.stdout
                or "Found an existing package already installed" in result.stdout
            ):
                typer.echo(
                    "\n✅ Build Tools already installed. Please RESTART your terminal if 'link.exe' is not found."
                )
            else:
                typer.echo(f"\n❌ Installation failed with code {result.returncode}")
                typer.echo(f"Stdout: {result.stdout}")
                typer.echo(f"Stderr: {result.stderr}")
                typer.echo("You may need to run this as Administrator.")
                raise typer.Exit(code=1)

        except Exception as e:
            typer.echo(f"\n❌ Unexpected error: {e}")
            raise typer.Exit(code=1)
