"""Cross-platform launcher shortcuts for Suzent.

Every install and update path funnels through here: the Rust installer runs its
``shortcuts`` stage against this module, the standalone updater calls it after
swapping the UI binary, ``scripts/setup.sh`` and ``scripts/setup.ps1`` call it at
the end of a CLI install or update, and ``suzent update --dev`` calls
:func:`install_or_repair` in process. Shortcuts therefore get repaired on every
update regardless of how Suzent was installed.

The entries we own are recorded in ``<workspace>/.suzent/shortcuts.json`` so a
repair can tell an entry Suzent created from one the user made, keep the choices
made at install time, and uninstall cleanly.
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

MANIFEST_VERSION = 1

APPLICATION_MENU = "application_menu"
DESKTOP = "desktop"

_STATE_DIR = ".suzent"
_MANIFEST_NAME = "shortcuts.json"
_APP_NAME = "Suzent"
_DESKTOP_ID = "com.suzent.app"
_COMMAND_TIMEOUT = 120

IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"

# Windows users expect a desktop icon; GNOME marks desktop ``.desktop`` files as
# untrusted and macOS has no desktop-shortcut convention at all, so those two
# only get an application-menu entry unless the user asks for more.
_DESKTOP_DEFAULT = IS_WINDOWS


@dataclass
class ShortcutReport:
    """What a shortcut pass changed, for the CLI and for calling installers."""

    created: list[str] = field(default_factory=list)
    repaired: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    ok: bool = True

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "created": self.created,
            "repaired": self.repaired,
            "kept": self.kept,
            "removed": self.removed,
            "notes": self.notes,
        }

    def summary(self) -> str:
        parts = []
        for label, paths in (
            ("created", self.created),
            ("repaired", self.repaired),
            ("removed", self.removed),
            ("unchanged", self.kept),
        ):
            if paths:
                parts.append(f"{len(paths)} {label}")
        return ", ".join(parts) if parts else "no shortcuts changed"


def manifest_path(root: Path) -> Path:
    return Path(root) / _STATE_DIR / _MANIFEST_NAME


def read_manifest(root: Path) -> dict:
    try:
        data = json.loads(manifest_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("schema") != MANIFEST_VERSION:
        return {}
    return data


def _write_manifest(root: Path, data: dict) -> None:
    path = manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.new")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def ui_binary(root: Path) -> Path | None:
    """Return the stable UI path every shortcut points at, if it is installed."""
    binary = Path(root) / "bin" / ("suzent-ui.exe" if IS_WINDOWS else "suzent-ui")
    return binary if binary.exists() else None


def _workspace_version(root: Path) -> str:
    for candidate in (
        Path(root) / _STATE_DIR / "release-tag",
        Path(root) / "bin" / "version.txt",
    ):
        try:
            value = candidate.read_text(encoding="utf-8").strip().lstrip("v")
        except OSError:
            continue
        if re.fullmatch(r"\d+(\.\d+){0,2}", value):
            return value
    try:
        from importlib.metadata import version

        installed = version("suzent")
    except Exception:
        return ""
    return installed if re.fullmatch(r"\d+(\.\d+){0,2}", installed) else ""


def _run(command: list[str]) -> subprocess.CompletedProcess | None:
    """Run a helper command, returning None when it is unavailable or fails."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result if result.returncode == 0 else None


def _entry(kind: str, path: Path, target: Path) -> dict:
    return {"kind": kind, "path": str(path), "target": str(target)}


