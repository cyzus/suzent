from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from suzent.config import CACHE_DIR, DATA_DIR, RUNTIME_DIR

PORTABLE_EXCLUDES = {"runtime", "cache", "exports", "backups", ".secret_key"}
MANIFEST_NAME = "manifest.json"


class DataStatus(BaseModel):
    data_dir: str
    runtime_dir: str
    cache_dir: str
    exists: bool
    portable_entries: list[str]


class ExportResult(BaseModel):
    output_path: str
    included: list[str]
    skipped: list[str] = Field(default_factory=list)
    manifest: dict[str, Any]


class ImportPreview(BaseModel):
    archive_path: str
    valid: bool
    manifest: dict[str, Any]
    entries: list[str]


class ImportResult(BaseModel):
    archive_path: str
    data_dir: str
    backup_path: str
    restored_entries: list[str]


def get_data_status() -> DataStatus:
    return DataStatus(
        data_dir=str(DATA_DIR),
        runtime_dir=str(RUNTIME_DIR),
        cache_dir=str(CACHE_DIR),
        exists=DATA_DIR.exists(),
        portable_entries=_portable_entries(DATA_DIR),
    )


def export_data(
    output_path: Path | None = None,
    *,
    include_secrets: bool = False,
) -> ExportResult:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = output_path or _default_export_path()
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    included = _portable_entries(DATA_DIR)
    if include_secrets and (DATA_DIR / ".secret_key").exists():
        included.append(".secret_key")
        included = sorted(set(included))
    manifest = {
        "app": "suzent",
        "format_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_data_dir": str(DATA_DIR),
        "includes": included,
        "secrets": "included" if include_secrets else "excluded",
    }

    skipped: list[str] = []

    with tempfile.TemporaryDirectory(prefix="suzent-export-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
            for name in included:
                path = DATA_DIR / name
                if _safe_is_file(path, skipped):
                    _safe_write_portable_file(
                        zf, path, name, skipped, temp_dir, include_secrets
                    )
                elif _safe_is_dir(path, skipped):
                    for child in path.rglob("*"):
                        if _safe_is_file(child, skipped):
                            _safe_write_portable_file(
                                zf,
                                child,
                                child.relative_to(DATA_DIR).as_posix(),
                                skipped,
                                temp_dir,
                                include_secrets,
                            )

    return ExportResult(
        output_path=str(output_path),
        included=included,
        skipped=skipped,
        manifest=manifest,
    )


def preview_import(archive_path: Path) -> ImportPreview:
    archive_path = archive_path.expanduser().resolve()
    manifest, entries = _read_archive(archive_path)
    return ImportPreview(
        archive_path=str(archive_path),
        valid=True,
        manifest=manifest,
        entries=entries,
    )


def import_data(
    archive_path: Path,
    *,
    mode: Literal["replace"] = "replace",
    dry_run: bool = False,
) -> ImportPreview | ImportResult:
    if mode != "replace":
        raise ValueError(f"Unsupported import mode: {mode}")

    preview = preview_import(archive_path)
    if dry_run:
        return preview

    backup_path = _backup_current_data_dir()
    restored_entries = _restore_archive(archive_path.expanduser().resolve())
    return ImportResult(
        archive_path=preview.archive_path,
        data_dir=str(DATA_DIR),
        backup_path=str(backup_path),
        restored_entries=restored_entries,
    )


def sync_push(target: Path) -> ExportResult:
    target = target.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    return export_data(target / _default_export_name())


def sync_pull(target: Path, *, dry_run: bool = False) -> ImportPreview | ImportResult:
    target = target.expanduser().resolve()
    archives = sorted(
        target.glob("suzent-export-*.zip"), key=lambda p: p.stat().st_mtime
    )
    if not archives:
        raise FileNotFoundError(f"No SUZENT export archives found in {target}")
    return import_data(archives[-1], dry_run=dry_run)


def _portable_entries(root: Path) -> list[str]:
    if not root.exists():
        return []
    entries = []
    for child in root.iterdir():
        if child.name in PORTABLE_EXCLUDES:
            continue
        entries.append(child.name)
    return sorted(entries)


def _safe_is_file(path: Path, skipped: list[str]) -> bool:
    if path.is_symlink():
        skipped.append(_portable_path(path))
        return False
    try:
        return path.is_file()
    except OSError:
        skipped.append(_portable_path(path))
        return False


def _safe_is_dir(path: Path, skipped: list[str]) -> bool:
    if path.is_symlink():
        skipped.append(_portable_path(path))
        return False
    try:
        return path.is_dir()
    except OSError:
        skipped.append(_portable_path(path))
        return False


def _safe_write(
    zf: zipfile.ZipFile,
    path: Path,
    arcname: str,
    skipped: list[str],
) -> None:
    try:
        zf.write(path, arcname)
    except OSError:
        skipped.append(_portable_path(path))


def _safe_write_portable_file(
    zf: zipfile.ZipFile,
    path: Path,
    arcname: str,
    skipped: list[str],
    temp_dir: Path,
    include_secrets: bool = False,
) -> None:
    source: Path | None = path
    if arcname == "chats.db" and not include_secrets:
        source = _scrub_chats_db(path, temp_dir, skipped)
    if source is None:
        return
    _safe_write(zf, source, arcname, skipped)


def _scrub_chats_db(path: Path, temp_dir: Path, skipped: list[str]) -> Path | None:
    scrubbed = temp_dir / "chats.db"
    conn: sqlite3.Connection | None = None
    try:
        shutil.copy2(path, scrubbed)
        conn = sqlite3.connect(scrubbed)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='api_keys'"
        )
        if cursor.fetchone():
            conn.execute("DELETE FROM api_keys")
            conn.commit()
        return scrubbed
    except (OSError, sqlite3.DatabaseError):
        skipped.append(f"{_portable_path(path)}: api_keys scrub failed")
        return None
    finally:
        if conn is not None:
            conn.close()


def _portable_path(path: Path) -> str:
    try:
        return path.relative_to(DATA_DIR).as_posix()
    except ValueError:
        return path.as_posix()


def _default_export_path() -> Path:
    return DATA_DIR / "exports" / _default_export_name()


def _default_export_name() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"suzent-export-{stamp}.zip"


def _read_archive(archive_path: Path) -> tuple[dict[str, Any], list[str]]:
    if not archive_path.exists():
        raise FileNotFoundError(str(archive_path))

    with zipfile.ZipFile(archive_path, "r") as zf:
        if MANIFEST_NAME not in zf.namelist():
            raise ValueError("Archive is missing manifest.json")
        manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
        if manifest.get("app") != "suzent":
            raise ValueError("Archive is not a SUZENT export")
        entries = sorted(
            {
                name.split("/", 1)[0]
                for name in zf.namelist()
                if name != MANIFEST_NAME and not name.startswith("/")
            }
        )
    return manifest, entries


def _backup_current_data_dir() -> Path:
    backup_root = DATA_DIR / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / f"before-import-{_default_export_name()}"
    export_data(backup_path, include_secrets=True)
    return backup_path


def _restore_archive(archive_path: Path) -> list[str]:
    _manifest, entries = _read_archive(archive_path)

    for entry in entries:
        target = DATA_DIR / entry
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

    with zipfile.ZipFile(archive_path, "r") as zf:
        for info in zf.infolist():
            if info.filename == MANIFEST_NAME:
                continue
            target = (DATA_DIR / info.filename).resolve()
            target.relative_to(DATA_DIR.resolve())
            zf.extract(info, DATA_DIR)

    return entries
