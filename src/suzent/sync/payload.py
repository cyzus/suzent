from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from suzent.config import CONFIG, DATA_DIR, USER_CONFIG_DIR, USER_SKILLS_DIR
from suzent.sync.models import DevicePresence, SyncManifest, SyncProfile

PAYLOAD_DIR_NAME = "suzent-sync"
MANIFEST_PATH = "_sync/manifest.json"
PRESENCE_DIR = "_sync/presence"

EXCLUDED_NAMES = {
    ".env",
    ".secret_key",
    "backups",
    "cache",
    "chats.db",
    "exports",
    "local.yaml",
    "runtime",
    "secrets.db",
    "sessions",
    "sync_secret.key",
    "sync_profiles.json",
}
EXCLUDED_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


class SyncPayloadBuilder:
    def __init__(
        self,
        *,
        data_dir: Path = DATA_DIR,
        user_config_dir: Path = USER_CONFIG_DIR,
        user_skills_dir: Path = USER_SKILLS_DIR,
        sandbox_data_path: Path | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.user_config_dir = user_config_dir
        self.user_skills_dir = user_skills_dir
        self.sandbox_data_path = sandbox_data_path or Path(CONFIG.sandbox_data_path)

    def build(self, repo_path: Path, profile: SyncProfile) -> SyncManifest:
        payload_dir = repo_path / PAYLOAD_DIR_NAME
        if payload_dir.exists():
            shutil.rmtree(payload_dir)
        payload_dir.mkdir(parents=True, exist_ok=True)

        self._copy_tree(self.user_config_dir, payload_dir / "config")
        self._copy_tree(self.user_skills_dir, payload_dir / "skills")
        self._copy_tree(self._memory_dir(), payload_dir / "memory")

        presence = DevicePresence(
            device_id=profile.device_id,
            device_name=_device_name(),
            status="online",
            last_sync_revision=profile.last_revision,
        )
        presence_path = payload_dir / PRESENCE_DIR / f"{profile.device_id}.json"
        presence_path.parent.mkdir(parents=True, exist_ok=True)
        presence_path.write_text(presence.model_dump_json(indent=2), encoding="utf-8")

        hashes = self.content_hashes(payload_dir)
        manifest = SyncManifest(
            revision_id=uuid4().hex,
            source_device=profile.device_id,
            included_paths=sorted(hashes),
            content_hashes=hashes,
        )
        manifest_path = payload_dir / MANIFEST_PATH
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return manifest

    def content_hashes(self, payload_dir: Path) -> dict[str, str]:
        hashes: dict[str, str] = {}
        if not payload_dir.exists():
            return hashes
        for path in sorted(p for p in payload_dir.rglob("*") if p.is_file()):
            rel = path.relative_to(payload_dir).as_posix()
            if rel == MANIFEST_PATH:
                continue
            hashes[rel] = _sha256(path)
        return hashes

    def validate_no_forbidden_paths(self, payload_dir: Path) -> list[str]:
        forbidden: list[str] = []
        if not payload_dir.exists():
            return forbidden
        for path in payload_dir.rglob("*"):
            rel_parts = path.relative_to(payload_dir).parts
            if any(_is_excluded_name(part) for part in rel_parts):
                forbidden.append(path.relative_to(payload_dir).as_posix())
            elif path.is_file() and path.suffix.lower() in EXCLUDED_SUFFIXES:
                forbidden.append(path.relative_to(payload_dir).as_posix())
        return sorted(set(forbidden))

    def apply_to_local(self, payload_dir: Path) -> list[str]:
        restored: list[str] = []
        mappings = [
            ("config", self.user_config_dir),
            ("skills", self.user_skills_dir),
            ("memory", self._memory_dir()),
        ]
        for name, target in mappings:
            source = payload_dir / name
            if not source.exists():
                continue
            self._remove_tree_preserving_excluded(target)
            self._copy_tree(source, target)
            restored.append(name)
        return restored

    def _remove_tree_preserving_excluded(self, target: Path) -> None:
        if not target.exists():
            return

        with tempfile.TemporaryDirectory() as temp_dir:
            preserved_root = Path(temp_dir)
            preserved: list[tuple[Path, Path]] = []
            for path in sorted(target.rglob("*")):
                rel = path.relative_to(target)
                if not any(_is_excluded_name(part) for part in rel.parts):
                    continue
                preserved_path = preserved_root / rel
                preserved_path.parent.mkdir(parents=True, exist_ok=True)
                if path.is_dir():
                    shutil.copytree(path, preserved_path, dirs_exist_ok=True)
                elif path.is_file():
                    shutil.copy2(path, preserved_path)
                preserved.append((rel, preserved_path))

            shutil.rmtree(target)
            for rel, preserved_path in preserved:
                dest = target / rel
                if preserved_path.is_dir():
                    shutil.copytree(preserved_path, dest, dirs_exist_ok=True)
                elif preserved_path.is_file():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(preserved_path, dest)

    def _copy_tree(self, source: Path, target: Path) -> None:
        if not source.exists():
            return
        if source.is_file():
            if _is_portable_file(source):
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            return
        for child in source.rglob("*"):
            rel = child.relative_to(source)
            if any(_is_excluded_name(part) for part in rel.parts):
                continue
            dest = target / rel
            if child.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            elif _is_portable_file(child):
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(child, dest)

    def _memory_dir(self) -> Path:
        return self.sandbox_data_path / "shared" / "memory"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_portable_file(path: Path) -> bool:
    return (
        not path.is_symlink()
        and not _is_excluded_name(path.name)
        and path.suffix.lower() not in EXCLUDED_SUFFIXES
    )


def _is_excluded_name(name: str) -> bool:
    return name in EXCLUDED_NAMES or name.startswith(".env")


def _device_name() -> str:
    import platform

    return platform.node() or "local-device"
