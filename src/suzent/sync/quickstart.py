from __future__ import annotations

import re
import subprocess
from pathlib import Path

from suzent.config import DATA_DIR
from suzent.logger import get_logger
from suzent.sync.github_api import (
    GitHubApiError,
    create_private_repo,
    get_authenticated_user,
    parse_owner_repo,
    public_clone_url,
    repo_exists,
    resolve_github_token,
)
from suzent.sync.github_device_flow import GITHUB_APP_INSTALL_URL
from suzent.sync.github_token import (
    _redact_git_credentials,
    authed_clone_url,
    git_push_with_token,
)
from suzent.sync.models import SyncProfile
from suzent.sync.provider import GitHubSyncProvider

logger = get_logger(__name__)

DEFAULT_REPO_DIR = DATA_DIR / "github-sync"
DEFAULT_REPO_NAME = "suzent-brain"
DEFAULT_BRANCH = "main"
DEFAULT_REMOTE = "origin"
REPO_NAME_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9._-]*[a-zA-Z0-9])?$")


def default_repo_path() -> Path:
    return DEFAULT_REPO_DIR.resolve()


def _is_ephemeral_repo_path(path: Path) -> bool:
    parts = path.parts
    if not any(part.lower().startswith("pytest-of") for part in parts):
        return False
    if parts[-1].lower() != "github-sync":
        return False
    return any(part.startswith("test_") for part in parts)


def _resolve_quickstart_target(repo_path: Path | None) -> Path:
    if repo_path is None:
        return default_repo_path()
    resolved = repo_path.expanduser().resolve()
    if _is_ephemeral_repo_path(resolved):
        return default_repo_path()
    return resolved


def _remote_exists(path: Path, name: str = DEFAULT_REMOTE) -> bool:
    try:
        _git_in(path, "remote", "get-url", name)
        return True
    except RuntimeError:
        return False


def normalize_repo_name(name: str) -> str:
    cleaned = name.strip().lower() or DEFAULT_REPO_NAME
    if not REPO_NAME_RE.fullmatch(cleaned):
        raise ValueError(
            "Repository name may only contain letters, numbers, dots, hyphens, "
            "and underscores."
        )
    return cleaned


