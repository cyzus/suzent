#!/usr/bin/env python3
"""Build Python backend executable using Nuitka."""

import subprocess
import sys
import platform
import os
import shutil
from pathlib import Path

# Fix console encoding issues on Windows (especially Chinese Windows)
if platform.system() == "Windows":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())
    # Set UTF-8 encoding for subprocess
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

    # Fallback/Unknown
    print(f"Warning: Unknown platform {system}/{machine}, asking rustc...")
    try:
        return (
            subprocess.check_output(["rustc", "-vV"], text=True)
            .split("host: ")[1]
            .split("\n")[0]
            .strip()
        )
    except Exception:
        return "unknown"


def get_output_name() -> str:
    """Get platform-specific executable name with target triple."""
    triple = get_target_triple()
    ext = ".exe" if platform.system() == "Windows" else ""
    return f"suzent-backend-{triple}{ext}"


def get_platform_flags() -> list[str]:
    """Get platform-specific Nuitka flags."""
    system = platform.system()
    flags = []

    if system == "Windows":
        if is_clang_available():
            flags.append("--clang")
            print("[OK] Using Clang compiler (faster than MSVC)")
        else:
            print(
                "[WARNING] Using MSVC compiler (slower). Install Clang for faster builds:"
            )
            print("  choco install llvm")

    if system == "Darwin":
        flags.append("--macos-create-app-bundle")

    return flags


def is_clang_available() -> bool:
    """Check if Clang is available on the system."""
    try:
        result = subprocess.run(
            ["clang", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def clean_build_artifacts(output_dir: Path) -> None:
    """Clean previous Nuitka build artifacts to avoid file lock issues."""
    build_dirs = [
        output_dir / "server.build",
        output_dir / "server.dist",
        output_dir / "server.onefile-build",
    ]

    for build_dir in build_dirs:
        if build_dir.exists():
            try:
                shutil.rmtree(build_dir)
                print(f"[OK] Cleaned {build_dir.name}")
            except Exception as e:
                print(f"[WARNING] Could not clean {build_dir.name}: {e}")


def build_backend() -> None:
    """Build the Python backend as a standalone executable."""
    system = platform.system()
    project_root = Path(__file__).parent.parent
    output_dir = project_root / "src-tauri" / "binaries"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_name = get_output_name()
    print(f"Building backend for {system}...")

    # Clean previous build artifacts to avoid permission errors
    clean_build_artifacts(output_dir)

    # Get number of CPU cores for parallel compilation
    cpu_count = os.cpu_count() or 4

    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--onefile",
        "--python-flag=no_site",
        "--assume-yes-for-downloads",  # Auto-accept downloads in CI/CD environments
        f"--jobs={cpu_count}",  # Use all available CPU cores for parallel compilation
        "--lto=no",  # Disable LTO - saves 30-40 min on Windows with minimal runtime impact
        "--include-package=suzent",
        "--include-package=crawl4ai",
        "--include-package=lancedb",
        "--include-package=starlette",
        "--include-package=uvicorn",
        "--include-package=smolagents",
        "--include-package=litellm",
        # Include litellm data files (endpoints.json, cost.json, etc.)
        "--include-package-data=gradio_client",
        "--include-package-data=litellm",
        f"--include-data-dir={project_root / 'config'}=config",
        f"--include-data-dir={project_root / 'skills'}=skills",
        f"--output-dir={output_dir}",
        f"--output-filename={output_name}",
        # Exclude heavy unused modules to prevent C compiler heap exhaustion
        "--nofollow-import-to=sqlalchemy.dialects.postgresql",
        "--nofollow-import-to=sqlalchemy.dialects.mysql",
        "--nofollow-import-to=sqlalchemy.dialects.oracle",
        "--nofollow-import-to=sqlalchemy.dialects.mssql",
        "--nofollow-import-to=pytest",  # Exclude testing framework
        "--nofollow-import-to=lancedb.conftest",  # Exclude lancedb test config
        "--nofollow-import-to=litellm.proxy",  # Exclude litellm server/proxy components
        "--nofollow-import-to=pandas.tests",
        "--nofollow-import-to=numpy.tests",
        "--nofollow-import-to=sympy",  # Exclude sympy to prevent MSVC heap exhaustion
        str(project_root / "src" / "suzent" / "server.py"),
        *get_platform_flags(),
    ]

    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print("Build failed!")
        sys.exit(1)

    print(f"\nBackend built successfully: {output_dir / output_name}")


if __name__ == "__main__":
    build_backend()
