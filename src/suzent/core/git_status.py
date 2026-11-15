"""Multi-repository Git status inspection for a chat session."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from suzent.core.repository_context import (
    RepositoryContextRoots,
    find_repository_root,
    resolve_repository_context,
)
from suzent.logger import get_logger

logger = get_logger(__name__)

_SHORTSTAT_INSERTIONS_RE = re.compile(r"(\d+)\s+insertion")
_SHORTSTAT_DELETIONS_RE = re.compile(r"(\d+)\s+deletion")
_MAX_FILES_PER_REPO = 25


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _is_internal_suzent_path(path: Path, project_dir: Path) -> bool:
    """Return True if *path* is inside Suzent's internal `.suzent` or sandbox project dir."""
    resolved = path.resolve()
    if _is_within(resolved, project_dir):
        return True
    try:
        from suzent.config import CONFIG, get_data_dir

        data_dir = get_data_dir().resolve()
        sandbox_root = Path(CONFIG.sandbox_data_path).expanduser().resolve()
        if _is_within(resolved, data_dir) or _is_within(resolved, sandbox_root):
            return True
    except Exception:
        pass
    return any(part.lower() == ".suzent" for part in resolved.parts)


def discover_chat_git_repositories(
    chat_id: str | None,
    *,
    cwd: str | None = None,
    custom_volumes: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return unique Git repositories accessible to the chat, primary first.

    Only considers explicit session directories (``working_dir`` and mounted
    ``asset_directories``) and ignores Suzent's internal ``.suzent`` /
    ``project_dir`` sandbox directories (including ``scratch/``).
    """
    roots: RepositoryContextRoots = resolve_repository_context(
        chat_id,
        cwd=cwd,
        custom_volumes=custom_volumes,
    )
    project_dir = roots.project_dir.resolve()
    primary_working = roots.working_dir.resolve()

    candidates: list[tuple[Path, bool]] = []
    if not _is_internal_suzent_path(primary_working, project_dir):
        candidates.append((primary_working, True))
    for asset_dir in roots.asset_directories:
        resolved_asset = asset_dir.resolve()
        if not _is_internal_suzent_path(resolved_asset, project_dir):
            candidates.append((resolved_asset, resolved_asset == primary_working))

    seen_roots: dict[Path, dict[str, Any]] = {}
    for directory, is_primary in candidates:
        repo_root = find_repository_root(directory)
        if repo_root is None:
            continue
        repo_root = repo_root.resolve()
        if _is_internal_suzent_path(repo_root, project_dir):
            continue
        existing = seen_roots.get(repo_root)
        if existing is None:
            seen_roots[repo_root] = {
                "root": repo_root,
                "name": repo_root.name or str(repo_root),
                "primary": is_primary,
            }
        elif is_primary:
            existing["primary"] = True

    repos = list(seen_roots.values())
    repos.sort(key=lambda item: (not item["primary"], item["name"].lower()))
    return repos


def _run_git(repo_root: Path, args: list[str], timeout: float = 3.0) -> str | None:
    """Run a read-only git command without taking index locks."""
    cmd = ["git", "--no-optional-locks", "-C", str(repo_root), *args]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=creationflags,
        )
    except Exception as exc:
        logger.debug(f"git command failed in {repo_root}: {exc}")
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def _parse_shortstat(output: str | None) -> tuple[int, int]:
    if not output:
        return 0, 0
    ins_match = _SHORTSTAT_INSERTIONS_RE.search(output)
    del_match = _SHORTSTAT_DELETIONS_RE.search(output)
    additions = int(ins_match.group(1)) if ins_match else 0
    deletions = int(del_match.group(1)) if del_match else 0
    return additions, deletions


def inspect_git_repository(
    repo_root: Path,
    *,
    primary: bool = False,
    name: str | None = None,
) -> dict[str, Any] | None:
    """Inspect a single Git repository's branch, ahead/behind, and working tree."""
    status_out = _run_git(
        repo_root,
        ["status", "--porcelain=v2", "--branch", "-unormal"],
    )
    if status_out is None:
        return None

    branch = "HEAD"
    commit = ""
    detached = False
    ahead = 0
    behind = 0
    staged = 0
    modified = 0
    untracked = 0
    conflicted = 0
    files: list[dict[str, str]] = []

    for raw_line in status_out.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# branch.oid "):
            oid = line[len("# branch.oid ") :].strip()
            if oid and oid != "(initial)":
                commit = oid[:7]
        elif line.startswith("# branch.head "):
            head = line[len("# branch.head ") :].strip()
            if head == "(detached)":
                detached = True
                branch = commit or "detached"
            else:
                branch = head
        elif line.startswith("# branch.ab "):
            parts = line[len("# branch.ab ") :].split()
            for part in parts:
                if part.startswith("+"):
                    try:
                        ahead = int(part[1:])
                    except ValueError:
                        pass
                elif part.startswith("-"):
                    try:
                        behind = abs(int(part))
                    except ValueError:
                        pass
        elif line.startswith(("1 ", "2 ")):
            # 1 <XY> <sub> <mH> <mI> <mW> <hH> <hI> <path>
            # 2 <XY> <sub> <mH> <mI> <mW> <hH> <hI> <X><score> <path>\t<origPath>
            fields = line.split(" ", 8 if line.startswith("1 ") else 9)
            xy = fields[1] if len(fields) > 1 else ".."
            raw_path = fields[-1]
            path = raw_path.split("\t", 1)[0]
            index_status = xy[0] if len(xy) > 0 else "."
            worktree_status = xy[1] if len(xy) > 1 else "."
            if index_status != ".":
                staged += 1
            if worktree_status != ".":
                modified += 1
            if len(files) < _MAX_FILES_PER_REPO:
                status_code = index_status if index_status != "." else worktree_status
                files.append({"path": path, "status": status_code})
        elif line.startswith("u "):
            conflicted += 1
            fields = line.split(" ", 10)
            path = fields[-1]
            if len(files) < _MAX_FILES_PER_REPO:
                files.append({"path": path, "status": "U"})
        elif line.startswith("? "):
            untracked += 1
            path = line[2:]
            if len(files) < _MAX_FILES_PER_REPO:
                files.append({"path": path, "status": "?"})

    if detached and commit:
        branch = f"detached@{commit}"

    additions = 0
    deletions = 0
    if staged or modified:
        shortstat = _run_git(repo_root, ["diff", "--shortstat", "HEAD"])
        if shortstat is None:
            # Initial commit (no HEAD yet): sum cached + unstaged diff stats.
            a1, d1 = _parse_shortstat(
                _run_git(repo_root, ["diff", "--shortstat", "--cached"])
            )
            a2, d2 = _parse_shortstat(_run_git(repo_root, ["diff", "--shortstat"]))
            additions, deletions = a1 + a2, d1 + d2
        else:
            additions, deletions = _parse_shortstat(shortstat)

    clean = staged == 0 and modified == 0 and untracked == 0 and conflicted == 0
    total_changed = staged + modified + untracked + conflicted

    return {
        "name": name or repo_root.name or str(repo_root),
        "path": str(repo_root),
        "primary": primary,
        "branch": branch,
        "commit": commit,
        "detached": detached,
        "ahead": ahead,
        "behind": behind,
        "staged": staged,
        "modified": modified,
        "untracked": untracked,
        "conflicted": conflicted,
        "additions": additions,
        "deletions": deletions,
        "clean": clean,
        "total_changed": total_changed,
        "files": files,
    }


def get_chat_git_status(
    chat_id: str | None,
    *,
    cwd: str | None = None,
    custom_volumes: list[str] | None = None,
) -> dict[str, Any]:
    """Return multi-repository Git status for a chat session."""
    discovered = discover_chat_git_repositories(
        chat_id,
        cwd=cwd,
        custom_volumes=custom_volumes,
    )
    repositories: list[dict[str, Any]] = []
    for item in discovered:
        inspected = inspect_git_repository(
            item["root"],
            primary=bool(item["primary"]),
            name=str(item["name"]),
        )
        if inspected is not None:
            repositories.append(inspected)

    return {"repositories": repositories}
