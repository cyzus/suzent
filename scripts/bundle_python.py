#!/usr/bin/env python3
"""
Bundle a prebuilt Python environment into src-tauri/resources/ for Tauri packaging.

Instead of bundling a bare Python + uv and installing at first-launch, we:
  1. Download a standalone Python distribution
  2. Install the suzent wheel + all dependencies into that Python directly
  3. Copy config examples and skills directories
  4. Generate CLI shims

At launch, Rust simply runs resources/python-env/python.exe -m suzent.server —
no venv creation, no network access, no first-run delay.
"""

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

# --- Configuration ---

PYTHON_VERSION = "3.12.8"
PYTHON_STANDALONE_TAG = "20241219"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESOURCES_DIR = PROJECT_ROOT / "src-tauri" / "resources"


def get_platform_info() -> tuple[str, str, str]:
    """Return (os_name, arch, exe_ext) for current platform."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        os_name = "windows"
        arch = "x86_64" if machine in ("amd64", "x86_64") else machine
        exe_ext = ".exe"
    elif system == "darwin":
        os_name = "macos"
        arch = "aarch64" if machine == "arm64" else "x86_64"
        exe_ext = ""
    elif system == "linux":
        os_name = "linux"
        arch = "x86_64" if machine in ("amd64", "x86_64") else machine
        exe_ext = ""
    else:
        raise RuntimeError(f"Unsupported platform: {system}")

    return os_name, arch, exe_ext


def download_file(url: str, dest: Path, description: str = "") -> None:
    label = description or url.split("/")[-1]
    print(f"  Downloading {label}...")
    urllib.request.urlretrieve(url, str(dest))
    size_mb = dest.stat().st_size / (1024 * 1024)
    print(f"  Downloaded {label} ({size_mb:.1f} MB)")


def download_python(target_dir: Path) -> Path:
    """Download python-build-standalone and extract to target_dir.

    Returns the path to the python executable.
    """
    os_name, arch, exe_ext = get_platform_info()
    target_dir.mkdir(parents=True, exist_ok=True)

    if os_name == "windows":
        triple = f"{arch}-pc-windows-msvc"
    elif os_name == "macos":
        triple = f"{arch}-apple-darwin"
    else:
        triple = f"{arch}-unknown-linux-gnu"

    tarball_name = f"cpython-{PYTHON_VERSION}+{PYTHON_STANDALONE_TAG}-{triple}-install_only_stripped.tar.gz"
    url = f"https://github.com/astral-sh/python-build-standalone/releases/download/{PYTHON_STANDALONE_TAG}/{tarball_name}"
    tarball_path = target_dir / tarball_name

    download_file(url, tarball_path, f"Python {PYTHON_VERSION} (standalone, {triple})")

    print("  Extracting Python...")
    with tarfile.open(tarball_path, "r:gz") as tf:
        tf.extractall(target_dir)
    tarball_path.unlink()

    # python-build-standalone extracts to a 'python' subdirectory — flatten it
    python_inner = target_dir / "python"
    if python_inner.exists():
        for item in python_inner.iterdir():
            shutil.move(str(item), str(target_dir / item.name))
        python_inner.rmdir()

    if os_name == "windows":
        return target_dir / "python.exe"
    else:
        python_exe = target_dir / "bin" / "python3"
        if not python_exe.exists():
            python_exe = target_dir / "bin" / "python"
        return python_exe


def build_and_install_wheel(python_exe: Path) -> None:
    """Build the suzent wheel and install it (with all deps) into the given Python."""
    wheel_dir = RESOURCES_DIR / "_wheel_tmp"
    wheel_dir.mkdir(parents=True, exist_ok=True)

    print("  Building suzent wheel...")
    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(wheel_dir)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  STDOUT: {result.stdout}")
        print(f"  STDERR: {result.stderr}")
        raise RuntimeError("Failed to build suzent wheel")

    wheels = list(wheel_dir.glob("suzent-*.whl"))
    if not wheels:
        raise RuntimeError(f"No wheel found in {wheel_dir}")
    wheel_path = wheels[0]
    print(f"  Built wheel: {wheel_path.name}")

    print(
        "  Installing suzent + all dependencies into python-env (this will take a while)..."
    )
    result = subprocess.run(
        [
            str(python_exe),
            "-m",
            "pip",
            "install",
            str(wheel_path),
            "--no-warn-script-location",
        ],
        capture_output=False,  # show live pip output
    )
    if result.returncode != 0:
        raise RuntimeError("pip install failed")

    print("  All dependencies installed.")
    shutil.rmtree(wheel_dir)


def copy_config_and_skills(target_dir: Path) -> None:
    config_dest = target_dir / "config"
    config_dest.mkdir(parents=True, exist_ok=True)
    for example_file in (PROJECT_ROOT / "config").glob("*.example.*"):
        shutil.copy2(str(example_file), str(config_dest / example_file.name))
        print(f"  Copied config: {example_file.name}")

    skills_src = PROJECT_ROOT / "skills"
    skills_dest = target_dir / "skills"
    if skills_dest.exists():
        shutil.rmtree(skills_dest)
    if skills_src.exists():
        shutil.copytree(str(skills_src), str(skills_dest))
        print("  Copied skills directory")
    else:
        print("  WARNING: No skills directory found")


def generate_shims(python_exe: Path, target_dir: Path) -> None:
    """Generate CLI shims pointing directly at the bundled python-env."""
    # Windows CMD shim
    cmd_shim = target_dir / "suzent.cmd"
    cmd_shim.write_text(
        f'@echo off\r\n"{python_exe.as_posix()}" -m suzent.cli %*',
        encoding="utf-8",
    )
    print(f"  Generated Windows shim: {cmd_shim.name}")

    # Unix shell shim
    sh_shim = target_dir / "suzent"
    sh_shim.write_text(
        f'#!/bin/sh\nexec "{python_exe}" -m suzent.cli "$@"',
        encoding="utf-8",
    )
    if hasattr(os, "chmod"):
        sh_shim.chmod(sh_shim.stat().st_mode | 0o111)
    print(f"  Generated Unix shim: {sh_shim.name}")


def bundle_python() -> None:
    print("=" * 50)
    print("  SUZENT Python Backend Bundler (Prebuilt Env)")
    print("=" * 50)

    os_name, arch, _ = get_platform_info()
    print(f"\nPlatform: {os_name}/{arch}")

    if RESOURCES_DIR.exists():
        print("\nCleaning previous resources...")
        shutil.rmtree(RESOURCES_DIR)
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Download Python into python-env/
    print("\n[1/4] Downloading Python runtime...")
    python_env_dir = RESOURCES_DIR / "python-env"
    python_exe = download_python(python_env_dir)
    print(f"  Python executable: {python_exe}")

    # Step 2: Install suzent + all deps into that Python
    print("\n[2/4] Installing suzent and all dependencies...")
    build_and_install_wheel(python_exe)

    # Step 3: Copy config and skills
    print("\n[3/4] Copying config and skills...")
    copy_config_and_skills(RESOURCES_DIR)

    # Step 4: Generate CLI shims
    print("\n[4/4] Generating CLI shims...")
    generate_shims(python_exe, RESOURCES_DIR)

    total_size = sum(f.stat().st_size for f in RESOURCES_DIR.rglob("*") if f.is_file())
    total_mb = total_size / (1024 * 1024)

    print("\n" + "=" * 50)
    print(f"  Bundle complete! Total size: {total_mb:.1f} MB")
    print(f"  Output: {RESOURCES_DIR}")
    print("=" * 50)

    print("\nContents:")
    for item in sorted(RESOURCES_DIR.iterdir()):
        if item.is_dir():
            dir_size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
            print(f"  {item.name}/  ({dir_size / (1024 * 1024):.1f} MB)")
        else:
            print(f"  {item.name}  ({item.stat().st_size / (1024 * 1024):.1f} MB)")


if __name__ == "__main__":
    bundle_python()
