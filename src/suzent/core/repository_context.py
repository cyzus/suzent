"""Resolve project/repository context roots and discover local agent assets."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path


ASSISTANT_ROOTS = (".claude", ".agents", ".codex", ".grok")
INSTRUCTION_FILENAMES = ("CLAUDE.md", "AGENTS.md")


@dataclass(frozen=True)
class RepositoryContextRoots:
    """Filesystem roots that contribute context to one chat run."""

    project_dir: Path
    working_dir: Path
    repository_root: Path | None
    home_dir: Path | None = field(default_factory=Path.home)
    asset_directories: tuple[Path, ...] = ()

    def unique_asset_bases(self) -> tuple[tuple[str, Path], ...]:
        """Return working-tree bases in increasing precedence order.

        ``project_dir`` is Suzent's durable per-project storage and is reserved
        for core memory such as ``context.md``. Agent assets come from the
        effective working directory and its repository root.
        """
        candidates: list[tuple[str, Path]] = []
        if self.home_dir is not None:
            candidates.append(("home", self.home_dir))
        asset_directories = self.asset_directories
        if not asset_directories and (
            self.repository_root is not None or self.working_dir != self.project_dir
        ):
            asset_directories = (self.working_dir,)
        for working_dir in asset_directories:
            repository_root = (
                self.repository_root
                if working_dir == self.working_dir and self.repository_root is not None
                else find_repository_root(working_dir)
            )
            if repository_root is not None:
                candidates.append(("repository", repository_root))
                if working_dir != repository_root:
                    candidates.append(("working", working_dir))
            else:
                candidates.append(("working", working_dir))

        result: list[tuple[str, Path]] = []
        seen: set[Path] = set()
        for scope, path in candidates:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            result.append((scope, resolved))
        return tuple(result)


@dataclass(frozen=True)
class DiscoveredSkillRoot:
    """One directory whose immediate children are AgentSkills."""

    path: Path
    source: str
    source_id: str
    virtual_root: str | None
    default_enabled: bool = True


@dataclass(frozen=True)
class DiscoveredAgentFile:
    """One declarative sub-agent definition found in repository context."""

    path: Path
    source: str
    source_id: str


@dataclass(frozen=True)
class DiscoveredInstructionFile:
    """One instruction file loaded by RepoContext's walk-up strategy."""

    path: Path
    source: str


def find_repository_root(start: Path) -> Path | None:
    """Find the nearest Git repository containing *start*."""
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def resolve_repository_context(
    chat_id: str | None,
    cwd: str | None = None,
    *,
    custom_volumes: list[str] | None = None,
) -> RepositoryContextRoots:
    """Resolve Suzent's project directory and the chat's effective working tree."""
    from suzent.database import get_database

    database = get_database()
    process_cwd = Path.cwd().resolve()
    project_dir = (
        database.get_project_dir(chat_id).resolve() if chat_id else process_cwd
    )
    chat = database.get_chat(chat_id) if chat_id else None
    configured_cwd = cwd or (chat.working_directory if chat else None)
    if not configured_cwd and chat:
        configured_cwd = (chat.config or {}).get("cwd")

    from suzent.config import get_effective_volumes
    from suzent.tools.filesystem.path_resolver import PathResolver

    configured_volumes = custom_volumes
    if configured_volumes is None and chat:
        configured_volumes = list((chat.config or {}).get("sandbox_volumes") or [])
    effective_volumes = get_effective_volumes(configured_volumes or [])
    mounts: list[tuple[Path, str]] = []
    for volume in effective_volumes:
        parsed = PathResolver.parse_volume_string(volume)
        if parsed:
            host, virtual = parsed
            mounts.append((Path(host).expanduser().resolve(), virtual.rstrip("/")))

    def host_path_for(value: str) -> Path:
        normalized = value.replace("\\", "/")
        for host_root, virtual_root in sorted(
            mounts, key=lambda item: len(item[1]), reverse=True
        ):
            if normalized == virtual_root or normalized.startswith(f"{virtual_root}/"):
                suffix = normalized[len(virtual_root) :].lstrip("/")
                return (host_root / suffix).resolve()
        return Path(value).expanduser().resolve()

    ignored_mounts = {"/mnt/notebook", "/mnt/skills", "/shared"}
    repository_mounts = tuple(
        host
        for host, virtual in mounts
        if virtual not in ignored_mounts and find_repository_root(host) is not None
    )
    if configured_cwd:
        working_dir = host_path_for(str(configured_cwd))
    elif repository_mounts:
        working_dir = repository_mounts[0]
    elif chat_id is None:
        working_dir = process_cwd
    else:
        working_dir = project_dir

    asset_directories = list(repository_mounts)
    if working_dir != project_dir and working_dir not in asset_directories:
        asset_directories.append(working_dir)
    return RepositoryContextRoots(
        project_dir=project_dir,
        working_dir=working_dir,
        repository_root=find_repository_root(working_dir),
        home_dir=Path.home().resolve(),
        asset_directories=tuple(asset_directories),
    )


def _source_id(scope: str, base: Path, assistant_root: str) -> str:
    digest = hashlib.sha1(str(base.resolve()).encode("utf-8")).hexdigest()[:10]
    return f"{scope}:{digest}:{assistant_root}"


