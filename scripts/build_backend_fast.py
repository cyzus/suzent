#!/usr/bin/env python3
"""
Fast build script for Suzent backend using PyInstaller.
Drastically faster than Nuitka (2 mins vs 2 hours) but less protected.
"""

import sys
import os
import platform
import subprocess
from pathlib import Path

# Fix Windows console encoding
if platform.system() == "Windows":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())
    os.environ["PYTHONIOENCODING"] = "utf-8"


def get_target_triple() -> str:
    """Get the Rust target triple for the current platform."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        return "x86_64-pc-windows-msvc"
    elif system == "darwin":
        return "aarch64-apple-darwin" if machine == "arm64" else "x86_64-apple-darwin"
    elif system == "linux":
        return "x86_64-unknown-linux-gnu"
    return "unknown"


def get_output_name() -> str:
    """Get platform-specific executable name with target triple."""
    triple = get_target_triple()
    ext = ".exe" if platform.system() == "Windows" else ""
    return f"suzent-backend-{triple}{ext}"


def build_backend() -> None:
    project_root = Path(__file__).parent.parent
    output_dir = project_root / "src-tauri" / "binaries"
    output_dir.mkdir(parents=True, exist_ok=True)

    target_name = get_output_name()
    dist_dir = output_dir / "dist"  # PyInstaller output dir

    print(f"Building backend using PyInstaller to {output_dir}...")
    print(f"Distribution dir: {dist_dir}")

    # Include Data paths: source -> dest
    # PyInstaller syntax: src;dest (Windows) or src:dest (Linux/Mac)
    sep = ";" if platform.system() == "Windows" else ":"

    datas = [
        f"{project_root / 'config'}{sep}config",
        f"{project_root / 'skills'}{sep}skills",
    ]

    # LiteLLM data files are tricky, usually handled by collect_data_files from PyInstaller hook
    # But explicitly including them is safer.
    # We use --collect-all for critical packages

    cmd = [
        "pyinstaller",
        "--clean",
        "--noconfirm",
        "--onefile",
        f"--name={target_name.replace('.exe', '')}",  # PyInstaller adds extension
        f"--distpath={output_dir}",
        f"--workpath={output_dir / 'build'}",
        f"--specpath={output_dir}",
        # Hidden imports for dynamic loading
        "--hidden-import=suzent.tools",
        "--hidden-import=suzent.programs",
        "--hidden-import=tiktoken_ext.openai_public",
        "--hidden-import=tiktoken_ext",
        # Data files
        *[f"--add-data={d}" for d in datas],
        # Collect all data/binaries for complex packages
        "--collect-all=litellm",
        "--collect-all=gradio_client",
        "--collect-all=suzent",
        "--collect-all=lancedb",
        "--collect-all=crawl4ai",
        "--collect-all=uvicorn",
        # Entry point
        str(project_root / "src" / "suzent" / "server.py"),
    ]

    print("Running:", " ".join(cmd))

    # Run PyInstaller via subprocess
    # We use sys.executable -m PyInstaller to ensuring we use the installed module
    run_cmd = [sys.executable, "-m", "PyInstaller"] + cmd[1:]

    try:
        subprocess.run(run_cmd, check=True)
        print(f"\n[SUCCESS] Backend built at: {output_dir / target_name}")

    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Build failed with code {e.returncode}")
        sys.exit(1)

    # Cleanup build artifacts (spec file, build dir)
    # Keeping them for debugging if needed, but user wanted fast iteration
    # Optional: shutil.rmtree(output_dir / 'build')


if __name__ == "__main__":
    build_backend()
