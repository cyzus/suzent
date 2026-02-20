#!/usr/bin/env python3
"""
Bundle Python runtime + uv + suzent wheel into src-tauri/resources/ for Tauri packaging.

Instead of compiling Python with PyInstaller/Nuitka, we bundle:
  - A standalone/embeddable Python distribution
  - The uv package manager binary
  - A pre-built wheel of the suzent package
  - Config examples and skills directories

At first launch, the Rust side uses uv to create a venv and install the wheel.
"""

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

# --- Configuration ---

PYTHON_VERSION = "3.12.8"
# python-build-standalone release tag for cross-platform standalone builds
PYTHON_STANDALONE_TAG = "20241219"

# uv version to bundle
UV_VERSION = "0.5.14"

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
    """Download a file with progress indication."""
    label = description or url.split("/")[-1]
    print(f"  Downloading {label}...")
    urllib.request.urlretrieve(url, str(dest))
    size_mb = dest.stat().st_size / (1024 * 1024)
    print(f"  Downloaded {label} ({size_mb:.1f} MB)")


def download_python(target_dir: Path) -> Path:
    """Download embeddable/standalone Python and extract to target_dir.

    Returns the path to the python executable inside target_dir.
    """
    os_name, arch, exe_ext = get_platform_info()
    target_dir.mkdir(parents=True, exist_ok=True)

    if os_name == "windows":
        # Use the official embeddable zip from python.org
        zip_name = f"python-{PYTHON_VERSION}-embed-amd64.zip"
        url = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/{zip_name}"
        zip_path = target_dir / zip_name

        download_file(url, zip_path, f"Python {PYTHON_VERSION} (embeddable)")

        print("  Extracting Python...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(target_dir)
        zip_path.unlink()

        # Enable site-packages by uncommenting the import site line in python312._pth
        pth_files = list(target_dir.glob("python*._pth"))
        for pth_file in pth_files:
            content = pth_file.read_text(encoding="utf-8")
            content = content.replace("#import site", "import site")
            pth_file.write_text(content, encoding="utf-8")

        return target_dir / f"python{exe_ext}"

    else:
        # Use python-build-standalone for macOS/Linux
        if os_name == "macos":
            triple = f"{arch}-apple-darwin"
        else:
            triple = f"{arch}-unknown-linux-gnu"

        tarball_name = f"cpython-{PYTHON_VERSION}+{PYTHON_STANDALONE_TAG}-{triple}-install_only_stripped.tar.gz"
        url = f"https://github.com/indygreg/python-build-standalone/releases/download/{PYTHON_STANDALONE_TAG}/{tarball_name}"
        tarball_path = target_dir / tarball_name

        download_file(url, tarball_path, f"Python {PYTHON_VERSION} (standalone)")

        print("  Extracting Python...")
        with tarfile.open(tarball_path, "r:gz") as tf:
            tf.extractall(target_dir)
        tarball_path.unlink()

        # python-build-standalone extracts to a 'python' subdirectory
        python_inner = target_dir / "python"
        if python_inner.exists():
            # Move contents up one level
            for item in python_inner.iterdir():
                shutil.move(str(item), str(target_dir / item.name))
            python_inner.rmdir()

        python_exe = target_dir / "bin" / "python3"
        if not python_exe.exists():
            python_exe = target_dir / "bin" / "python"
        return python_exe


def download_uv(target_dir: Path) -> Path:
    """Download the uv binary for the current platform.

    Returns path to the uv executable.
    """
    os_name, arch, exe_ext = get_platform_info()
    target_dir.mkdir(parents=True, exist_ok=True)

    if os_name == "windows":
        archive_name = f"uv-{arch}-pc-windows-msvc.zip"
    elif os_name == "macos":
        archive_name = f"uv-{arch}-apple-darwin.tar.gz"
    else:
        archive_name = f"uv-{arch}-unknown-linux-gnu.tar.gz"

    url = (
        f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/{archive_name}"
    )
    archive_path = target_dir / archive_name

    download_file(url, archive_path, f"uv {UV_VERSION}")

    print("  Extracting uv...")
    if archive_name.endswith(".zip"):
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(target_dir)
    else:
        with tarfile.open(archive_path, "r:gz") as tf:
            tf.extractall(target_dir)
    archive_path.unlink()

    # uv archives extract into a subdirectory like uv-x86_64-pc-windows-msvc/
    # Find and move the uv binary to the target_dir root
    uv_exe_name = f"uv{exe_ext}"
    uv_binary = next(target_dir.rglob(uv_exe_name), None)

    if not uv_binary:
        raise RuntimeError(f"Could not find uv binary after extraction in {target_dir}")

    if uv_binary.parent != target_dir:
        dest = target_dir / uv_exe_name
        shutil.move(str(uv_binary), str(dest))
        # Clean up extracted subdirectory
        for d in target_dir.iterdir():
            if d.is_dir() and d.name.startswith("uv-"):
                shutil.rmtree(d)
        uv_binary = dest

    # Ensure executable on Unix
    if os_name != "windows":
        uv_binary.chmod(0o755)

    return uv_binary


def build_wheel(output_dir: Path) -> Path:
    """Build a wheel for the suzent package.

    Returns the path to the .whl file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    print("  Building suzent wheel...")
    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(output_dir)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"  STDOUT: {result.stdout}")
        print(f"  STDERR: {result.stderr}")
        raise RuntimeError("Failed to build suzent wheel")

    wheels = list(output_dir.glob("suzent-*.whl"))
    if not wheels:
        raise RuntimeError(f"No wheel found in {output_dir}")

    wheel_path = wheels[0]
    print(f"  Built wheel: {wheel_path.name}")
    return wheel_path


def copy_config_and_skills(target_dir: Path) -> None:
    """Copy example config files and skills to resources."""
    # Config: only copy example files (no secrets)
    config_dest = target_dir / "config"
    config_dest.mkdir(parents=True, exist_ok=True)

    config_src = PROJECT_ROOT / "config"
    for example_file in config_src.glob("*.example.*"):
        shutil.copy2(str(example_file), str(config_dest / example_file.name))
        print(f"  Copied config: {example_file.name}")

    # Skills: copy entire directory
    skills_src = PROJECT_ROOT / "skills"
    skills_dest = target_dir / "skills"

    if skills_dest.exists():
        shutil.rmtree(skills_dest)

    if skills_src.exists():
        shutil.copytree(str(skills_src), str(skills_dest))
        print("  Copied skills directory")
    else:
        print("  WARNING: No skills directory found")


def generate_shims(target_dir: Path) -> None:
    """Generate CLI shims (suzent.cmd and suzent) in the target directory.

    These shims are moved to the installation root by NSIS hooks (Windows)
    or expected to be in the PATH (Linux/macOS).
    """
    # Windows CMD shim
    cmd_shim = target_dir / "suzent.cmd"
    # %~dp0 returns the drive and path to the batch script.
    # We call SUZENT.exe which should be in the same directory after installation moves.
    cmd_content = '@echo off\r\n"%~dp0SUZENT.exe" %*'
    cmd_shim.write_text(cmd_content, encoding="utf-8")
    print(f"  Generated Windows shim: {cmd_shim.name}")

    # Unix Shell shim
    sh_shim = target_dir / "suzent"
    # $0 is the script path. dirname $0 gets the directory.
    # We assume the binary is named 'suzent' on Linux/macOS
    sh_content = '#!/bin/sh\nexec "$(dirname "$0")/suzent" "$@"'
    sh_shim.write_text(sh_content, encoding="utf-8")
    # Make executable
    if hasattr(os, "chmod"):
        current_mode = sh_shim.stat().st_mode
        sh_shim.chmod(current_mode | 0o111)
    print(f"  Generated Unix shim: {sh_shim.name}")


def bundle_python() -> None:
    """Main bundling function. Creates src-tauri/resources/ with everything needed."""
    print("=" * 50)
    print("  SUZENT Python Backend Bundler")
    print("=" * 50)

    os_name, arch, exe_ext = get_platform_info()
    print(f"\nPlatform: {os_name}/{arch}")

    # Clean previous resources
    if RESOURCES_DIR.exists():
        print("\nCleaning previous resources...")
        shutil.rmtree(RESOURCES_DIR)

    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Download Python
    print("\n[1/4] Downloading Python runtime...")
    python_dir = RESOURCES_DIR / "python"
    python_exe = download_python(python_dir)
    print(f"  Python executable: {python_exe}")

    # Step 2: Download uv
    print("\n[2/4] Downloading uv package manager...")
    uv_exe = download_uv(RESOURCES_DIR)
    print(f"  uv binary: {uv_exe}")

    # Step 3: Build wheel
    print("\n[3/4] Building suzent wheel...")
    wheel_dir = RESOURCES_DIR / "wheel"
    build_wheel(wheel_dir)

    # Step 4: Copy config and skills
    print("\n[4/4] Copying config and skills...")
    copy_config_and_skills(RESOURCES_DIR)

    # Step 5: Generate CLI shims
    print("\n[5/5] Generating CLI shims...")
    generate_shims(RESOURCES_DIR)

    # Summary
    total_size = sum(f.stat().st_size for f in RESOURCES_DIR.rglob("*") if f.is_file())
    total_mb = total_size / (1024 * 1024)

    print("\n" + "=" * 50)
    print(f"  Bundle complete! Total size: {total_mb:.1f} MB")
    print(f"  Output: {RESOURCES_DIR}")
    print("=" * 50)

    # List top-level contents
    print("\nContents:")
    for item in sorted(RESOURCES_DIR.iterdir()):
        if item.is_dir():
            dir_size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
            print(f"  {item.name}/  ({dir_size / (1024 * 1024):.1f} MB)")
        else:
            print(f"  {item.name}  ({item.stat().st_size / (1024 * 1024):.1f} MB)")


if __name__ == "__main__":
    bundle_python()
