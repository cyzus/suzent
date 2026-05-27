from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
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
    store_github_token,
)
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

_WINDOWS_GH_CANDIDATES = (
    Path(r"C:\Program Files\GitHub CLI\gh.exe"),
    Path(r"C:\Program Files (x86)\GitHub CLI\gh.exe"),
)


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


def resolve_gh_cli() -> str | None:
    found = shutil.which("gh")
    if found:
        return found
    if sys.platform == "win32":
        for candidate in _WINDOWS_GH_CANDIDATES:
            if candidate.is_file():
                return str(candidate)
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            scoop = Path(local_app_data) / "Programs" / "gh" / "bin" / "gh.exe"
            if scoop.is_file():
                return str(scoop)
    return None


def gh_cli_available() -> bool:
    return resolve_gh_cli() is not None


def _run_gh(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    gh_exe = resolve_gh_cli()
    if not gh_exe:
        raise FileNotFoundError("GitHub CLI (gh) not found on PATH")
    return subprocess.run(
        [gh_exe, *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )


def gh_is_authenticated() -> bool:
    if not gh_cli_available():
        return False
    completed = _run_gh("auth", "status")
    return completed.returncode == 0


def gh_authenticate_web() -> None:
    if not gh_cli_available():
        raise ValueError(
            "GitHub CLI (gh) is required. Install from https://cli.github.com/ "
            "then try Quick start again."
        )
    if gh_is_authenticated():
        return
    completed = _run_gh("auth", "login", "-h", "github.com", "-p", "https", "-w")
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"GitHub sign-in failed: {detail}")
    _run_gh("auth", "setup-git")


def gh_current_username() -> str:
    completed = _run_gh("api", "user", "-q", ".login")
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"Could not read GitHub username: {detail}")
    username = completed.stdout.strip()
    if not username:
        raise RuntimeError("GitHub username is empty")
    return username


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
    authenticate_github: bool = True,
    github_token: str | None = None,
    repo_path: Path | None = None,
    branch: str | None = None,
    remote: str = DEFAULT_REMOTE,
    auto_sync_enabled: bool = False,
    auto_resolve_enabled: bool = True,
    interval_hours: int = 4,
) -> dict:
    actions: list[str] = []
    warnings: list[str] = []
    owner_override, repo_slug = parse_owner_repo(repo_name)
    slug = normalize_repo_name(repo_slug)
    target = _resolve_quickstart_target(repo_path)
    if repo_path and _is_ephemeral_repo_path(repo_path.expanduser().resolve()):
        actions.append(f"Ignored test/temp repo path; using {target}")
    branch_name = branch or DEFAULT_BRANCH
    username: str | None = owner_override
    remote_url = ""
    token = resolve_github_token(github_token)
    auth_method = "none"

    if authenticate_github:
        if token:
            auth_method = "token"
            if github_token:
                store_github_token(github_token)
                actions.append("Saved GitHub token for push and pull")
            username = username or get_authenticated_user(token)
            actions.append(f"Signed in to GitHub as {username}")
            remote_url = public_clone_url(username, slug)
        elif gh_cli_available():
            auth_method = "gh"
            actions.append("Opening GitHub sign-in in your browser")
            gh_authenticate_web()
            actions.append("Signed in to GitHub")
            username = gh_current_username()
            remote_url = public_clone_url(username, slug)
        else:
            raise ValueError(
                "GitHub sign-in requires a personal access token or GitHub CLI (gh). "
                "Set GITHUB_TOKEN, paste a token under Advanced options, or install gh "
                "from https://cli.github.com/"
            )
    elif token:
        auth_method = "token"
        username = username or get_authenticated_user(token)
        remote_url = public_clone_url(username, slug)
    elif gh_is_authenticated():
        auth_method = "gh"
        username = gh_current_username()
        remote_url = public_clone_url(username, slug)

    if not (target / ".git").exists():
        if (
            remote_url
            and username
            and _remote_repo_exists(auth_method, token, username, slug)
        ):
            _clone_existing_repo(
                target,
                remote_url,
                remote,
                token if auth_method == "token" else None,
                actions,
            )
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
        if authenticate_github:
            if auth_method == "token" and token:
                created = _create_github_repo_api(
                    target, token, username, slug, branch_name, warnings
                )
            elif auth_method == "gh":
                created = _create_github_repo(target, username, slug, remote, warnings)
            else:
                created = None
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
        "gh_available": gh_cli_available(),
        "github_authenticated": gh_is_authenticated() or bool(token),
        "github_token_configured": bool(resolve_github_token()),
        "auth_method": auth_method,
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
) -> str | None:
    full_name = f"{username}/{repo_name}"
    try:
        if repo_exists(token, username, repo_name):
            if token:
                push_url = authed_clone_url(username, repo_name, token)
                try:
                    git_push_with_token(path, token, push_url, branch)
                except RuntimeError as exc:
                    warnings.append(str(exc))
            return f"Linked to existing GitHub repository {full_name}"
        create_private_repo(
            token,
            repo_name,
            description="Suzent portable brain sync",
        )
        push_url = authed_clone_url(username, repo_name, token)
        git_push_with_token(path, token, push_url, branch)
        return (
            f"Created private GitHub repository {full_name} and pushed initial commit"
        )
    except (GitHubApiError, RuntimeError) as exc:
        warnings.append(f"Could not create GitHub repository: {exc}")
        return None


def _remote_repo_exists(
    auth_method: str,
    token: str | None,
    username: str,
    repo_name: str,
) -> bool:
    if auth_method == "token" and token:
        try:
            return repo_exists(token, username, repo_name)
        except GitHubApiError:
            return False
    if auth_method == "gh":
        return _run_gh("repo", "view", f"{username}/{repo_name}").returncode == 0
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


def _create_github_repo(
    path: Path, username: str, repo_name: str, remote: str, warnings: list[str]
) -> str | None:
    full_name = f"{username}/{repo_name}"
    view = _run_gh("repo", "view", full_name, cwd=path)
    if view.returncode == 0:
        branch = _detect_branch(path)
        try:
            _git_in(path, "push", "-u", remote, branch)
        except RuntimeError as exc:
            warnings.append(f"Could not push to {full_name}: {exc}")
        return f"Linked to existing GitHub repository {full_name}"

    completed = _run_gh(
        "repo",
        "create",
        repo_name,
        "--private",
        f"--remote={remote}",
        "--source=.",
        "--push",
        "--description=Suzent portable brain sync",
        cwd=path,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        warnings.append(f"Could not create GitHub repository: {detail}")
        return None
    return f"Created private GitHub repository {full_name} and pushed initial commit"


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