def install_or_repair(
    root: Path,
    *,
    application_menu: bool | None = None,
    desktop: bool | None = None,
) -> ShortcutReport:
    """Create Suzent's launcher entries, or bring existing ones back in line.

    Safe to run on every update: entries that already point at the right binary
    are left untouched, missing ones are recreated, and stale ones are rewritten.
    ``application_menu`` and ``desktop`` override the choices stored at install
    time and are remembered for later repairs.
    """
    root = Path(root).resolve()
    report = ShortcutReport()
    manifest = read_manifest(root)
    entries = {
        entry["kind"]: entry
        for entry in manifest.get("entries", [])
        if isinstance(entry, dict) and entry.get("kind") and entry.get("path")
    }
    options = dict(manifest.get("options") or {})
    if application_menu is not None:
        options[APPLICATION_MENU] = application_menu
    if desktop is not None:
        options[DESKTOP] = desktop
    options.setdefault(APPLICATION_MENU, True)
    options.setdefault(DESKTOP, _DESKTOP_DEFAULT)

    binary = ui_binary(root)
    if binary is None:
        report.ok = False
        report.notes.append(
            f"desktop UI binary is missing from {root / 'bin'}; shortcuts left unchanged"
        )
        return report

    wanted: list[str] = []
    if options[APPLICATION_MENU]:
        wanted.append(APPLICATION_MENU)
    if options[DESKTOP]:
        # A desktop shortcut is optional, so a missing one during a repair means
        # the user deleted it. Recreating it on every update would be rude.
        previous = entries.get(DESKTOP)
        if desktop is None and previous and not Path(previous["path"]).exists():
            options[DESKTOP] = False
            report.notes.append(
                "desktop shortcut was removed by the user; leaving it out"
            )
        else:
            wanted.append(DESKTOP)

    if IS_MACOS and DESKTOP in wanted and APPLICATION_MENU not in wanted:
        wanted.append(APPLICATION_MENU)

    retained = dict(entries)
    for kind, entry in sorted(entries.items(), key=lambda item: item[0] != DESKTOP):
        if kind in wanted:
            continue
        if _remove_entry(entry, report):
            retained.pop(kind, None)

    if IS_WINDOWS:
        current = _apply_windows(root, binary, wanted, entries, report)
    elif IS_MACOS:
        current = _apply_macos(root, binary, wanted, report)
    else:
        current = _apply_linux(root, binary, wanted, report)

    for entry in current:
        retained[entry["kind"]] = entry

    _write_manifest(
        root,
        {
            "schema": MANIFEST_VERSION,
            "platform": sys.platform,
            "workspace": str(root),
            "target": str(binary),
            "options": options,
            "entries": list(retained.values()),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )
    return report


def remove(root: Path) -> ShortcutReport:
    """Remove recorded entries and verified legacy launchers, retaining failures."""
    root = Path(root).resolve()
    report = ShortcutReport()
    manifest = read_manifest(root)
    remaining = []
    entries = [
        entry
        for entry in manifest.get("entries", [])
        if isinstance(entry, dict) and entry.get("path")
    ]
    recorded = {entry.get("path") for entry in entries if isinstance(entry, dict)}
    binary = root / "bin" / ("suzent-ui.exe" if IS_WINDOWS else "suzent-ui")
    for legacy in _legacy_paths(root):
        if str(legacy) not in recorded and _legacy_owned(legacy, binary):
            entries.append(_entry(APPLICATION_MENU, legacy, binary))
    # Remove aliases before their bundles so ownership can still be checked.
    entries.sort(key=lambda entry: entry.get("kind") != DESKTOP)
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("path"):
            continue
        if not _remove_entry(entry, report):
            remaining.append(entry)
    if remaining:
        manifest.update(schema=MANIFEST_VERSION, entries=remaining)
        _write_manifest(root, manifest)
    else:
        manifest_path(root).unlink(missing_ok=True)
    return report


def _remove_entry(entry: dict, report: ShortcutReport) -> bool:
    path = Path(entry["path"])
    if not path.exists() and not path.is_symlink():
        return True
    if IS_MACOS and not _macos_owned(path, Path(entry.get("target", ""))):
        report.ok = False
        report.notes.append(f"leaving unrecognized launcher intact: {path}")
        return False
    if _remove_path(path):
        report.removed.append(str(path))
        return True
    report.ok = False
    report.notes.append(f"could not remove {path}; retry 'suzent shortcuts --remove'")
    return False


def _macos_owned(path: Path, binary: Path) -> bool:
    try:
        launcher = (path / "Contents" / "MacOS" / _APP_NAME).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    root = binary.parent.parent
    return launcher in (
        f'#!/bin/sh\nexec "{binary}" "$@"\n',
        f'#!/bin/sh\ncd {shlex.quote(str(root))}\nexec {shlex.quote(str(binary))} "$@"\n',
    )


def _legacy_owned(path: Path, binary: Path) -> bool:
    if IS_MACOS:
        return _macos_owned(path, binary)
    try:
        return (
            f"Exec={_desktop_quote(binary)}"
            in path.read_text(encoding="utf-8").splitlines()
        )
    except (OSError, UnicodeError):
        return False


def _remove_path(path: Path) -> bool:
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
            return True
        if path.is_dir():
            shutil.rmtree(path)
            return True
    except OSError:
        return False
    return False


def _legacy_paths(root: Path) -> list[Path]:
    """Entries written by installers that predate the manifest."""
    home = Path.home()
    if IS_WINDOWS:
        return []
    if IS_MACOS:
        return [home / "Applications" / f"{_APP_NAME}.app", root / f"{_APP_NAME}.app"]
    return [home / ".local" / "share" / "applications" / "suzent.desktop"]


# ── Windows ───────────────────────────────────────────────────────────────────


def _apply_windows(
    root: Path,
    binary: Path,
    wanted: list[str],
    entries: dict[str, dict],
    report: ShortcutReport,
) -> list[dict]:
    if not wanted:
        return []

    # Desktop and Start Menu can be redirected (OneDrive, roaming profiles), so
    # the folders are resolved by Windows itself rather than guessed from $HOME.
    folders = {
        APPLICATION_MENU: "Programs",
        DESKTOP: "DesktopDirectory",
    }
    requests = "; ".join(
        f"@{{ kind = '{kind}'; folder = '{folders[kind]}' }}" for kind in wanted
    )
    script = (
        "$ErrorActionPreference = 'Stop'; "
        f"$ui = '{_ps_quote(binary)}'; "
        f"$workspace = '{_ps_quote(root)}'; "
        f"$requests = @({requests}); "
        "$shell = New-Object -ComObject WScript.Shell; "
        "foreach ($request in $requests) { "
        "  $dir = [Environment]::GetFolderPath($request.folder); "
        "  if ([string]::IsNullOrWhiteSpace($dir)) { "
        '    Write-Output ("skipped`t" + $request.kind + "`t"); continue }; '
        "  New-Item -ItemType Directory -Force -Path $dir | Out-Null; "
        f"  $path = Join-Path $dir '{_APP_NAME}.lnk'; "
        "  $link = $shell.CreateShortcut($path); "
        "  $state = if ($link.TargetPath -eq $ui -and $link.WorkingDirectory -eq $workspace) "
        "    { 'kept' } elseif (Test-Path -LiteralPath $path) { 'repaired' } else { 'created' }; "
        "  if ($state -ne 'kept') { "
        "    $link.TargetPath = $ui; "
        "    $link.WorkingDirectory = $workspace; "
        "    $link.IconLocation = $ui; "
        "    $link.Description = 'Suzent'; "
        "    $link.Save() }; "
        '  Write-Output ($state + "`t" + $request.kind + "`t" + $path) }'
    )

    result = _run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ]
    )
    if result is None:
        report.ok = False
        report.notes.append(
            "Windows shortcut creation failed; run 'suzent shortcuts' after the update"
        )
        return [entries[kind] for kind in wanted if kind in entries]

    buckets = {
        "created": report.created,
        "repaired": report.repaired,
        "kept": report.kept,
    }
    current: list[dict] = []
    for line in result.stdout.splitlines():
        state, _, rest = line.partition("\t")
        kind, _, path = rest.partition("\t")
        if kind not in wanted:
            continue
        if state not in buckets or not path:
            report.ok = False
            report.notes.append(f"Windows did not report a folder for the {kind} entry")
            continue
        buckets[state].append(path)
        current.append(_entry(kind, Path(path), binary))
    return current