def normalize_github_remote(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    if raw.startswith("git@"):
        return raw
    if raw.startswith("http://") or raw.startswith("https://"):
        cleaned = raw.rstrip("/")
        return cleaned if cleaned.endswith(".git") else f"{cleaned}.git"
    if re.fullmatch(r"[\w.-]+/[\w.-]+", raw):
        return f"https://github.com/{raw}.git"
    raise ValueError(
        "GitHub repo must be owner/name, a github.com URL, or a git@github.com URL"
    )


def quickstart_github_sync(
    *,
    repo_name: str = DEFAULT_REPO_NAME,
    repo_path: Path | None = None,
    branch: str | None = None,
    remote: str = DEFAULT_REMOTE,
    auto_sync_enabled: bool = True,
    auto_resolve_enabled: bool = True,
    interval_hours: int = 4,
) -> dict:
    actions: list[str] = []
    warnings: list[str] = []
    install_required: bool = False
    owner_override, repo_slug = parse_owner_repo(repo_name)
    slug = normalize_repo_name(repo_slug)
    target = _resolve_quickstart_target(repo_path)
    if repo_path and _is_ephemeral_repo_path(repo_path.expanduser().resolve()):
        actions.append(f"Ignored test/temp repo path; using {target}")
    branch_name = branch or DEFAULT_BRANCH
    username: str | None = owner_override

    token = resolve_github_token()
    if not token:
        raise ValueError(
            "Sign in with GitHub first (Settings → Data → GitHub Sync → Sign in)"
        )
    username = username or get_authenticated_user(token)
    remote_url = public_clone_url(username, slug)
    actions.append(f"Signed in to GitHub as {username}")

    if not (target / ".git").exists():
        if remote_url and _remote_repo_exists(token, username, slug):
            _clone_existing_repo(target, remote_url, remote, token, actions)
        else:
            target.mkdir(parents=True, exist_ok=True)
            _init_repo(target)
            actions.append(f"Initialized Git repository at {target}")
            readme = target / "README.md"
            if not readme.exists():
                readme.write_text(
                    "# Suzent sync\n\nPortable Suzent brain data is stored under `suzent-sync/`.\n",
                    encoding="utf-8",
                )
                _git_in(target, "add", "README.md")
                _git_in(
                    target, "commit", "-m", "chore: initialize suzent sync repository"
                )
                actions.append("Created initial commit")
    else:
        actions.append(f"Using existing repository at {target}")

    if remote_url and username:
        _ensure_remote(target, remote, remote_url, actions)
        created, install_required = _create_github_repo_api(
            target, token, username, slug, branch_name, warnings
        )
        if created:
            actions.append(created)

    detected_branch = _detect_branch(target)
    if detected_branch:
        branch_name = detected_branch

    profile = _save_default_profile(
        target,
        branch_name,
        remote=remote,
        auto_sync_enabled=auto_sync_enabled,
        auto_resolve_enabled=auto_resolve_enabled,
        interval_hours=interval_hours,
    )

    git_status: dict | None = None
    try:
        git_status = GitHubSyncProvider(
            target, remote=remote, branch=branch_name
        ).validate(require_clean=False)
    except Exception as exc:
        warnings.append(str(exc))

    if git_status and git_status.get("valid"):
        actions.append("GitHub sync is ready")

    return {
        "success": True,
        "profile": profile.model_dump(mode="json"),
        "repo_path": str(target),
        "branch": branch_name,
        "remote": remote,
        "repo_name": slug,
        "github_username": username,
        "github_repo": f"{username}/{slug}" if username else None,
        "actions": actions,
        "warnings": warnings,
        "install_required": install_required,
        "install_url": GITHUB_APP_INSTALL_URL if install_required else None,
        "git": git_status,
    }


def _save_default_profile(
    repo_path: Path,
    branch: str,
    *,
    remote: str,
    auto_sync_enabled: bool,
    auto_resolve_enabled: bool,
    interval_hours: int,
) -> SyncProfile:
    from suzent.sync.service import GitHubSyncService

    service = GitHubSyncService()
    existing = service.list_profiles()
    if existing:
        profile = existing[0]
    else:
        profile = SyncProfile(repo_path=str(repo_path))
    profile.repo_path = str(repo_path)
    profile.branch = branch
    profile.remote = remote
    profile.auto_sync_enabled = auto_sync_enabled
    profile.auto_resolve_enabled = auto_resolve_enabled
    profile.interval_hours = max(1, interval_hours)
    return service.save_profile(profile)


def _create_github_repo_api(
    path: Path,
    token: str,
    username: str,
    repo_name: str,
    branch: str,
    warnings: list[str],
) -> tuple[str | None, bool]:
    full_name = f"{username}/{repo_name}"
    try:
        if repo_exists(token, username, repo_name):
            push_url = authed_clone_url(username, repo_name, token)
            try:
                git_push_with_token(path, token, push_url, branch)
            except RuntimeError as exc:
                warnings.append(str(exc))
            return f"Linked to existing GitHub repository {full_name}", False
        create_private_repo(
            token,
            repo_name,
            description="Suzent portable brain sync",
        )
        push_url = authed_clone_url(username, repo_name, token)
        git_push_with_token(path, token, push_url, branch)
        return (
            f"Created private GitHub repository {full_name} and pushed initial commit",
            False,
        )
    except GitHubApiError as exc:
        if "403" in str(exc):
            return None, True
        warnings.append(f"Could not create GitHub repository: {exc}")
        return None, False
    except RuntimeError as exc:
        warnings.append(f"Could not create GitHub repository: {exc}")
        return None, False


def _remote_repo_exists(token: str, username: str, repo_name: str) -> bool:
    try:
        return repo_exists(token, username, repo_name)
    except GitHubApiError:
        return False


def _clone_existing_repo(
    target: Path,
    remote_url: str,
    remote: str,
    token: str | None,
    actions: list[str],
) -> None:
    if target.exists() and any(target.iterdir()):
        raise ValueError(
            f"Sync repo path already exists and is not empty: {target}. "
            "Choose an empty folder or an existing Git repository."
        )

    clone_url = remote_url
    if token:
        owner_repo = remote_url.removeprefix("https://github.com/").removesuffix(".git")
        if "/" in owner_repo:
            owner, repo = owner_repo.split("/", 1)
            clone_url = authed_clone_url(owner, repo, token)
    target.parent.mkdir(parents=True, exist_ok=True)
    _run_git(None, "clone", "--origin", remote, clone_url, str(target))
    _git_in(target, "remote", "set-url", remote, remote_url)
    _ensure_local_git_identity(target)
    actions.append(f"Cloned existing GitHub repository into {target}")


def _init_repo(path: Path) -> str:
    try:
        _git_in(path, "init", "-b", DEFAULT_BRANCH)
    except RuntimeError:
        _git_in(path, "init")
        _git_in(path, "checkout", "-B", DEFAULT_BRANCH)
    _ensure_local_git_identity(path)
    return DEFAULT_BRANCH


def _ensure_local_git_identity(path: Path) -> None:
    if not _git_config(path, "user.email"):
        _git_in(path, "config", "user.email", "suzent@local")
    if not _git_config(path, "user.name"):
        _git_in(path, "config", "user.name", "Suzent")


def _git_config(path: Path, key: str) -> str:
    completed = subprocess.run(
        ["git", "config", key],
        cwd=path,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _detect_branch(path: Path) -> str:
    try:
        branch = _git_in(path, "branch", "--show-current").strip()
        return branch or DEFAULT_BRANCH
    except RuntimeError:
        return DEFAULT_BRANCH


def _ensure_remote(
    path: Path, remote: str, remote_url: str, actions: list[str]
) -> None:
    try:
        current = _git_in(path, "remote", "get-url", remote).strip()
        if current != remote_url:
            _git_in(path, "remote", "set-url", remote, remote_url)
            actions.append(f"Updated remote {remote}")
        return
    except RuntimeError:
        pass
    _git_in(path, "remote", "add", remote, remote_url)
    actions.append(f"Added GitHub remote {remote}")


def _git_in(path: Path, *args: str) -> str:
    return _run_git(path, *args)


def _run_git(cwd: Path | None, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = _redact_git_credentials(
            completed.stderr.strip() or completed.stdout.strip()
        )
        command = " ".join(_redact_git_credentials(arg) for arg in args)
        raise RuntimeError(f"git {command} failed: {detail}")
    return completed.stdout
