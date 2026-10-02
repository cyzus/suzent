"""Keep a project's ``context.md`` file index in step with its deliverables.

Tools that save output into ``artifacts/`` register each file here, so later
chats find it through the index instead of listing folders.
"""

import threading
from pathlib import Path

from suzent.config import CONFIG
from suzent.core.agent_deps import AgentDeps
from suzent.logger import get_logger

logger = get_logger(__name__)

ARTIFACTS_DIRNAME = "artifacts"
CONTEXT_FILENAME = "context.md"
FILE_INDEX_HEADING = "## File index"

_lock = threading.Lock()


def project_root(deps: AgentDeps) -> Path:
    if deps.chat_id:
        from suzent.database import get_database

        return get_database().get_project_dir(deps.chat_id)
    return Path(CONFIG.workspace_root)


def artifacts_dir(deps: AgentDeps, kind: str) -> Path:
    """Return ``artifacts/<kind>`` in the chat's project, creating it."""
    directory = project_root(deps) / ARTIFACTS_DIRNAME / kind
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def add_to_file_index(project_dir: Path, entries: list[tuple[Path, str]]) -> int:
    """Add ``(path, description)`` lines under the file index of ``context.md``.

    Paths are written relative to the project and skipped when already listed.
    Returns the number of lines added.
    """
    context = project_dir / CONTEXT_FILENAME
    with _lock:
        text = context.read_text(encoding="utf-8") if context.exists() else ""
        lines = []
        for path, description in entries:
            try:
                relative = path.relative_to(project_dir).as_posix()
            except ValueError:
                relative = path.as_posix()
            if relative in text or any(relative in line for line in lines):
                continue
            lines.append(f"- `{relative}`: {description}")
        if not lines:
            return 0
        block = "\n".join(lines)
        if FILE_INDEX_HEADING not in text:
            text = text.rstrip("\n") + ("\n\n" if text.strip() else "")
            text += f"{FILE_INDEX_HEADING}\n\n{block}\n"
        else:
            start = text.index(FILE_INDEX_HEADING) + len(FILE_INDEX_HEADING)
            next_heading = text.find("\n## ", start)
            end = len(text) if next_heading == -1 else next_heading
            section = text[start:end].rstrip("\n")
            tail = text[end:].lstrip("\n")
            text = f"{text[:start]}{section}\n{block}\n" + (f"\n{tail}" if tail else "")
        context.write_text(text, encoding="utf-8")
    return len(lines)


def register_artifacts(deps: AgentDeps, paths: list[str], description: str) -> None:
    """Index saved tool output, logging instead of failing the tool."""
    try:
        add_to_file_index(
            project_root(deps), [(Path(path), description) for path in paths]
        )
    except Exception as exc:
        logger.warning("Could not index artifacts {}: {}", paths, exc)


def unindexed_artifacts(project_dir: Path, limit: int = 10) -> list[Path]:
    """Return up to ``limit`` files in ``artifacts/`` missing from ``context.md``."""
    root = project_dir / ARTIFACTS_DIRNAME
    if not root.is_dir():
        return []
    context = project_dir / CONTEXT_FILENAME
    text = context.read_text(encoding="utf-8") if context.exists() else ""
    missing = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith(".") or path.suffix == ".json":
            continue
        if path.relative_to(project_dir).as_posix() not in text:
            missing.append(path)
            if len(missing) >= limit:
                break
    return missing
