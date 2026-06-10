"""
Top-level CLI commands: start, doctor, update, upgrade, setup-build-tools.
"""

import csv
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
import urllib.request
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import typer
from suzent.config import DEFAULT_PORT

IS_WINDOWS = sys.platform == "win32"

_REPO = "cyzus/suzent"
_BIN_DIR = "bin"
_UPDATE_CHECK_TTL_SECONDS = 24 * 60 * 60


def _is_development_workspace(root: Path) -> bool:
    """Return True for source checkouts that are not bootstrapped installs."""
    return not (root / ".suzent-bootstrap-complete").exists()


def _backend_sync_args(root: Path) -> list[str]:
    args = ["uv", "sync", "--extra", "social"]
    if _is_development_workspace(root):
        args.extend(["--extra", "dev"])
    return args


def _get_ui_binary(root: Path) -> Path | None:
    """Return a compatible UI binary: newest local/release build wins."""
    name = "suzent-ui.exe" if IS_WINDOWS else "suzent-ui"
    release_name = "suzent.exe" if IS_WINDOWS else "suzent"
    candidates = [
        root / _BIN_DIR / name,
        root / "src-tauri" / "target" / "release" / release_name,
    ]
    existing = [p for p in candidates if p.exists() and _is_ui_binary_current(root, p)]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def _is_ui_binary_current(root: Path, binary: Path) -> bool:
    """Avoid launching a stale UI binary against newer backend/Tauri sources."""
    try:
        if (root / _BIN_DIR) in binary.resolve().parents and _has_unreleased_ui_changes(
            root
        ):
            return False
    except OSError:
        return False

    source_paths = [
        root / "src-tauri" / "src" / "backend.rs",
        root / "src-tauri" / "src" / "main.rs",
        root / "src-tauri" / "tauri.conf.json",
    ]
    existing_sources = [path for path in source_paths if path.exists()]
    if not existing_sources:
        return True
    binary_mtime = binary.stat().st_mtime
    return all(path.stat().st_mtime <= binary_mtime for path in existing_sources)


def _has_unreleased_ui_changes(root: Path) -> bool:
    """Return True when local backend/Tauri changes are not represented by releases."""
    if not (root / ".git").exists():
        return False

    watched_paths = [
        "src-tauri",
        "src/suzent/server.py",
        "src/suzent/config/__init__.py",
        "src/suzent/client/base.py",
        "src/suzent/sandbox/manager.py",
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


def _latest_asset_url(asset_name: str) -> str:
    return f"https://github.com/{_REPO}/releases/latest/download/{asset_name}"


def _local_ui_version(root: Path) -> str:
    f = root / _BIN_DIR / "version.txt"
    return f.read_text().strip() if f.exists() else ""


def _current_version(root: Path) -> str:
    """Return the installed/project version, falling back to pyproject for source runs."""
    try:
        return version("suzent")
    except PackageNotFoundError:
        pass

    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return ""

    for line in pyproject.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("version ="):
            return line.split("=", 1)[1].strip().strip('"')
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


def download_ui_binary(root: Path, *, version: str = "latest") -> bool:
    """Download the pre-built UI binary from GitHub Releases. Returns True on success."""
    asset_name = _platform_asset_name()
    try:
        bin_dir = root / _BIN_DIR
        dest = bin_dir / ("suzent-ui.exe" if IS_WINDOWS else "suzent-ui")

        typer.echo("  • Downloading UI binary...")
        _download_file_atomic(_latest_asset_url(asset_name), dest)
        if not IS_WINDOWS:
            dest.chmod(0o755)
        (bin_dir / "version.txt").write_text(version)
        typer.echo(f"  ✅ UI binary ready at {dest}")
        return True
    except Exception as e:
        typer.echo(f"  ⚠️  Binary download failed: {e}")
        return False


def _update_ui_binary(root: Path) -> None:
    """Download a new UI binary only if the release version changed."""
    try:
        release = _fetch_latest_release()
        latest = release.get("tag_name", "")
        local = _local_ui_version(root)
        if latest and latest != local:
            typer.echo(f"  • UI binary: {local or 'none'} → {latest}")
            download_ui_binary(root, version=latest)
        else:
            typer.echo(f"  • UI binary up to date ({local})")
    except Exception as e:
        typer.echo(f"  ⚠️  Could not check UI binary version: {e}")
        typer.echo("  • Attempting direct latest binary download...")
        download_ui_binary(root)


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
    else:
        typer.echo("⚠️  Could not find 'cargo' in standard locations.")
        typer.echo("   Please ensure Rust is installed and 'cargo' is in your PATH.")


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


def _windows_image_pids(image_name: str, *, exclude_pid: int) -> list[int]:
    if not IS_WINDOWS:
        return []
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
    )
    pids: list[int] = []
    for row in csv.reader(result.stdout.splitlines()):
        if len(row) < 2:
            continue
        try:
            pid = int(row[1])
        except ValueError:
            continue
        if pid != exclude_pid:
            pids.append(pid)
    return pids


