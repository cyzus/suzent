"""Mainland China network support shared by the CLI and the backend.

The installer and standalone updater decide whether the machine is behind the
mainland firewall (by probing, not by system language) and record the result
in ``~/.suzent/network-region``. A choice the user made by hand lives in
``~/.suzent/china-mirror`` and ``SUZENT_CHINA_MIRROR`` overrides both. This
module only reads those files; it never probes, so importing it is free.
"""

from __future__ import annotations

import gzip
import io
import json
import os
import platform
import re
import shutil
import sys
import tarfile
import urllib.error
import urllib.request
import zlib
from http.client import HTTPException
from pathlib import Path

REPO = "cyzus/suzent"
MIRROR_RELEASE_BASE = "https://registry.npmmirror.com/-/binary/suzent"
GITHUB_RELEASE_BASE = f"https://github.com/{REPO}/releases/download"
# Release CI also publishes each platform's release files as the npm package
# ``@suzent/desktop-<platform>``, which npmmirror copies without review.
NPM_MIRROR_REGISTRY = "https://registry.npmmirror.com"
GITHUB_REPO_URL = f"https://github.com/{REPO}.git"
# Gitee pull-mirrors the GitHub repository, tags and branches included.
GITEE_REPO_URL = "https://gitee.com/cyzus/suzent.git"
_LATEST_RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"
_LATEST_RELEASE_PAGE = f"https://github.com/{REPO}/releases/latest"
_RELEASE_TAG = re.compile(r"^v\d+\.\d+\.\d+$")
_USER_AGENT = {"User-Agent": "suzent-updater"}

MIRROR_ENV = {
    "UV_DEFAULT_INDEX": "https://pypi.tuna.tsinghua.edu.cn/simple",
    "UV_PYTHON_INSTALL_MIRROR": "https://registry.npmmirror.com/-/binary/python-build-standalone",
    "NPM_CONFIG_REGISTRY": "https://registry.npmmirror.com",
    "PLAYWRIGHT_DOWNLOAD_HOST": "https://npmmirror.com/mirrors/playwright",
    # Playwright's Chromium is a Chrome for Testing build with its own URL
    # layout, except on Linux arm64 (see ``_uses_chrome_for_testing``).
    "PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST": "https://cdn.npmmirror.com/binaries/chrome-for-testing",
}


def _state_dir() -> Path:
    return Path.home() / ".suzent"


def parse_preference(value: str) -> bool | None:
    """On/off from a flag value; ``auto`` and anything unknown mean "detect"."""
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on", "cn", "china"}:
        return True
    if lowered in {"0", "false", "no", "off", "global"}:
        return False
    return None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def china_mode() -> bool:
    explicit = parse_preference(os.environ.get("SUZENT_CHINA_MIRROR", ""))
    if explicit is None:
        explicit = parse_preference(_read(_state_dir() / "china-mirror"))
    if explicit is not None:
        return explicit
    return _read(_state_dir() / "network-region") == "china"


def _uses_chrome_for_testing() -> bool:
    """Playwright fetches its own Chromium builds on Linux arm64, which the
    Chrome for Testing mirror does not carry."""
    return not (
        sys.platform.startswith("linux")
        and platform.machine().lower() in {"aarch64", "arm64"}
    )


def mirror_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """``base`` (default: this process's environment) plus the mirrors in
    China mode. Values already set win."""
    env = dict(os.environ if base is None else base)
    if china_mode():
        for key, value in MIRROR_ENV.items():
            if (
                key == "PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST"
                and not _uses_chrome_for_testing()
            ):
                continue
            if not env.get(key, "").strip():
                env[key] = value
    return env


def repo_sources() -> list[str]:
    """Repositories to fetch the source from when ``origin`` fails."""
    return [GITEE_REPO_URL, GITHUB_REPO_URL] if china_mode() else []


def release_bases(version: str) -> list[str]:
    """Release download bases to try in order for ``version``."""
    override = os.environ.get("SUZENT_RELEASE_BASE_URL", "").strip().rstrip("/")
    if override:
        return [override]
    if version == "latest":
        github = f"https://github.com/{REPO}/releases/latest/download"
        return [github]
    github = f"{GITHUB_RELEASE_BASE}/{version}"
    return [f"{MIRROR_RELEASE_BASE}/{version}", github] if china_mode() else [github]


def release_asset_urls(asset_name: str, version: str) -> list[str]:
    """URLs to try in order for one release file.

    In China mode the npm package for the file's platform comes first: it is
    downloaded and unpacked once, then served as a ``file://`` URL.
    """
    urls = [f"{base}/{asset_name}" for base in release_bases(version)]
    if (
        china_mode()
        and _RELEASE_TAG.match(version)
        and not os.environ.get("SUZENT_RELEASE_BASE_URL", "").strip()
    ):
        package = _npm_release_dir(npm_platform_for(asset_name), version)
        if package is not None and (package / asset_name).is_file():
            urls.insert(0, (package / asset_name).as_uri())
    return urls


_NPM_PLATFORMS = {
    "windows-x86_64": "win32-x64",
    "macos-aarch64": "darwin-arm64",
    "macos-x86_64": "darwin-x64",
    "linux-x86_64": "linux-x64",
}


def npm_platform_for(asset_name: str) -> str:
    """npm platform of the package carrying ``asset_name``. Files every package
    carries, such as SHA256SUMS, come from this machine's."""
    for suffix, npm_platform in _NPM_PLATFORMS.items():
        if suffix in asset_name:
            return npm_platform
    if sys.platform == "win32":
        return "win32-x64"
    if sys.platform == "darwin":
        arm = platform.machine().lower() in {"arm64", "aarch64"}
        return "darwin-arm64" if arm else "darwin-x64"
    return "linux-x64"


