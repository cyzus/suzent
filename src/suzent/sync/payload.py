from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from suzent.config import CONFIG, get_data_dir
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
    # Node-mesh device/auth state is inherently machine-local and must NOT sync:
    #  - node_host_devices.json holds inbound device auth tokens (secrets).
    #  - node_devices.json / node_peers.json are this device's pairing graph
    #    (who it approved / who it reaches) — syncing would overwrite another
    #    machine's mesh state on pull.
    #  - permission-audit.jsonl is this device's local decision log.
    "node_devices.json",
    "node_host_devices.json",
    "node_peers.json",
    "permission-audit.jsonl",
}
EXCLUDED_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


class SyncPayloadBuilder:
    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        user_config_dir: Path | None = None,
        user_skills_dir: Path | None = None,
        sandbox_data_path: Path | None = None,
    ) -> None:
        # Resolve dirs at construction (honors SUZENT_DATA_DIR) rather than from
        # module-frozen constants, so test isolation actually takes effect.
        base = get_data_dir()
        self.data_dir = data_dir or base
        self.user_config_dir = user_config_dir or base / "config"
        self.user_skills_dir = user_skills_dir or base / "skills" / "user"
        self.sandbox_data_path = sandbox_data_path or Path(CONFIG.sandbox_data_path)

    def build(self, repo_path: Path, profile: SyncProfile) -> SyncManifest:
        payload_dir = repo_path / PAYLOAD_DIR_NAME
        with tempfile.TemporaryDirectory() as temp_dir:
            preserved_memory = Path(temp_dir) / "memory"
            existing_memory = payload_dir / "memory"
            if existing_memory.exists():
                self._copy_tree(existing_memory, preserved_memory)
            if payload_dir.exists():
                shutil.rmtree(payload_dir)
            payload_dir.mkdir(parents=True, exist_ok=True)

            self._copy_tree(self.user_config_dir, payload_dir / "config")
            self._copy_tree(self.user_skills_dir, payload_dir / "skills")
            # Conversation memory is append-heavy and may be partially missing on a
            # device after recovery. Preserve the repo's existing memory files, then
            # overlay this device's local updates, so a partial local tree does not
            # become an authoritative mass deletion on push.
            self._copy_tree(preserved_memory, payload_dir / "memory")
            self._copy_tree(self._memory_dir(), payload_dir / "memory")
            presence = DevicePresence(
                device_id=profile.device_id,
                device_name=_device_name(),
                status="online",
                last_sync_revision=profile.last_revision,
            )
            presence_path = payload_dir / PRESENCE_DIR / f"{profile.device_id}.json"
            presence_path.parent.mkdir(parents=True, exist_ok=True)
            presence_path.write_text(
                presence.model_dump_json(indent=2), encoding="utf-8"
            )

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
            rel = path.relative_to(payload_dir)
            if any(_is_excluded_name(part) for part in rel.parts):
                forbidden.append(rel.as_posix())
            elif path.is_file() and path.suffix.lower() in EXCLUDED_SUFFIXES:
                forbidden.append(rel.as_posix())
        return sorted(set(forbidden))

    def apply_to_local(
        self, payload_dir: Path, *, replace_memory: bool = False
    ) -> list[str]:
        restored: list[str] = []
        replace_mappings = [
            ("config", self.user_config_dir),
            ("skills", self.user_skills_dir),
        ]
        for name, target in replace_mappings:
            source = payload_dir / name
            if not source.exists():
                continue
            self._remove_tree_preserving_excluded(target)
            self._copy_tree(source, target)
            restored.append(name)

        memory_source = payload_dir / "memory"
        if memory_source.exists():
            if replace_memory:
                self._remove_tree_preserving_excluded(self._memory_dir())
            self._copy_tree(memory_source, self._memory_dir())
            restored.append("memory")
        return restored

    def apply_paths_to_local(self, payload_dir: Path, paths: list[str]) -> list[str]:
        restored: list[str] = []
        for raw_path in paths:
            rel = Path(raw_path.replace("\\", "/"))
            if rel.is_absolute() or ".." in rel.parts or len(rel.parts) < 2:
                continue

            top = rel.parts[0]
            if top == "config":
                target = self.user_config_dir.joinpath(*rel.parts[1:])
            elif top == "skills":
                target = self.user_skills_dir.joinpath(*rel.parts[1:])
            elif top == "memory":
                target = self._memory_dir().joinpath(*rel.parts[1:])
            else:
                continue

            source = payload_dir / rel
            if source.is_file():
                self._copy_tree(source, target)
            elif target.exists() and not any(
                _is_excluded_name(part) for part in rel.parts
            ):
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            restored.append(rel.as_posix())
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