def _ps_quote(value: Path | str) -> str:
    return str(value).replace("'", "''")


# ── macOS ─────────────────────────────────────────────────────────────────────


def _apply_macos(
    root: Path,
    binary: Path,
    wanted: list[str],
    report: ShortcutReport,
) -> list[dict]:
    if not wanted:
        return []

    current: list[dict] = []
    bundle = Path.home() / "Applications" / f"{_APP_NAME}.app"
    if APPLICATION_MENU not in wanted:
        report.notes.append(
            "a Desktop alias needs the ~/Applications bundle, so it was kept"
        )
    if not _write_macos_bundle(root, binary, bundle, report):
        return current
    current.append(_entry(APPLICATION_MENU, bundle, binary))
    _remove_legacy_macos_bundle(root, report)

    if DESKTOP in wanted:
        # Launchpad and Spotlight both read ~/Applications; a second copy on the
        # Desktop would only duplicate the bundle, so alias it instead.
        alias = Path.home() / "Desktop" / f"{_APP_NAME}.app"
        state = _link_macos_alias(bundle, alias)
        if state is None:
            report.ok = False
            report.notes.append(f"could not create {alias}")
        else:
            getattr(report, state).append(str(alias))
            current.append(_entry(DESKTOP, alias, binary))
    return current


