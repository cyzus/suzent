import sys
import os
import subprocess
import typer
from pathlib import Path

app = typer.Typer(help="Suzent CLI - Your Digital Co-worker Manager")

IS_WINDOWS = sys.platform == "win32"


def get_project_root() -> Path:
    """Get the root directory of the project."""
    # Assuming this file is in src/suzent/cli.py
    return Path(__file__).parent.parent.parent


def ensure_cargo_in_path():
    """Ensure Rust's cargo is in PATH for non-Windows systems."""
    if not IS_WINDOWS:
        cargo_bin = Path.home() / ".cargo" / "bin"
        if cargo_bin.exists():
            current_path = os.environ.get("PATH", "")
            if str(cargo_bin) not in current_path:
                os.environ["PATH"] = f"{cargo_bin}:{current_path}"


def run_command(
    cmd: list[str], cwd: Path = None, check: bool = True, shell_on_windows: bool = False
):
    """Run a subprocess command with platform-specific adjustments."""
    use_shell = IS_WINDOWS and shell_on_windows
    subprocess.run(cmd, cwd=cwd, check=check, shell=use_shell)


@app.command()
def start(
    debug: bool = typer.Option(False, "--debug", help="Run server in debug mode"),
    docs: bool = typer.Option(
        False, "--docs", help="Run documentation server instead of app"
    ),
):
    """Start the Suzent development environment."""
    root = get_project_root()
    ensure_cargo_in_path()  # Ensure Rust is available

    if docs:
        typer.echo("📚 Starting Documentation Server...")
        # Placeholder for docs server
        return

    typer.echo("🚀 Starting SUZENT...")

    # 1. Start Backend
    backend_cmd = ["python", "src/suzent/server.py"]
    if debug:
        backend_cmd.append("--debug")

    typer.echo("  • Starting Backend...")
    # On Windows, we need to handle the separate window/process carefully
    if IS_WINDOWS:
        subprocess.Popen(
            ["start", "powershell", "-NoExit", "-Command"] + [" ".join(backend_cmd)],
            shell=True,
            cwd=root,
        )
    else:
        # Mac/Linux: run in background
        subprocess.Popen(backend_cmd, cwd=root)

    # 2. Start Frontend
    typer.echo("  • Starting Frontend...")
    frontend_app_dir = root / "frontend"
    src_tauri_dir = root / "src-tauri"

    # Check if frontend node_modules exists
    if not (frontend_app_dir / "node_modules").exists():
        typer.echo("    Installing frontend app dependencies...")
        run_command(["npm", "install"], cwd=frontend_app_dir, shell_on_windows=True)

    # Check if src-tauri node_modules exists
    if not (src_tauri_dir / "node_modules").exists():
        typer.echo("    Installing tauri dependencies...")
        run_command(["npm", "install"], cwd=src_tauri_dir, shell_on_windows=True)

    # Start dev server
    run_command(["npm", "run", "dev"], cwd=src_tauri_dir, shell_on_windows=True)


@app.command()
def doctor():
    """Check if all requirements are installed and configured correctly."""
    typer.echo("🩺 QA Checking System Health...")

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

    all_ok = True
    for name, cmd in checks.items():
        try:
            # Use shell=True on Windows for npm/uv/etc which might be scripts/shims
            is_script = name in ["npm", "uv"]

            # Capture output
            use_shell = IS_WINDOWS and is_script
            res = subprocess.run(cmd, capture_output=True, text=True, shell=use_shell)

            if res.returncode == 0:
                typer.echo(f"  ✅ {name:<10} : {res.stdout.strip()}")
            else:
                typer.echo(f"  ❌ {name:<10} : Not found or error")
                all_ok = False
        except FileNotFoundError:
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

    # 1. Git Pull
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

    # 2. Update Backend Deps
    typer.echo("  • Updating backend dependencies...")
    run_command(["uv", "sync"], cwd=root, shell_on_windows=True)

    # 3. Update Frontend Deps
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

    # Check for winget
    try:
        subprocess.run(["winget", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        typer.echo(
            "❌ 'winget' not found. Please update App Installer from Microsoft Store."
        )
        raise typer.Exit(code=1)

    # Command to install VS Build Tools with C++ workload
    cmd = [
        "winget",
        "install",
        "--id",
        "Microsoft.VisualStudio.2022.BuildTools",
        "--override",
        "--passive --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended",
    ]

    try:
        subprocess.run(cmd, check=True)
        typer.echo(
            "\n✅ Build Tools installed successfully! Please RESTART your terminal."
        )
    except subprocess.CalledProcessError:
        typer.echo(
            "\n❌ Installation failed. You may need to run this as Administrator."
        )
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
