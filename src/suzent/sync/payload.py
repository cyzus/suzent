from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path

from suzent.config import CONFIG, get_data_dir

PAYLOAD_DIR_NAME = "suzent-sync"
PORTABLE_CONFIG_FILES = frozenset({"config.yaml", "default.yaml", "skills.json"})

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

    def build(self, repo_path: Path) -> None:
        payload_dir = repo_path / PAYLOAD_DIR_NAME
        with tempfile.TemporaryDirectory() as temp_dir:
            preserved_memory = Path(temp_dir) / "memory"
            existing_memory = payload_dir / "memory"
            if existing_memory.exists():
                self._copy_tree(existing_memory, preserved_memory)
            if payload_dir.exists():
                shutil.rmtree(payload_dir)
            payload_dir.mkdir(parents=True, exist_ok=True)

            self._copy_portable_config(self.user_config_dir, payload_dir / "config")
            self._copy_tree(self.user_skills_dir, payload_dir / "skills")
            # Conversation memory is append-heavy and may be partially missing on a
            # device after recovery. Preserve the repo's existing memory files, then
            # overlay this device's local updates, so a partial local tree does not
            # become an authoritative mass deletion on push.
            self._copy_tree(preserved_memory, payload_dir / "memory", suffixes={".md"})
            self._copy_tree(
                self._memory_dir(), payload_dir / "memory", suffixes={".md"}
            )

    def content_hashes(self, payload_dir: Path) -> dict[str, str]:
        hashes: dict[str, str] = {}
        if not payload_dir.exists():
            return hashes
        for path in sorted(p for p in payload_dir.rglob("*") if p.is_file()):
            rel = path.relative_to(payload_dir).as_posix()
            if path.is_symlink() or not _is_allowed_payload_path(Path(rel)):
                continue
            hashes[rel] = _sha256(path)
        return hashes

    def preview_content_hashes(self, payload_dir: Path) -> dict[str, str]:
        hashes: dict[str, str] = {}
        self._overlay_config_hashes(hashes)
        self._overlay_tree_hashes(self.user_skills_dir, "skills", hashes)
        self._overlay_tree_hashes(
            payload_dir / "memory", "memory", hashes, suffixes={".md"}
        )
        self._overlay_tree_hashes(
            self._memory_dir(), "memory", hashes, suffixes={".md"}
        )
        return hashes

    def validate_no_forbidden_paths(self, payload_dir: Path) -> list[str]:
        forbidden: list[str] = []
        if not payload_dir.exists():
            return forbidden
        for path in payload_dir.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(payload_dir)
            if path.is_symlink() or not _is_allowed_payload_path(rel):
                forbidden.append(rel.as_posix())
        return sorted(set(forbidden))

    def apply_to_local(
        self, payload_dir: Path, *, replace_memory: bool = False
    ) -> list[str]:
        restored: list[str] = []
        config_source = payload_dir / "config"
        if config_source.exists():
            self._replace_portable_config(config_source, self.user_config_dir)
            restored.append("config")

        skills_source = payload_dir / "skills"
        if skills_source.exists():
            self._remove_tree_preserving_excluded(self.user_skills_dir)
            self._copy_tree(skills_source, self.user_skills_dir)
            restored.append("skills")

        memory_source = payload_dir / "memory"
        if memory_source.exists():
            if replace_memory:
                self._remove_markdown_files(self._memory_dir())
            self._copy_tree(memory_source, self._memory_dir(), suffixes={".md"})
            restored.append("memory")
        return restored

    def apply_paths_to_local(self, payload_dir: Path, paths: list[str]) -> list[str]:
        restored: list[str] = []
        for raw_path in paths:
            resolved = self.resolve_local_path(raw_path)
            if resolved is None:
                continue
            rel, target = resolved

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

    def resolve_local_path(self, payload_path: str) -> tuple[Path, Path] | None:
        rel = Path(payload_path.replace("\\", "/"))
        if (
            rel.is_absolute()
            or ".." in rel.parts
            or len(rel.parts) < 2
            or any(_is_excluded_name(part) for part in rel.parts)
            or rel.suffix.lower() in EXCLUDED_SUFFIXES
        ):
            return None

        top = rel.parts[0]
        if top == "config":
            if len(rel.parts) != 2 or rel.parts[1] not in PORTABLE_CONFIG_FILES:
                return None
            target = self.user_config_dir.joinpath(*rel.parts[1:])
        elif top == "skills":
            target = self.user_skills_dir.joinpath(*rel.parts[1:])
        elif top == "memory":
            if rel.suffix.lower() != ".md":
                return None
            target = self._memory_dir().joinpath(*rel.parts[1:])
        else:
            return None
        return rel, target

    def has_outgoing_change(self, payload_dir: Path, payload_path: str) -> bool:
        resolved = self.resolve_local_path(payload_path)
        if resolved is None:
            return False
        rel, local_path = resolved
        payload_file = payload_dir / rel
        before = payload_file.read_bytes() if payload_file.is_file() else None
        after = local_path.read_bytes() if local_path.is_file() else None
        if rel.parts[0] == "memory" and after is None:
            after = before
        return before != after

    def _overlay_tree_hashes(
        self,
        source: Path,
        prefix: str,
        hashes: dict[str, str],
        *,
        suffixes: set[str] | None = None,
    ) -> None:
        if not source.exists():
            return
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            rel = path.relative_to(source)
            if any(_is_excluded_name(part) for part in rel.parts):
                continue
            if not _is_portable_file(path):
                continue
            if suffixes is not None and path.suffix.lower() not in suffixes:
                continue
            hashes[(Path(prefix) / rel).as_posix()] = _sha256(path)

    def _overlay_config_hashes(self, hashes: dict[str, str]) -> None:
        for name in sorted(PORTABLE_CONFIG_FILES):
            path = self.user_config_dir / name
            if path.is_file() and _is_portable_file(path):
                hashes[(Path("config") / name).as_posix()] = _sha256(path)

    def _copy_portable_config(self, source: Path, target: Path) -> None:
        for name in sorted(PORTABLE_CONFIG_FILES):
            self._copy_tree(source / name, target / name)

    def _replace_portable_config(self, source: Path, target: Path) -> None:
        for name in sorted(PORTABLE_CONFIG_FILES):
            source_path = source / name
            target_path = target / name
            if source_path.is_file():
                self._copy_tree(source_path, target_path)
            elif target_path.exists():
                target_path.unlink()

    def _remove_markdown_files(self, target: Path) -> None:
        if not target.exists():
            return
        for path in sorted(target.rglob("*.md")):
            if path.is_file() and not any(
                _is_excluded_name(part) for part in path.relative_to(target).parts
            ):
                path.unlink()

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

    def _copy_tree(
        self,
        source: Path,
        target: Path,
        *,
        suffixes: set[str] | None = None,
    ) -> None:
        if not source.exists():
            return
        if source.is_file():
            if _is_portable_file(source) and (
                suffixes is None or source.suffix.lower() in suffixes
            ):
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
            elif _is_portable_file(child) and (
                suffixes is None or child.suffix.lower() in suffixes
            ):
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


def _is_allowed_payload_path(rel: Path) -> bool:
    if len(rel.parts) < 2 or any(_is_excluded_name(part) for part in rel.parts):
        return False
    top = rel.parts[0]
    if top == "config":
        return len(rel.parts) == 2 and rel.parts[1] in PORTABLE_CONFIG_FILES
    if top == "skills":
        return rel.suffix.lower() not in EXCLUDED_SUFFIXES
    if top == "memory":
        return rel.suffix.lower() == ".md"
    return False
