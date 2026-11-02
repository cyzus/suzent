"""Install a pinned agent-desktop 1.0.x release after the user agrees.

Nothing in this module runs unless a caller has already collected consent.
Tool calls never reach it. The download is the GitHub release archive for
this computer, checked against the checksum published with that release.
``npm install -g`` is used only when the release has no archive for this
platform. The platform helper stays beside the executable because the CLI
looks for it there.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable

from suzent.config.paths import DATA_DIR
from suzent.logger import get_logger

logger = get_logger(__name__)

PINNED_VERSION = "1.0.2"
REPO = "vercel-labs/agent-desktop"
RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/tags/v{PINNED_VERSION}"
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024

CONSENT_TEXT = (
    f"Suzent will download agent-desktop {PINNED_VERSION} from GitHub into its "
    "own folder and check the checksum published with that release. When the "
    "GitHub CLI is available it also checks the build attestation. The program "
    "can read and operate the apps on this computer; that is separate from the "
    "chat sandbox.\n"
    "On Windows the release binary is unsigned. SmartScreen, antivirus software, "
    "or Smart App Control may block it.\n"
    "On macOS, Accessibility permission is still required. Suzent opens "
    "`agent-desktop permissions --guide` after a successful install.\n"
    "If this computer has no published archive, Suzent falls back to "
    f"`npm install -g agent-desktop@{PINNED_VERSION}`."
)


class DesktopInstallError(Exception):
    """The release could not be installed. Nothing was left in place."""


class ReleaseSource:
    """The GitHub release API and its asset downloads."""

    def fetch_release(self) -> dict[str, Any]:
        return _read_json(RELEASE_API)

    def download(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": "suzent"})
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read(MAX_ARCHIVE_BYTES + 1)
        if len(payload) > MAX_ARCHIVE_BYTES:
            raise DesktopInstallError("The release archive is larger than 50 MB.")
        return payload


def install_root() -> Path:
    """Directory that holds the verified 1.0.x tree."""
    return DATA_DIR / "agent-desktop" / PINNED_VERSION


def runtime_status() -> dict[str, Any]:
    """Where the CLI would come from, without downloading anything."""
    located = _locate()
    return {
        "installed": located is not None,
        "path": str(located[0]) if located else None,
        "source": located[1] if located else None,
        "version": PINNED_VERSION,
        "consent": CONSENT_TEXT,
    }


def managed_executable() -> Path | None:
    """The binary Suzent installed, if that tree is still runnable."""
    root = install_root()
    if not root.is_dir():
        return None
    binary = _find_executable(root)
    if binary is not None and os.access(binary, os.X_OK):
        return binary
    return None


def install_release(
    *,
    source: ReleaseSource | None = None,
    root: Path | None = None,
    attest: Callable[[Path], str] | None = None,
    npm_install: Callable[[], Path] | None = None,
    open_guide: Callable[[Path], str] | None = None,
) -> dict[str, Any]:
    """Download and verify the pinned release. Consent is the caller's job."""
    client = source or ReleaseSource()
    destination = root or install_root()
    existing = _find_executable(destination) if destination.is_dir() else None
    if existing is not None and os.access(existing, os.X_OK):
        guide = (open_guide or open_permissions_guide)(existing)
        return _result(existing, "managed", guide, attestation="already-installed")

    release = client.fetch_release()
    name = asset_name()
    asset = next(
        (item for item in release.get("assets", []) if item.get("name") == name),
        None,
    )
    if asset is None:
        binary = (npm_install or _npm_install)()
        guide = (open_guide or open_permissions_guide)(binary)
        return _result(binary, "npm", guide, attestation="not-applicable")

    checksum_asset = next(
        (
            item
            for item in release.get("assets", [])
            if item.get("name") == "checksums.txt"
        ),
        None,
    )
    archive_url = str(asset.get("browser_download_url") or "")
    if not archive_url:
        raise DesktopInstallError(f"The {name} asset has no download URL.")
    expected = _expected_checksum(client, asset, checksum_asset, name)
    payload = client.download(archive_url)
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise DesktopInstallError(
            f"Checksum mismatch for {name}: expected {expected}, found {actual}. "
            "The archive was not installed."
        )

    staging = destination.parent / f".{destination.name}.partial"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    archive_path = staging / name
    try:
        archive_path.write_bytes(payload)
        attestation = (attest or verify_attestation)(archive_path)
        _extract(archive_path, staging / "tree")
        binary = _find_executable(staging / "tree")
        if binary is None:
            raise DesktopInstallError(
                f"{name} does not contain the agent-desktop executable."
            )
        _mark_executable(binary)
        for sibling in binary.parent.iterdir():
            if sibling.is_file():
                _mark_executable(sibling)
        manifest = {
            "version": PINNED_VERSION,
            "sha256": actual,
            "asset": name,
            "attestation": attestation,
        }
        (binary.parent / "install.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Keep the directory that holds the executable and its helper.
        binary.parent.rename(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if destination.exists() and _find_executable(destination) is None:
            shutil.rmtree(destination, ignore_errors=True)
        raise
    else:
        shutil.rmtree(staging, ignore_errors=True)

    installed = _find_executable(destination)
    if installed is None:
        raise DesktopInstallError("The install finished without an executable.")
    guide = (open_guide or open_permissions_guide)(installed)
    logger.info(
        "Installed agent-desktop {} at {} (attestation={})",
        PINNED_VERSION,
        installed,
        attestation,
    )
    return _result(installed, "managed", guide, attestation=attestation)


def asset_name(version: str = PINNED_VERSION) -> str:
    """Release archive for this OS and CPU. The CLI builds are tar.gz."""
    machine = platform.machine().lower()
    if machine in {"aarch64", "arm64"}:
        arch = "aarch64"
    elif machine in {"x86_64", "amd64", "x64"}:
        arch = "x86_64"
    else:
        arch = machine or "unknown"
    if sys.platform == "darwin":
        system = "apple-darwin"
    elif sys.platform == "win32":
        system = "pc-windows-msvc"
    else:
        system = "unknown-linux-gnu"
    return f"agent-desktop-v{version}-{arch}-{system}.tar.gz"


def verify_attestation(archive: Path) -> str:
    """Check GitHub build provenance when ``gh`` is installed.

    The checksum is always required. Attestation is an extra origin check the
    release publishes; without the GitHub CLI we cannot run it.
    """
    gh = shutil.which("gh")
    if gh is None:
        return "checksum-only"
    completed = subprocess.run(
        [
            gh,
            "attestation",
            "verify",
            str(archive),
            "--repo",
            REPO,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise DesktopInstallError(
            "The release archive failed GitHub attestation verification and was "
            f"not installed. {detail[:400]}"
        )
    return "verified"


def open_permissions_guide(binary: Path) -> str:
    """Open the macOS Accessibility guide. Other systems need no grant here."""
    if sys.platform != "darwin":
        return "not_needed"
    try:
        subprocess.run(
            [str(binary), "permissions", "--guide"],
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("Could not open the Accessibility guide: {}", exc)
        return "failed"
    return "started"


def _npm_install() -> Path:
    npm = shutil.which("npm")
    if npm is None:
        raise DesktopInstallError(
            f"No agent-desktop {PINNED_VERSION} archive is published for this "
            "computer, and npm is not installed."
        )
    completed = subprocess.run(
        [npm, "install", "-g", f"agent-desktop@{PINNED_VERSION}"],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise DesktopInstallError(
            f"npm install of agent-desktop@{PINNED_VERSION} failed. {detail[:400]}"
        )
    found = shutil.which("agent-desktop")
    if found is None:
        raise DesktopInstallError(
            "npm reported success but agent-desktop is not on PATH."
        )
    return Path(found)


def _locate() -> tuple[Path, str] | None:
    override = os.environ.get("SUZENT_AGENT_DESKTOP_BIN", "").strip()
    if override:
        path = Path(override).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return path, "override"
        return None
    managed = managed_executable()
    if managed is not None:
        return managed, "managed"
    found = shutil.which("agent-desktop")
    if found:
        return Path(found), "path"
    return None


def _result(
    binary: Path, source: str, guide: str, *, attestation: str
) -> dict[str, Any]:
    return {
        "installed": True,
        "path": str(binary),
        "source": source,
        "version": PINNED_VERSION,
        "consent": CONSENT_TEXT,
        "permissionsGuide": guide,
        "attestation": attestation,
    }


def _expected_checksum(
    client: ReleaseSource,
    asset: dict[str, Any],
    checksum_asset: dict[str, Any] | None,
    name: str,
) -> str:
    from_digest = _digest(asset.get("digest"))
    from_file: str | None = None
    if checksum_asset and checksum_asset.get("browser_download_url"):
        text = client.download(str(checksum_asset["browser_download_url"])).decode(
            "utf-8", errors="replace"
        )
        from_file = _checksum_entry(text, name)
    if from_digest and from_file and from_digest != from_file:
        raise DesktopInstallError(
            "The release checksum file and the asset digest disagree. "
            "The archive was not installed."
        )
    expected = from_file or from_digest
    if not expected:
        raise DesktopInstallError(
            f"The {PINNED_VERSION} release does not publish a checksum for {name}."
        )
    return expected


def _digest(value: Any) -> str | None:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return None
    digest = value.split(":", 1)[1].strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        return None
    return digest


def _checksum_entry(contents: str, name: str) -> str | None:
    for line in contents.splitlines():
        parts = line.strip().split()
        if len(parts) != 2:
            continue
        digest, filename = parts
        if filename.lstrip("*") == name and len(digest) == 64:
            return digest.lower()
    return None


def _extract(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(archive.read_bytes())) as bundle:
            for info in bundle.infolist():
                _reject_unsafe_path(info.filename)
            bundle.extractall(dest)
        return
    with tarfile.open(archive, "r:*") as bundle:
        bundle.extractall(dest, filter="data")


def _reject_unsafe_path(name: str) -> None:
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise DesktopInstallError(f"Archive path is not safe: {name}")


def _find_executable(root: Path) -> Path | None:
    names = ("agent-desktop.exe", "agent-desktop")
    found = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.name in names and ".partial" not in path.parts
    ]
    if not found:
        return None
    return min(found, key=lambda path: len(path.parts))


def _mark_executable(path: Path) -> None:
    if not path.is_file():
        return
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _read_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "suzent",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise DesktopInstallError("The GitHub release response was not an object.")
    return payload
