"""
Top-level CLI commands: start, serve, stop, doctor, update, upgrade, setup-build-tools.
"""

import io
import json
import os
import platform
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import typer
from suzent.config import DEFAULT_PORT

IS_WINDOWS = sys.platform == "win32"

_REPO = "cyzus/suzent"
_BIN_DIR = "bin"
_UPDATE_CHECK_TTL_SECONDS = 24 * 60 * 60
_UPDATE_CHANNEL_FILE = ".suzent/update-channel"
_STABLE_CHANNEL = "stable"
_DEV_CHANNEL = "dev"
_UPDATE_HELPER_ENV = "SUZENT_UPDATE_HELPER"


def _is_development_workspace(root: Path) -> bool:
    """Return True for source checkouts that are not bootstrapped installs."""
    return not (root / ".suzent-bootstrap-complete").exists()


def _backend_sync_args(root: Path) -> list[str]:
    args = ["uv", "sync", "--frozen", "--extra", "social"]
    if _is_development_workspace(root):
        args.extend(["--extra", "dev"])
    return args


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


def _is_ui_binary_current(root: Path, binary: Path) -> bool:
    """Return True when a discovered UI binary can be launched."""
    return binary.exists()


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


def _is_suzent_server_running(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return True when a Suzent backend responds on host:port."""
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{probe_host}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError, urllib.error.URLError):
        return False
    return payload.get("app") == "suzent" and payload.get("status") == "ok"


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


def _fetch_latest_release(timeout: float = 10.0) -> dict:
    url = f"https://api.github.com/repos/{_REPO}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": "suzent-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _release_asset_url(asset_name: str, version: str) -> str:
    if version == "latest":
        return f"https://github.com/{_REPO}/releases/latest/download/{asset_name}"
    return f"https://github.com/{_REPO}/releases/download/{version}/{asset_name}"


def _local_ui_version(root: Path) -> str:
    f = root / _BIN_DIR / "version.txt"
    return f.read_text().strip() if f.exists() else ""


def _current_version(root: Path) -> str:
    """Return the source version first, then installed package metadata."""
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version ="):
                return line.split("=", 1)[1].strip().strip('"')

    try:
        return version("suzent")
    except PackageNotFoundError:
        return ""


def _normalize_version_tag(value: str) -> str:
    return value.strip().lstrip("vV")


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
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


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


def _notify_update_available(root: Path) -> None:
    if os.environ.get("SUZENT_SKIP_UPDATE_CHECK") == "1":
        return

    result = _check_for_update(root, use_cache=True)
    if not result.get("update_available"):
        return

    latest = result.get("latest_version") or "latest"
    current = result.get("current_version") or "unknown"
    typer.echo(f"  • Update available: {current} -> {latest}. Run 'suzent update'.")


def _download_file_atomic(url: str, dest: Path, *, timeout: float = 60.0) -> None:
    dest.parent.mkdir(exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{dest.name}.", suffix=".tmp", dir=dest.parent
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as file:
            req = urllib.request.Request(url, headers={"User-Agent": "suzent-updater"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                shutil.copyfileobj(resp, file)
        tmp_path.replace(dest)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


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
    """Get the PID of the process using the specified port."""
    try:
        if IS_WINDOWS:
            cmd = f"netstat -ano | findstr :{port}"
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            if result.returncode == 0 and result.stdout:
                for line in result.stdout.strip().splitlines():
                    parts = line.split()
                    if len(parts) >= 5 and f":{port}" in parts[1]:
                        return int(parts[-1])
        else:
            cmd = ["lsof", "-t", f"-i:{port}"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout:
                return int(result.stdout.strip().split("\n")[0])
    except Exception:
        pass
    return None


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
            # Pre-built binary manages both backend and webview internally.
            typer.echo(f"  • Launching UI binary ({ui_bin.name})...")
            try:
                subprocess.run(
                    [str(ui_bin)],
                    env=_ui_launch_env({"SUZENT_DIR": str(root)}),
                )
            except (subprocess.CalledProcessError, KeyboardInterrupt):
                pass
            return

        # ── Developer fallback: tauri dev ────────────────────────────────────
        if dev:
            typer.echo("  * Starting in developer mode (--dev).")
        else:
            typer.echo("  No pre-built UI binary found - starting in developer mode.")
            typer.echo("     Run 'suzent update' to download the binary.")
        ensure_cargo_in_path()
        ensure_msvc_linker()

        backend_running = _is_suzent_server_running("127.0.0.1", DEFAULT_PORT)
        ports_to_check = [(18080, "Frontend")]
        if not backend_running:
            ports_to_check.insert(0, (DEFAULT_PORT, "Backend"))
        elif not dev:
            typer.echo(
                f"  ✅ Backend already running on http://127.0.0.1:{DEFAULT_PORT}; "
                "reusing it."
            )

        for port, name in ports_to_check:
            pid = get_pid_on_port(port)
            if pid:
                typer.echo(f"\n⚠️  {name} Port {port} is already in use by PID {pid}.")
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
            pid = get_pid_on_port(DEFAULT_PORT)
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
            for _attempt in range(20):
                if get_pid_on_port(DEFAULT_PORT) is None:
                    break
                time.sleep(0.1)
            else:
                typer.echo("  ❌ Existing backend did not release its port.")
                raise typer.Exit(code=1)
            backend_running = False

        backend_env = os.environ.copy()
        backend_env["SUZENT_PORT"] = str(DEFAULT_PORT)
        if dev:
            backend_env["SUZENT_DEV_MODE"] = "1"

        backend_proc = None
        if backend_running:
            typer.echo("  • Skipping backend startup.")
        else:
            typer.echo("  • Starting backend...")
            backend_cmd = [sys.executable, "-m", "suzent.server"]
            if debug:
                backend_cmd.append("--debug")
            backend_proc = subprocess.Popen(
                backend_cmd,
                cwd=root,
                env=backend_env,
            )

        typer.echo("  • Starting frontend (Tauri dev)...")
        _ensure_npm_deps(root)

        try:
            run_command(
                ["npm", "run", "dev"], cwd=root / "src-tauri", shell_on_windows=True
            )
        except (subprocess.CalledProcessError, KeyboardInterrupt):
            pass
        finally:
            if backend_proc is not None:
                typer.echo("\n🛑 Stopping backend...")
                _terminate_process_gracefully(backend_proc)

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
    def stop(
        port: int = typer.Option(DEFAULT_PORT, help="Port the backend is running on"),
    ):
        """Stop a running Suzent backend server."""
        if not _is_suzent_server_running("127.0.0.1", port):
            typer.echo(f"No Suzent server running on http://127.0.0.1:{port}.")
            return

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
            typer.echo("✅ Server stopped.")
        except Exception as e:
            typer.echo(f"❌ Failed to stop server: {e}")
            raise typer.Exit(code=1)

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
                subprocess.run([str(ui_bin)], env=env)
            except (subprocess.CalledProcessError, KeyboardInterrupt):
                pass
            return

        ensure_cargo_in_path()
        ensure_msvc_linker()
        _ensure_npm_deps(root)

        env = os.environ.copy()
        env["SUZENT_PORT"] = str(port)

        try:
            run_command(
                ["npm", "run", "dev"], cwd=root / "src-tauri", shell_on_windows=True
            )
        except (subprocess.CalledProcessError, KeyboardInterrupt):
            pass

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

    def _run_update(*, dev: bool = False) -> None:
        channel = _DEV_CHANNEL if dev else _STABLE_CHANNEL
        typer.echo(f"🔄 Updating Suzent ({channel} channel)...")
        root = get_project_root()

        if _delegate_windows_update(root, dev=dev):
            return

        if not dev and _is_development_workspace(root):
            typer.echo(
                "  ❌ Stable updates require a bootstrapped installation. "
                "Use 'suzent update --dev' for a source checkout."
            )
            raise typer.Exit(code=1)

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
    ):
        """Update Suzent to the latest version."""
        _run_update(dev=dev)

    @app.command()
    def upgrade(
        dev: bool = typer.Option(
            False,
            "--dev",
            help="Update to origin/main and run the matching development frontend.",
        ),
    ):
        """Alias for `update`."""
        typer.echo(
            "`suzent upgrade` is supported; `suzent update` is the primary command."
        )
        _run_update(dev=dev)

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
