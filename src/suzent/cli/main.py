"""
Top-level CLI commands: start, doctor, upgrade, setup-build-tools.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import typer

IS_WINDOWS = sys.platform == "win32"


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


def run_command(
    cmd: list[str], cwd: Path = None, check: bool = True, shell_on_windows: bool = False
):
    """Run a subprocess command with platform-specific adjustments."""
    use_shell = IS_WINDOWS and shell_on_windows
    subprocess.run(cmd, cwd=cwd, check=check, shell=use_shell)


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
        ensure_cargo_in_path()

        if docs:
            typer.echo("📚 Starting Documentation Server...")
            return

        typer.echo("🚀 Starting SUZENT...")

        for port, name in [(8000, "Backend"), (5173, "Frontend")]:
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

        backend_cmd = ["python", "src/suzent/server.py"]
        if debug:
            backend_cmd.append("--debug")

        typer.echo("  • Starting Backend...")
        if IS_WINDOWS:
            subprocess.Popen(
                ["start", "powershell", "-NoExit", "-Command"]
                + [" ".join(backend_cmd)],
                shell=True,
                cwd=root,
            )
        else:
            subprocess.Popen(backend_cmd, cwd=root)

        typer.echo("  • Starting Frontend...")
        frontend_app_dir = root / "frontend"
        src_tauri_dir = root / "src-tauri"

        if not (frontend_app_dir / "node_modules").exists():
            typer.echo("    Installing frontend app dependencies...")
            run_command(["npm", "install"], cwd=frontend_app_dir, shell_on_windows=True)

        if not (src_tauri_dir / "node_modules").exists():
            typer.echo("    Installing tauri dependencies...")
            run_command(["npm", "install"], cwd=src_tauri_dir, shell_on_windows=True)

        try:
            run_command(["npm", "run", "dev"], cwd=src_tauri_dir, shell_on_windows=True)
        except subprocess.CalledProcessError:
            typer.echo("\n⚠️  Dev server failed to start.")
            typer.echo(
                "    Attempting to fix by performing a CLEAN install of dependencies..."
            )

            for d in [frontend_app_dir, src_tauri_dir]:
                nm = d / "node_modules"
                if nm.exists():
                    typer.echo(f"    🗑️  Removing {nm}...")
                    shutil.rmtree(nm, ignore_errors=True)

                typer.echo(f"    📥 Installing dependencies in {d.name}...")
                run_command(["npm", "install"], cwd=d, shell_on_windows=True)

            typer.echo("    Retrying dev server...")
            run_command(["npm", "run", "dev"], cwd=src_tauri_dir, shell_on_windows=True)

    @app.command()
    def doctor():
        """Check if all requirements are installed and configured correctly."""
        typer.echo("🩺 QA Checking System Health...")

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

    @app.command()
    def upgrade():
        """Update Suzent to the latest version."""
        typer.echo("🔄 Upgrading Suzent...")
        root = get_project_root()

        typer.echo("  • Pulling latest changes...")
        try:
            run_command(["git", "pull"], cwd=root)
        except subprocess.CalledProcessError:
            typer.echo(
                "  ⚠️  Git pull failed. This is usually due to local file changes (e.g. lockfiles)."
            )
            if typer.confirm("  Discard local changes and force upgrade?"):
                typer.echo("  🔄 Resetting local changes...")
                run_command(["git", "reset", "--hard"], cwd=root)
                run_command(["git", "pull"], cwd=root)
            else:
                typer.echo("  ❌ Upgrade aborted.")
                raise typer.Exit(code=1)

        typer.echo("  • Updating backend dependencies...")
        run_command(["uv", "sync"], cwd=root, shell_on_windows=True)

        typer.echo("  • Updating frontend dependencies...")
        frontend_dir = root / "src-tauri"
        run_command(["npm", "install"], cwd=frontend_dir, shell_on_windows=True)

        typer.echo("\n✨ Suzent successfully upgraded!")

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
