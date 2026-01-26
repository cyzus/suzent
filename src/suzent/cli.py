import typer
import subprocess
import sys
from pathlib import Path

app = typer.Typer(help="Suzent CLI - Your Digital Co-worker Manager")


def get_project_root() -> Path:
    """Get the root directory of the project."""
    # Assuming this file is in src/suzent/cli.py
    return Path(__file__).parent.parent.parent


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
        # Placeholder for docs server
        return

    typer.echo("🚀 Starting SUZENT...")

    # 1. Start Backend
    backend_cmd = ["python", "src/suzent/server.py"]
    if debug:
        backend_cmd.append("--debug")

    typer.echo("  • Starting Backend...")
    # On Windows, we might want a new window or just background it
    if sys.platform == "win32":
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
    frontend_dir = root / "src-tauri"

    # Check if node_modules exists
    if not (frontend_dir / "node_modules").exists():
        typer.echo("    Installing dependencies...")
        subprocess.run(["npm", "install"], cwd=frontend_dir, check=True, shell=sys.platform == "win32")

    subprocess.run(["npm", "run", "dev"], cwd=frontend_dir, shell=sys.platform == "win32")


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

    all_ok = True
    for name, cmd in checks.items():
        try:
            # Use shell=True on Windows for npm/cargo which might be scripts/shims
            use_shell = sys.platform == "win32" and name in ["npm", "uv"] 
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
        subprocess.run(["git", "pull"], cwd=root, check=True)
    except subprocess.CalledProcessError:
        typer.echo("  ❌ Git pull failed. Please check for local conflicts.")
        raise typer.Exit(code=1)

    # 2. Update Backend Deps
    typer.echo("  • Updating backend dependencies...")
    subprocess.run(["uv", "sync"], cwd=root, check=True, shell=sys.platform == "win32")

    # 3. Update Frontend Deps
    typer.echo("  • Updating frontend dependencies...")
    frontend_dir = root / "src-tauri"
    subprocess.run(["npm", "install"], cwd=frontend_dir, check=True, shell=sys.platform == "win32")

    typer.echo("\n✨ Suzent successfully upgraded!")

if __name__ == "__main__":
    app()
