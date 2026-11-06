"""Programs a plugin needs on the host, downloaded only after the user agrees.

A plugin lists them under ``binaries`` in ``plugin.yaml``. Each one is an npm
package tarball pinned by version and SHA-256, so the same file can come from
registry.npmjs.org or from npmmirror (which copies npm packages without
review) and is checked against the plugin's own hash either way. Only the
files the manifest names for this platform are taken out of the tarball.

Nothing here runs from a tool call: the settings page and the CLI install a
binary after showing the consent text, and tools only ``locate`` it.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from suzent.logger import get_logger

logger = get_logger(__name__)

NPM_REGISTRY = "https://registry.npmjs.org"
NPM_MIRROR = "https://registry.npmmirror.com"
DEFAULT_MAX_BYTES = 100 * 1024 * 1024
_SHA256 = r"^[0-9a-f]{64}$"
_FILE_NAME = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"

type Source = Literal["override", "managed", "path"]


_install_locks: dict[Path, threading.Lock] = {}
_install_locks_guard = threading.Lock()


class BinaryInstallError(Exception):
    """The binary could not be installed. Nothing was left in place."""


class PlatformFiles(BaseModel):
    """What to take from the tarball on one platform.

    ``files`` maps the installed file name to its path inside the tarball;
    the first entry is the executable, the rest sit beside it (helpers the
    executable looks for in its own directory). ``package`` and ``sha256``
    override the binary's own when each platform ships as a separate package.
    """

    model_config = ConfigDict(extra="forbid")

    files: dict[str, str] = Field(min_length=1)
    package: str | None = None
    sha256: str | None = Field(default=None, pattern=_SHA256)

    @model_validator(mode="after")
    def _check_files(self) -> "PlatformFiles":
        for name, member in self.files.items():
            if not re.fullmatch(_FILE_NAME, name):
                raise ValueError(f"installed file name is not safe: {name!r}")
            path = PurePosixPath(member)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError(f"tarball path is not safe: {member!r}")
        return self

    @property
    def executable(self) -> str:
        return next(iter(self.files))


class BinarySpec(BaseModel):
    """One ``binaries`` entry of ``plugin.yaml``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")
    version: str = Field(pattern=r"^[0-9][0-9A-Za-z.+-]{0,63}$")
    package: str | None = None
    sha256: str | None = Field(default=None, pattern=_SHA256)
    max_bytes: int = Field(default=DEFAULT_MAX_BYTES, gt=0, le=500 * 1024 * 1024)
    # An environment variable naming an executable to use instead.
    env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    # Command name to look for on PATH when Suzent has not installed it.
    command: str | None = None
    # Keyed by npm platform names: darwin-arm64, linux-x64, win32-x64, ...
    platforms: dict[str, PlatformFiles] = Field(min_length=1)
    # Arguments to run once after installing, per OS (darwin, linux, win32).
    after_install: dict[str, list[str]] = Field(default_factory=dict)
    # Extra text for the consent prompt, e.g. that the program is unsigned.
    notice: str = ""

    @model_validator(mode="after")
    def _every_platform_has_a_source(self) -> "BinarySpec":
        for key, entry in self.platforms.items():
            if not (entry.package or self.package):
                raise ValueError(f"{self.name}: no npm package for {key}")
            if not (entry.sha256 or self.sha256):
                raise ValueError(f"{self.name}: no sha256 for {key}")
        return self

    def for_platform(self, key: str | None = None) -> PlatformFiles | None:
        return self.platforms.get(key or current_platform())

    def package_for(self, entry: PlatformFiles) -> str:
        return entry.package or self.package or ""

    def sha256_for(self, entry: PlatformFiles) -> str:
        return entry.sha256 or self.sha256 or ""


def current_platform() -> str:
    """This computer in npm's ``<os>-<cpu>`` form."""
    machine = platform.machine().lower()
    if machine in {"aarch64", "arm64"}:
        cpu = "arm64"
    elif machine in {"x86_64", "amd64", "x64"}:
        cpu = "x64"
    else:
        cpu = machine or "unknown"
    os_name = sys.platform if sys.platform in {"darwin", "win32"} else "linux"
    return f"{os_name}-{cpu}"


def tarball_urls(package: str, version: str) -> list[str]:
    """Where npm and npmmirror serve ``package@version``, the closer one first."""
    from suzent.network_region import china_mode

    basename = package.rsplit("/", 1)[-1]
    path = f"{package}/-/{basename}-{version}.tgz"
    registries = (
        [NPM_MIRROR, NPM_REGISTRY] if china_mode() else [NPM_REGISTRY, NPM_MIRROR]
    )
    return [f"{registry}/{path}" for registry in registries]


def install_dir(plugin_id: str, spec: BinarySpec) -> Path:
    from suzent.config.paths import DATA_DIR

    return DATA_DIR / "plugin-bin" / plugin_id / spec.name / spec.version


def managed_executable(plugin_id: str, spec: BinarySpec) -> Path | None:
    """The copy Suzent installed for this plugin, if it is still runnable."""
    entry = spec.for_platform()
    if entry is None:
        return None
    path = install_dir(plugin_id, spec) / entry.executable
    if path.is_file() and os.access(path, os.X_OK):
        return path
    return None


def locate(plugin_id: str, spec: BinarySpec) -> tuple[Path, Source] | None:
    """The executable to run: the env override, then Suzent's copy, then PATH.

    This never downloads anything. A set but unusable override returns None
    rather than quietly running something else.
    """
    if spec.env:
        override = os.environ.get(spec.env, "").strip()
        if override:
            path = Path(override).expanduser()
            if path.is_file() and os.access(path, os.X_OK):
                return path, "override"
            return None
    managed = managed_executable(plugin_id, spec)
    if managed is not None:
        return managed, "managed"
    found = shutil.which(spec.command or spec.name)
    if found:
        return Path(found), "path"
    return None