def _virtual_root(skill_root: Path, project_dir: Path) -> str | None:
    try:
        relative = skill_root.resolve().relative_to(project_dir.resolve())
    except ValueError:
        return None
    suffix = relative.as_posix()
    return "/workspace" if suffix == "." else f"/workspace/{suffix}"


def _skill_library_roots(candidate: Path) -> list[Path]:
    """Return direct and one-level namespaced AgentSkill libraries."""
    libraries: list[Path] = []
    if any(
        child.is_dir() and (child / "SKILL.md").is_file()
        for child in candidate.iterdir()
    ):
        libraries.append(candidate)

    # Codex stores bundled skills under ``skills/.system/<skill>/SKILL.md``.
    # Supporting one namespace level also covers similar vendor/group layouts
    # without recursively mistaking resources inside a skill for more skills.
    for namespace in sorted(candidate.iterdir()):
        if not namespace.is_dir() or (namespace / "SKILL.md").is_file():
            continue
        if any(
            child.is_dir() and (child / "SKILL.md").is_file()
            for child in namespace.iterdir()
        ):
            libraries.append(namespace)
    return libraries


def discover_skill_roots(roots: RepositoryContextRoots) -> list[DiscoveredSkillRoot]:
    """Discover working-directory/repository AgentSkill containers."""
    discovered: list[DiscoveredSkillRoot] = []
    seen: set[Path] = set()
    for scope, base in roots.unique_asset_bases():
        candidates = [("skills", base / "skills")]
        candidates.extend((name, base / name / "skills") for name in ASSISTANT_ROOTS)
        for assistant_root, candidate in candidates:
            if not candidate.is_dir():
                continue
            for library in _skill_library_roots(candidate):
                resolved = library.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                relative_library = library.relative_to(candidate).as_posix()
                source_suffix = (
                    assistant_root
                    if relative_library == "."
                    else f"{assistant_root}/{relative_library}"
                )
                discovered.append(
                    DiscoveredSkillRoot(
                        path=resolved,
                        source=scope,
                        source_id=_source_id(scope, base, source_suffix),
                        virtual_root=_virtual_root(resolved, roots.project_dir),
                    )
                )
    return discovered


def discover_agent_files(roots: RepositoryContextRoots) -> list[DiscoveredAgentFile]:
    """Discover declarative agent markdown files without parsing their contents."""
    discovered: list[DiscoveredAgentFile] = []
    seen: set[Path] = set()
    for scope, base in roots.unique_asset_bases():
        for assistant_root in ASSISTANT_ROOTS:
            agent_dir = base / assistant_root / "agents"
            if not agent_dir.is_dir():
                continue
            for path in sorted(agent_dir.glob("*.md")):
                resolved = path.resolve()
                if resolved in seen or not resolved.is_file():
                    continue
                seen.add(resolved)
                discovered.append(
                    DiscoveredAgentFile(
                        path=resolved,
                        source=scope,
                        source_id=_source_id(scope, base, assistant_root),
                    )
                )
    return discovered


def discover_instruction_files(
    roots: RepositoryContextRoots,
) -> list[DiscoveredInstructionFile]:
    """Mirror RepoContext's ancestor-first instruction-file discovery."""
    workspace = roots.working_dir.resolve()
    repository_root = roots.repository_root.resolve() if roots.repository_root else None
    directories = [workspace]
    if repository_root is not None and (
        workspace == repository_root or repository_root in workspace.parents
    ):
        directories = []
        current = workspace
        while True:
            directories.append(current)
            if current == repository_root:
                break
            current = current.parent
        directories.reverse()

    discovered: list[DiscoveredInstructionFile] = []
    seen_paths: set[Path] = set()
    seen_content: set[str] = set()
    for directory in directories:
        source = "working" if directory == workspace else "repository"
        for filename in INSTRUCTION_FILENAMES:
            path = directory / filename
            if not path.is_file():
                continue
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            try:
                content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
            if content_hash in seen_content:
                continue
            seen_paths.add(resolved)
            seen_content.add(content_hash)
            discovered.append(DiscoveredInstructionFile(path=resolved, source=source))
    return discovered


def build_repo_context_capabilities(roots: RepositoryContextRoots) -> list[object]:
    """Create a RepoContext capability for working-tree instructions."""
    from pydantic_ai_harness import RepoContext

    working_dir = roots.working_dir.resolve()
    return [
        RepoContext(
            workspace_dir=working_dir,
            home_dir=roots.repository_root,
            filenames=INSTRUCTION_FILENAMES,
            expose_inventory_tool=False,
            nested_traversal=False,
        )
    ]


async def repository_agents_reminder_hook(chat_id: str, deps: object) -> str | None:
    """Surface discovered declarative agent definitions to the orchestrator."""
    del chat_id
    agent_files = getattr(deps, "repository_agent_files", None) or []
    if not agent_files:
        return None

    sandbox_enabled = bool(getattr(deps, "sandbox_enabled", True))
    lines: list[str] = []
    for agent_file in agent_files:
        path = agent_file.path.resolve()
        location = str(path)
        if sandbox_enabled:
            location = deps.path_resolver.to_virtual_path(path) or str(path)
        lines.append(f"- {path.stem} ({agent_file.source}): {location}")
    return (
        "Repository agent definitions are available. Read the matching definition "
        "before delegating work that fits it:\n" + "\n".join(lines)
    )