def _windows_suzent_backend_pids(root: Path, *, exclude_pid: int) -> list[int]:
    if not IS_WINDOWS:
        return []
    root_text = str(root.resolve()).replace("'", "''")
    script = (
        "$ErrorActionPreference = 'SilentlyContinue'; "
        f"$root = '{root_text}'; "
        f"$current = {exclude_pid}; "
        "$procs = Get-CimInstance Win32_Process | Where-Object { "
        "$_.ProcessId -ne $current -and "
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
        if pid != exclude_pid:
            pids.append(pid)
    return pids


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

        ui_bin = _get_ui_binary(root)
        if ui_bin:
            # Pre-built binary manages both backend and webview internally.
            typer.echo(f"  • Launching UI binary ({ui_bin.name})...")
            try:
                subprocess.run([str(ui_bin)])
            except (subprocess.CalledProcessError, KeyboardInterrupt):
                pass
            return

        # ── Developer fallback: tauri dev ────────────────────────────────────
        typer.echo("  ⚠️  No pre-built UI binary found — starting in developer mode.")
        typer.echo("     Run 'suzent update' to download the binary.")
        ensure_cargo_in_path()
        ensure_msvc_linker()

        for port, name in [(DEFAULT_PORT, "Backend"), (18080, "Frontend")]:
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

        backend_env = os.environ.copy()
        backend_env["SUZENT_PORT"] = str(DEFAULT_PORT)

        typer.echo("  • Starting backend...")
        backend_proc = subprocess.Popen(
            [sys.executable, "-m", "suzent.server"],
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
            typer.echo("\n🛑 Stopping backend...")
            _terminate_process_gracefully(backend_proc)

    @app.command()
    def serve(
        host: str = typer.Option("127.0.0.1", help="Host to bind to"),
        port: int = typer.Option(DEFAULT_PORT, help="Port to bind to"),
        debug: bool = typer.Option(False, "--debug", help="Run in debug mode"),
    ):
        """Start the Suzent backend server (headless/standalone mode)."""
        typer.echo(f"🚀 Starting Suzent Server on {host}:{port}...")

        env = os.environ.copy()
        env["SUZENT_HOST"] = host
        env["SUZENT_PORT"] = str(port)

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
            env = os.environ.copy()
            env["SUZENT_PORT"] = str(port)
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

        if all_ok:
            typer.echo("\n✨ System is ready for Suzent!")
        else:
            typer.echo("\n⚠️  Some tools are missing. Please install them.")

    def _kill_other_suzent_processes(root: Path) -> None:
        """Terminate running Suzent UI/backend processes before dependency sync."""
        if not IS_WINDOWS:
            return
        my_pid = os.getpid()

        try:
            for pid in _windows_image_pids("suzent.exe", exclude_pid=my_pid):
                _stop_windows_process(pid, "suzent process")
        except Exception:
            pass

        try:
            backend_pids = _windows_suzent_backend_pids(root, exclude_pid=my_pid)
            for pid in backend_pids:
                _stop_windows_process(pid, "suzent backend")
            if backend_pids:
                time.sleep(1)
        except Exception:
            pass

    def _run_update() -> None:
        typer.echo("🔄 Updating Suzent...")
        root = get_project_root()

        typer.echo("  • Pulling latest changes...")
        try:
            run_command(["git", "pull"], cwd=root)
        except subprocess.CalledProcessError:
            typer.echo(
                "  ⚠️  Git pull failed. This is usually due to local file changes (e.g. lockfiles)."
            )
            if typer.confirm("  Stash local changes and retry?"):
                typer.echo("  🔄 Stashing local changes...")
                run_command(["git", "stash", "--include-untracked"], cwd=root)
                try:
                    run_command(["git", "pull"], cwd=root)
                except subprocess.CalledProcessError:
                    typer.echo("  ❌ Git pull still failed. Restoring stash...")
                    run_command(["git", "stash", "pop"], cwd=root)
                    raise typer.Exit(code=1)
                # Re-apply stashed changes (may have merge conflicts, non-fatal)
                try:
                    run_command(["git", "stash", "pop"], cwd=root)
                except subprocess.CalledProcessError:
                    typer.echo(
                        "  ⚠️  Some stashed changes conflicted. Check 'git stash list'."
                    )
            else:
                typer.echo("  ❌ Update aborted.")
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

        # Update pre-built UI binary (non-fatal)
        typer.echo("  • Checking UI binary...")
        _update_ui_binary(root)

        ui_bin = _get_ui_binary(root)
        if ui_bin:
            # Frontend is embedded in the binary — no npm steps needed.
            typer.echo("\n✨ Suzent successfully updated!")
            return

        # ── Developer path: update npm dependencies ───────────────────────────
        typer.echo("  • Updating frontend dependencies...")
        frontend_dir = root / "frontend"
        try:
            run_command(["npm", "install"], cwd=frontend_dir, shell_on_windows=True)
        except subprocess.CalledProcessError:
            typer.echo("  ❌ Frontend dependency update failed (npm install).")
            raise typer.Exit(code=1)

        typer.echo("  • Updating src-tauri dependencies...")
        tauri_dir = root / "src-tauri"
        try:
            run_command(["npm", "install"], cwd=tauri_dir, shell_on_windows=True)
        except subprocess.CalledProcessError:
            typer.echo("  ❌ Src-tauri dependency update failed (npm install).")
            raise typer.Exit(code=1)

        typer.echo("\n✨ Suzent successfully updated!")

    @app.command()
    def update():
        """Update Suzent to the latest version."""
        _run_update()

    @app.command()
    def upgrade():
        """Alias for `update`."""
        typer.echo(
            "`suzent upgrade` is supported; `suzent update` is the primary command."
        )
        _run_update()

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