def status(plugin_id: str, spec: BinarySpec) -> dict[str, Any]:
    """What the plugins page shows, without touching the network."""
    located = locate(plugin_id, spec)
    entry = spec.for_platform()
    return {
        "name": spec.name,
        "version": spec.version,
        "package": spec.package_for(entry) if entry else spec.package,
        "supported": entry is not None,
        "installed": located is not None,
        "path": str(located[0]) if located else None,
        "source": located[1] if located else None,
        "env": spec.env,
        "notice": spec.notice,
    }


@dataclass(frozen=True)
class PluginBinary:
    """A plugin's handle on one of its declared binaries."""

    plugin_id: str
    spec: BinarySpec

    def locate(self) -> tuple[Path, Source] | None:
        return locate(self.plugin_id, self.spec)

    def status(self) -> dict[str, Any]:
        return status(self.plugin_id, self.spec)


class TarballSource:
    """Downloads from the npm registries. Tests swap in a fake."""

    def download(self, url: str, max_bytes: int) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": "suzent"})
        with urllib.request.urlopen(request, timeout=300) as response:
            payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise BinaryInstallError(
                f"The package is larger than {max_bytes // (1024 * 1024)} MB."
            )
        return payload


def install(
    plugin_id: str,
    spec: BinarySpec,
    *,
    source: TarballSource | None = None,
    root: Path | None = None,
    platform_key: str | None = None,
    run_after: bool = True,
) -> dict[str, Any]:
    """Download, verify and unpack the pinned package. Consent is the caller's job."""
    key = platform_key or current_platform()
    entry = spec.for_platform(key)
    if entry is None:
        raise BinaryInstallError(f"{spec.name} {spec.version} is not built for {key}.")
    destination = root or install_dir(plugin_id, spec)
    executable = destination / entry.executable
    # Two settings tabs installing at once would share the staging directory.
    with _install_lock(destination):
        url = _install_into(destination, executable, entry, spec, source)
    if url is not None:
        logger.info(
            "Installed {} {} for plugin {} from {}",
            spec.name,
            spec.version,
            plugin_id,
            url,
        )
    return _result(spec, executable, url, _after(spec, executable, run_after))


def _install_lock(destination: Path) -> threading.Lock:
    with _install_locks_guard:
        return _install_locks.setdefault(destination.resolve(), threading.Lock())


def _install_into(
    destination: Path,
    executable: Path,
    entry: PlatformFiles,
    spec: BinarySpec,
    source: TarballSource | None,
) -> str | None:
    """Unpack into ``destination``; None when a usable copy is already there."""
    if executable.is_file() and os.access(executable, os.X_OK):
        return None
    package = spec.package_for(entry)
    expected = spec.sha256_for(entry)
    payload, url = _download_verified(
        source or TarballSource(), package, spec, expected
    )
    staging = destination.with_name(f".{destination.name}.partial")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        _extract(payload, entry, staging)
        (staging / "install.json").write_text(
            json.dumps(
                {"package": package, "version": spec.version, "sha256": expected},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if destination.exists():
            shutil.rmtree(destination)
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return url


def _download_verified(
    source: TarballSource, package: str, spec: BinarySpec, expected: str
) -> tuple[bytes, str]:
    failures: list[str] = []
    for url in tarball_urls(package, spec.version):
        try:
            payload = source.download(url, spec.max_bytes)
        except (OSError, BinaryInstallError) as exc:
            logger.warning("Download of {} failed: {}", url, exc)
            failures.append(f"{url}: {exc}")
            continue
        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected:
            # A mirror serving other bytes is a reason to stop, not to try the next.
            raise BinaryInstallError(
                f"Checksum mismatch for {package}@{spec.version} from {url}: "
                f"expected {expected}, found {actual}. Nothing was installed."
            )
        return payload, url
    raise BinaryInstallError(
        f"Could not download {package}@{spec.version}. " + " | ".join(failures)[:600]
    )


def _extract(payload: bytes, entry: PlatformFiles, target: Path) -> None:
    wanted = {f"package/{member}": name for name, member in entry.files.items()}
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            for member in archive.getmembers():
                name = wanted.pop(member.name, None)
                if name is None:
                    continue
                if not member.isfile():
                    raise BinaryInstallError(f"{member.name} is not a regular file.")
                data = archive.extractfile(member)
                if data is None:
                    raise BinaryInstallError(f"{member.name} could not be read.")
                path = target / name
                path.write_bytes(data.read())
                path.chmod(
                    path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                )
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise BinaryInstallError(f"The package could not be unpacked: {exc}") from exc
    if wanted:
        missing = ", ".join(sorted(wanted))
        raise BinaryInstallError(f"The package does not contain {missing}.")


def _after(spec: BinarySpec, executable: Path, run: bool) -> str | None:
    args = spec.after_install.get(sys.platform)
    if not run or not args:
        return None
    try:
        subprocess.run([str(executable), *args], timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("{} {} failed after install: {}", spec.name, " ".join(args), exc)
        return "failed"
    return "started"


def _result(
    spec: BinarySpec, executable: Path, url: str | None, after: str | None
) -> dict[str, Any]:
    return {
        "name": spec.name,
        "version": spec.version,
        "installed": True,
        "path": str(executable),
        "source": "managed",
        "downloadedFrom": url,
        "afterInstall": after,
    }
