"""Build the self-contained runtime the desktop installers ship.

Produces, for the platform this runs on:

    apps/desktop/resources/runtime/python/   relocatable CPython 3.12 (python-build-standalone,
                                             what uv installs) with Suzent and its locked
                                             dependencies installed, bytecode precompiled
    apps/desktop/resources/suzent/           tracked config/, skills/, plugins/ and
                                             extensions/browser/, plus bundle.json

electron-builder copies both next to the app (see apps/desktop/electron-builder.yml),
and the Electron shell runs `runtime/python -m suzent.server` with
SUZENT_PROJECT_DIR pointing at `suzent/`. Nothing is cloned or synced on the
user's machine.

Usage:
    python scripts/build_desktop_runtime.py              # full build
    python scripts/build_desktop_runtime.py --resources-only
    python scripts/build_desktop_runtime.py --extras social,camera
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "apps" / "desktop" / "resources"
PYTHON_VERSION = "3.12"
# Built-in plugins' extras: an installed app has no uv.lock to resolve them
# against later, so they ship with the runtime, as in the MSIX package.
DEFAULT_EXTRAS = ("social", "camera", "wake")
RESOURCE_PATHS = ("config", "skills", "plugins", "extensions/browser")
# Never imported by Suzent; tkinter also drags in Tcl/Tk.
STRIP = (
    "tcl",
    "Lib/tkinter",
    "Lib/idlelib",
    "Lib/turtledemo",
    "Lib/test",
    "Lib/unittest/test",
    "Lib/lib2to3/tests",
    "DLLs/_tkinter.pyd",
    "DLLs/tcl86t.dll",
    "DLLs/tk86t.dll",
    "lib/tcl8.6",
    "lib/tk8.6",
    "lib/itcl4.2.4",
    "lib/thread2.8.9",
    f"lib/python{PYTHON_VERSION}/tkinter",
    f"lib/python{PYTHON_VERSION}/idlelib",
    f"lib/python{PYTHON_VERSION}/turtledemo",
    f"lib/python{PYTHON_VERSION}/test",
    f"lib/python{PYTHON_VERSION}/unittest/test",
    f"lib/python{PYTHON_VERSION}/lib2to3/tests",
    f"lib/python{PYTHON_VERSION}/lib-dynload/_tkinter.cpython-312-darwin.so",
    f"lib/python{PYTHON_VERSION}/lib-dynload/_tkinter.cpython-312-x86_64-linux-gnu.so",
    f"lib/python{PYTHON_VERSION}/lib-dynload/_tkinter.cpython-312-aarch64-linux-gnu.so",
)


def run(*args: str | Path, capture: bool = False) -> str:
    print("+", " ".join(str(a) for a in args), flush=True)
    result = subprocess.run(
        [str(a) for a in args],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout.strip() if capture else ""


def python_in(runtime: Path) -> Path:
    if sys.platform == "win32":
        return runtime / "python.exe"
    return runtime / "bin" / "python3"


def managed_python_root() -> Path:
    """The uv-managed python-build-standalone install, as a directory to copy."""
    run("uv", "python", "install", PYTHON_VERSION)
    executable = Path(
        run("uv", "python", "find", PYTHON_VERSION, "--managed-python", capture=True)
    ).resolve()
    # python.exe sits at the root on Windows; bin/python3.x elsewhere.
    return executable.parent if sys.platform == "win32" else executable.parent.parent


def copy_runtime(target: Path) -> Path:
    source = managed_python_root()
    print(f"Copying CPython from {source}")
    # Install into a copy: never into uv's own managed interpreter.
    shutil.copytree(source, target, symlinks=True)
    marker = target / "lib" / f"python{PYTHON_VERSION}" / "EXTERNALLY-MANAGED"
    marker.unlink(missing_ok=True)
    (target / "Lib" / "EXTERNALLY-MANAGED").unlink(missing_ok=True)
    return python_in(target)


def install_suzent(python: Path, extras: tuple[str, ...]) -> None:
    requirements = OUT / "requirements.txt"
    args = ["uv", "export", "--frozen", "--no-dev", "--no-editable", "--no-hashes"]
    args += ["--no-emit-project", "-o", str(requirements)]
    for extra in extras:
        args += ["--extra", extra]
    run(*args)
    run("uv", "pip", "install", "--python", python, "-r", requirements)
    run("uv", "pip", "install", "--python", python, "--no-deps", ".")
    requirements.unlink()


def strip(runtime: Path) -> None:
    for relative in STRIP:
        path = runtime / relative
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()
        else:
            continue
        print(f"removed {relative}")
    for helper in (runtime / "DLLs").glob("_test*.pyd"):
        helper.unlink()
    for cache in runtime.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def precompile(python: Path, runtime: Path) -> None:
    # The install dir may be read-only (macOS app bundle, Store package), so
    # every .pyc must exist up front. A few third-party files are Python 2
    # and fail to compile; that is expected.
    subprocess.run(
        [str(python), "-m", "compileall", "-q", "-j", "0", str(runtime)],
        cwd=ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
    )


def verify(python: Path) -> None:
    env = {**os.environ, "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    code = (
        "import suzent.server, lancedb, litellm, pydantic_ai, playwright; "
        "from suzent.version import get_backend_version, get_backend_source_root; "
        "assert get_backend_source_root() is None, 'runtime must not point at a checkout'; "
        "print('suzent', get_backend_version())"
    )
    subprocess.run([str(python), "-c", code], cwd=OUT, env=env, check=True)


def copy_resources(target: Path, version: str) -> None:
    files = run("git", "ls-files", *RESOURCE_PATHS, capture=True).splitlines()
    for relative in files:
        source = ROOT / relative
        if not source.is_file():
            continue
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    (target / "bundle.json").write_text(
        json.dumps({"version": version, "python": PYTHON_VERSION}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Copied {len(files)} resource files to {target}")


def project_version() -> str:
    import tomllib

    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def size_of(path: Path) -> int:
    return sum(
        p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink()
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--extras",
        default=",".join(DEFAULT_EXTRAS),
        help="comma-separated pyproject extras to bundle",
    )
    parser.add_argument(
        "--resources-only",
        action="store_true",
        help="only copy the resource files (no Python runtime)",
    )
    args = parser.parse_args()
    version = project_version()
    extras = tuple(e for e in (x.strip() for x in args.extras.split(",")) if e)

    resources = OUT / "suzent"
    if resources.exists():
        shutil.rmtree(resources)
    copy_resources(resources, version)
    if args.resources_only:
        return

    runtime = OUT / "runtime" / "python"
    if runtime.parent.exists():
        shutil.rmtree(runtime.parent)
    runtime.parent.mkdir(parents=True)
    python = copy_runtime(runtime)
    # `suzent web` serves src/suzent/webui/, which the wheel ships when present.
    if (ROOT / "frontend" / "dist" / "index.html").is_file():
        run(sys.executable, "scripts/build_webui.py", "--no-build")
    install_suzent(python, extras)
    strip(runtime)
    precompile(python, runtime)
    verify(python)
    print(f"Runtime: {size_of(runtime) / 1_048_576:.0f} MB at {runtime}")


if __name__ == "__main__":
    main()