def npm_tarball_url(npm_platform: str, version: str) -> str:
    name = f"desktop-{npm_platform}"
    return f"{NPM_MIRROR_REGISTRY}/@suzent/{name}/-/{name}-{version.lstrip('v')}.tgz"


_SAFE_PACKAGE_FILE = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*")


def unpack_npm_package(tarball: bytes, target: Path) -> None:
    """Writes the top-level files of an npm tarball (``package/<name>``) into
    ``target``, ignoring anything nested or that is not a regular file."""
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(tarball))) as archive:
        for member in archive.getmembers():
            name = member.name.removeprefix("package/")
            # A plain file name only: no separators of any platform, drive
            # letters or dot names, so nothing can land outside ``target``.
            if (
                not member.isfile()
                or name == member.name
                or not _SAFE_PACKAGE_FILE.fullmatch(name)
            ):
                continue
            source = archive.extractfile(member)
            if source is not None:
                (target / name).write_bytes(source.read())


_npm_packages: dict[str, Path | None] = {}


def _npm_release_dir(npm_platform: str, version: str) -> Path | None:
    """The unpacked npm package for ``version``, downloaded at most once per
    process and cached under ``~/.suzent/cache``; ``None`` when unavailable."""
    url = npm_tarball_url(npm_platform, version)
    if url in _npm_packages:
        return _npm_packages[url]
    target = _state_dir() / "cache" / "npm" / f"desktop-{npm_platform}" / version
    result: Path | None = target
    if not (target / "SHA256SUMS").is_file():
        try:
            request = urllib.request.Request(url, headers=_USER_AGENT)
            with urllib.request.urlopen(request, timeout=300) as response:
                tarball = response.read()
            staging = target.with_name(f"{version}.partial")
            shutil.rmtree(staging, ignore_errors=True)
            unpack_npm_package(tarball, staging)
            # Only the newest release is worth keeping; each is tens of MB.
            for old in target.parent.iterdir():
                if old != staging:
                    shutil.rmtree(old, ignore_errors=True)
            staging.replace(target)
        except (OSError, EOFError, HTTPException, zlib.error, tarfile.TarError):
            result = None
    _npm_packages[url] = result
    return result


def latest_tag_in_listing(listing: str) -> str:
    """Highest ``vX.Y.Z`` directory in an npmmirror binary listing, or ``""``."""
    try:
        entries = json.loads(listing)
    except json.JSONDecodeError:
        return ""
    if not isinstance(entries, list):
        return ""
    tags = [
        str(entry.get("name", "")).rstrip("/")
        for entry in entries
        if isinstance(entry, dict)
    ]
    stable = [tag for tag in tags if _RELEASE_TAG.match(tag)]
    if not stable:
        return ""
    return max(stable, key=lambda tag: tuple(int(part) for part in tag[1:].split(".")))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D102
        return None


def _latest_from_mirror(timeout: float) -> str:
    request = urllib.request.Request(f"{MIRROR_RELEASE_BASE}/", headers=_USER_AGENT)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        tag = latest_tag_in_listing(response.read().decode("utf-8"))
    if not tag:
        raise ValueError("release mirror lists no stable release")
    return tag


def tag_from_npm_dist_tags(body: str) -> str:
    """``vX.Y.Z`` from npm ``dist-tags``, or ``""``. The 0.0.0 placeholder that
    only exists so Trusted Publishing could be set up does not count."""
    try:
        latest = json.loads(body).get("latest", "")
    except (json.JSONDecodeError, AttributeError):
        return ""
    tag = f"v{latest}"
    return tag if _RELEASE_TAG.match(tag) and tag != "v0.0.0" else ""


def _latest_from_npm(timeout: float) -> str:
    url = (
        f"{NPM_MIRROR_REGISTRY}/-/package/@suzent/"
        f"desktop-{npm_platform_for('')}/dist-tags"
    )
    request = urllib.request.Request(url, headers=_USER_AGENT)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        tag = tag_from_npm_dist_tags(response.read().decode("utf-8"))
    if not tag:
        raise ValueError("npm mirror has no stable release")
    return tag


def _latest_from_api(timeout: float) -> str:
    request = urllib.request.Request(_LATEST_RELEASE_API, headers=_USER_AGENT)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return str(json.loads(response.read()).get("tag_name", ""))


def _latest_from_redirect(timeout: float) -> str:
    # The unauthenticated API allows 60 requests an hour per IP, which shared
    # addresses exhaust; the release page redirect has no such limit.
    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(_LATEST_RELEASE_PAGE, headers=_USER_AGENT)
    try:
        opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        location = error.headers.get("Location", "")
        tag = location.rstrip("/").rsplit("/", 1)[-1]
        if _RELEASE_TAG.match(tag):
            return tag
    raise ValueError("release page did not redirect to a stable tag")


def fetch_latest_release(timeout: float = 10.0) -> dict:
    """``{"tag_name", "html_url"}`` of the newest stable release.

    China mode asks the mirror first, so the version chosen is one the mirror
    already serves; everyone falls back from the API to the release page.
    """
    sources = [_latest_from_api, _latest_from_redirect]
    if china_mode():
        sources[:0] = [_latest_from_npm, _latest_from_mirror]
    errors = []
    for source in sources:
        try:
            tag = source(timeout)
        except (OSError, ValueError) as error:
            errors.append(str(error))
            continue
        if _RELEASE_TAG.match(tag):
            return {
                "tag_name": tag,
                "html_url": f"https://github.com/{REPO}/releases/tag/{tag}",
            }
        errors.append(f"invalid release tag: {tag!r}")
    raise OSError("; ".join(errors) or "no release source available")