def _remove_legacy_macos_bundle(root: Path, report: ShortcutReport) -> None:
    """Drop the in-workspace bundle that installers before the manifest created."""
    legacy = root / f"{_APP_NAME}.app"
    binary = root / "bin" / "suzent-ui"
    if _macos_owned(legacy, binary):
        _remove_entry(_entry(APPLICATION_MENU, legacy, binary), report)


def _write_macos_bundle(
    root: Path, binary: Path, bundle: Path, report: ShortcutReport
) -> bool:
    """Build the wrapper .app that gives the bare release binary a name and icon."""
    launcher = f'#!/bin/sh\ncd {shlex.quote(str(root))}\nexec {shlex.quote(str(binary))} "$@"\n'
    plist = _macos_plist(_workspace_version(root))
    icon = root / "src-tauri" / "icons" / "icon.icns"
    icon_bytes = icon.read_bytes() if icon.exists() else None

    if not bundle.is_symlink() and _macos_bundle_matches(
        bundle, launcher, plist, icon_bytes
    ):
        report.kept.append(str(bundle))
        return True

    existed = bundle.exists() or bundle.is_symlink()
    old_targets = [binary]
    for entry in read_manifest(root).get("entries", []):
        if entry.get("path") == str(bundle) and entry.get("target"):
            old_targets.append(Path(entry["target"]))
    if existed and not any(_macos_owned(bundle, target) for target in old_targets):
        report.ok = False
        report.notes.append(f"leaving unrecognized launcher intact: {bundle}")
        return False
    staging: Path | None = None
    previous: Path | None = None
    try:
        bundle.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{bundle.name}.", dir=bundle.parent))
        previous = staging / "previous"
        replacement = staging / "replacement"
        contents = replacement / "Contents"
        (contents / "MacOS").mkdir(parents=True)
        (contents / "Resources").mkdir(parents=True)
        (contents / "Info.plist").write_bytes(plist)
        executable = contents / "MacOS" / _APP_NAME
        executable.write_text(launcher, encoding="utf-8")
        executable.chmod(0o755)
        if icon_bytes is not None:
            (contents / "Resources" / "icon.icns").write_bytes(icon_bytes)

        # A rename onto an existing bundle fails, so the old one steps aside
        # first and is only discarded once the new bundle is in place.
        if existed:
            bundle.rename(previous)
        try:
            replacement.rename(bundle)
        except OSError:
            if previous.exists() or previous.is_symlink():
                previous.rename(bundle)
            raise
        _remove_path(previous)
        staging.rmdir()
    except OSError as error:
        if staging is not None and (
            previous is None or (not previous.exists() and not previous.is_symlink())
        ):
            shutil.rmtree(staging, ignore_errors=True)
        report.ok = False
        report.notes.append(f"could not write {bundle}: {error}")
        return False

    (report.repaired if existed else report.created).append(str(bundle))
    _register_macos_bundle(bundle)
    return True


def _macos_bundle_matches(
    bundle: Path, launcher: str, plist: bytes, icon_bytes: bytes | None
) -> bool:
    contents = bundle / "Contents"
    try:
        if (contents / "Info.plist").read_bytes() != plist:
            return False
        if (contents / "MacOS" / _APP_NAME).read_text(encoding="utf-8") != launcher:
            return False
        if icon_bytes is not None:
            if (contents / "Resources" / "icon.icns").read_bytes() != icon_bytes:
                return False
    except OSError:
        return False
    return True


def _macos_plist(version: str) -> bytes:
    info: dict[str, object] = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleDisplayName": _APP_NAME,
        "CFBundleExecutable": _APP_NAME,
        "CFBundleIconFile": "icon.icns",
        "CFBundleIdentifier": _DESKTOP_ID,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": _APP_NAME,
        "CFBundlePackageType": "APPL",
        "CFBundleSignature": "????",
        "LSMinimumSystemVersion": "10.13",
        "NSHighResolutionCapable": True,
    }
    if version:
        info["CFBundleShortVersionString"] = version
        info["CFBundleVersion"] = version
    return plistlib.dumps(info, sort_keys=True)


def _register_macos_bundle(bundle: Path) -> None:
    """Tell Launch Services about the rebuilt bundle so the icon refreshes."""
    lsregister = Path(
        "/System/Library/Frameworks/CoreServices.framework/Frameworks"
        "/LaunchServices.framework/Support/lsregister"
    )
    if lsregister.exists():
        _run([str(lsregister), "-f", str(bundle)])


