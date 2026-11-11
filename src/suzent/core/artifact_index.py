"""Index what the agent delivered, across every project.

Two sources: each project library's ``artifacts/`` folder, and files the agent
handed over with ``send_file`` or made with a media tool, read from chat
transcripts. Transcripts also tell which chat produced a library file.
"""

import json
from pathlib import Path
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel

from suzent.config import CONFIG
from suzent.core.library_index import ARTIFACTS_DIRNAME
from suzent.logger import get_logger

logger = get_logger(__name__)

type ArtifactKind = Literal["image", "video", "audio", "file"]

OUTPUT_TOOLS = {"generate_image", "edit_image", "check_video", "speak", "send_file"}
MAX_FILES_PER_PROJECT = 2000

_KINDS: dict[str, ArtifactKind] = {
    **dict.fromkeys(("png", "jpg", "jpeg", "gif", "webp", "svg"), "image"),
    **dict.fromkeys(("mp4", "mov", "webm", "m4v"), "video"),
    **dict.fromkeys(("mp3", "wav", "ogg", "m4a", "aac", "flac", "opus"), "audio"),
}


class ArtifactProject(BaseModel):
    id: str
    name: str
    count: int


class ArtifactEntry(BaseModel):
    path: str
    """Where the file lives on this computer."""
    name: str
    kind: ArtifactKind
    project_id: str
    chat_id: str | None
    """The chat that produced it, when a transcript says so."""
    chat_title: str | None
    serve_chat_id: str | None
    """A chat whose file access reaches the file, for previews."""
    modified: float
    size: int


class ArtifactIndex(BaseModel):
    projects: list[ArtifactProject]
    items: list[ArtifactEntry]


def artifact_kind(path: str) -> ArtifactKind:
    return _KINDS.get(Path(path).suffix.lower().lstrip("."), "file")


def _tool_paths(part: dict[str, Any]) -> list[str]:
    if part.get("type") != "tool" or part.get("toolName") not in OUTPUT_TOOLS:
        return []
    if part.get("state") == "error" or part.get("outcome"):
        return []
    try:
        result = json.loads(part.get("output") or "")
    except (TypeError, ValueError):
        return []
    if not isinstance(result, dict):
        return []
    # A send_file a chat app refused still names files that exist here.
    if result.get("success") is False and part.get("toolName") != "send_file":
        return []
    paths = (result.get("metadata") or {}).get("saved_paths")
    return (
        [p for p in paths if isinstance(p, str) and p]
        if isinstance(paths, list)
        else []
    )


def transcript_outputs(messages: list[Any]) -> list[str]:
    """Paths of files a chat's tools delivered, oldest first."""
    found: list[str] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        for part in message.get("parts") or []:
            if isinstance(part, dict):
                found.extend(_tool_paths(part))
        if message.get("file_changes_undone"):
            continue
        for change in message.get("file_changes") or []:
            if isinstance(change, dict) and change.get("after_exists") is not False:
                path = change.get("path")
                if isinstance(path, str) and f"/{ARTIFACTS_DIRNAME}/" in path.replace(
                    "\\", "/"
                ):
                    found.append(path)
    return found


def _to_host(
    path: str, project_dir: Path, resolve: Callable[[str], Path]
) -> Path | None:
    normalized = path.replace("\\", "/")
    if normalized.startswith("/workspace/"):
        candidate = project_dir / normalized.removeprefix("/workspace/")
    else:
        candidate = Path(path)
        if not candidate.is_absolute() or not candidate.exists():
            try:
                candidate = resolve(path)
            except Exception:
                return None
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    return resolved if resolved.is_file() else None


def _lazy_resolver(chat_id: str) -> Callable[[str], Path]:
    """Build the chat's file resolver only if a path needs it."""
    built: list[Any] = []

    def resolve(path: str) -> Path:
        if not built:
            from suzent.routes.sandbox_routes import _get_resolver_for_request

            built.append(_get_resolver_for_request(chat_id))
        return built[0].resolve(path)

    return resolve


def _library_files(project_dir: Path) -> list[Path]:
    root = project_dir / ARTIFACTS_DIRNAME
    if not root.is_dir():
        return []
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            files.append(path.resolve())
            if len(files) >= MAX_FILES_PER_PROJECT:
                logger.warning("Artifact index stopped at {} files", len(files))
                break
    return files


def build_artifact_index() -> ArtifactIndex:
    """Every project's deliverables, newest first."""
    from suzent.database import get_database

    db = get_database()
    projects = db.list_projects()
    project_dirs = {
        project.id: Path(CONFIG.sandbox_data_path) / "projects" / project.slug
        for project in projects
    }
    transcripts = db.list_chat_transcripts(list(project_dirs))

    origin: dict[Path, tuple[str, str]] = {}
    serve_chat: dict[str, str] = {}
    delivered: dict[Path, str] = {}
    for chat_id, title, project_id, messages in transcripts:
        serve_chat.setdefault(project_id, chat_id)
        outputs = transcript_outputs(messages)
        if not outputs:
            continue
        resolver = _lazy_resolver(chat_id)
        for raw in outputs:
            host = _to_host(raw, project_dirs[project_id], resolver)
            if host is None:
                continue
            origin[host] = (chat_id, title)
            delivered.setdefault(host, project_id)

    entries: dict[Path, ArtifactEntry] = {}

    def add(path: Path, project_id: str) -> None:
        if path in entries:
            return
        stat = path.stat()
        chat_id, title = origin.get(path, (None, None))
        entries[path] = ArtifactEntry(
            path=str(path),
            name=path.name,
            kind=artifact_kind(path.name),
            project_id=project_id,
            chat_id=chat_id,
            chat_title=title,
            serve_chat_id=chat_id or serve_chat.get(project_id),
            modified=stat.st_mtime,
            size=stat.st_size,
        )

    for project_id, project_dir in project_dirs.items():
        for path in _library_files(project_dir):
            add(path, project_id)
    for path, project_id in delivered.items():
        add(path, project_id)

    items = sorted(entries.values(), key=lambda entry: entry.modified, reverse=True)
    counts: dict[str, int] = {}
    for item in items:
        counts[item.project_id] = counts.get(item.project_id, 0) + 1
    return ArtifactIndex(
        projects=[
            ArtifactProject(id=p.id, name=p.name, count=counts.get(p.id, 0))
            for p in projects
        ],
        items=items,
    )