def _link_macos_alias(source: Path, alias: Path) -> str | None:
    if alias.is_symlink() and os.readlink(alias) == str(source):
        return "kept"
    existed = alias.exists() or alias.is_symlink()
    if existed:
        return None
    try:
        alias.parent.mkdir(parents=True, exist_ok=True)
        if existed and not _remove_path(alias):
            return None
        alias.symlink_to(source, target_is_directory=True)
    except OSError:
        return None
    return "repaired" if existed else "created"


# ── Linux ─────────────────────────────────────────────────────────────────────


def _apply_linux(
    root: Path,
    binary: Path,
    wanted: list[str],
    report: ShortcutReport,
) -> list[dict]:
    if not wanted:
        return []

    current: list[dict] = []
    icon_name = _install_linux_icons(root)
    content = _linux_desktop_entry(root, binary, icon_name)

    applications = Path.home() / ".local" / "share" / "applications"
    if APPLICATION_MENU in wanted:
        entry = applications / f"{_DESKTOP_ID}.desktop"
        if _write_linux_desktop_file(entry, content, report):
            current.append(_entry(APPLICATION_MENU, entry, binary))
            # Installers before the manifest wrote an unprefixed copy, which
            # would otherwise show up as a second menu entry.
            legacy = applications / "suzent.desktop"
            if _legacy_owned(legacy, binary):
                _remove_entry(_entry(APPLICATION_MENU, legacy, binary), report)

    if DESKTOP in wanted:
        desktop_dir = _linux_desktop_dir()
        entry = desktop_dir / f"{_DESKTOP_ID}.desktop"
        if _write_linux_desktop_file(entry, content, report):
            _trust_linux_desktop_file(entry)
            current.append(_entry(DESKTOP, entry, binary))

    if APPLICATION_MENU in wanted and shutil.which("update-desktop-database"):
        _run(["update-desktop-database", str(applications)])
    return current


def _write_linux_desktop_file(path: Path, content: str, report: ShortcutReport) -> bool:
    try:
        existed = path.exists()
        if existed and path.read_text(encoding="utf-8") == content:
            report.kept.append(str(path))
            return True
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)
    except OSError as error:
        report.ok = False
        report.notes.append(f"could not write {path}: {error}")
        return False
    (report.repaired if existed else report.created).append(str(path))
    return True


def _linux_desktop_entry(root: Path, binary: Path, icon: str) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={_APP_NAME}\n"
        "Comment=Your personal agent\n"
        f"Exec={_desktop_quote(binary)}\n"
        f"Path={root}\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=Utility;Development;\n"
        "StartupNotify=true\n"
        "StartupWMClass=SUZENT\n"
    )


def _desktop_quote(value: Path | str) -> str:
    escaped = str(value)
    for character in ("\\", '"', "$", "`"):
        escaped = escaped.replace(character, f"\\{character}")
    return f'"{escaped}"'


def _linux_desktop_dir() -> Path:
    result = _run(["xdg-user-dir", "DESKTOP"])
    if result is not None:
        directory = result.stdout.strip()
        if directory:
            return Path(directory)
    return Path.home() / "Desktop"


def _install_linux_icons(root: Path) -> str:
    """Install the app icon into the hicolor theme, falling back to the binary."""
    sources = {
        "128x128": root / "src-tauri" / "icons" / "128x128.png",
        "256x256": root / "src-tauri" / "icons" / "128x128@2x.png",
    }
    hicolor = Path.home() / ".local" / "share" / "icons" / "hicolor"
    installed = False
    for size, source in sources.items():
        if not source.exists():
            continue
        destination = hicolor / size / "apps" / f"{_DESKTOP_ID}.png"
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = source.read_bytes()
            if not destination.exists() or destination.read_bytes() != data:
                destination.write_bytes(data)
            installed = True
        except OSError:
            continue
    if not installed:
        return str(root / "src-tauri" / "icons" / "icon.png")
    if shutil.which("gtk-update-icon-cache"):
        _run(["gtk-update-icon-cache", "--quiet", "--ignore-theme-index", str(hicolor)])
    return _DESKTOP_ID


def _trust_linux_desktop_file(path: Path) -> None:
    """GNOME hides desktop launchers it does not trust; mark ours as launchable."""
    if shutil.which("gio"):
        _run(["gio", "set", str(path), "metadata::trusted", "true"])
