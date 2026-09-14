"""A stale/broken repo_path in a profile self-heals to the canonical repo."""

import json
import subprocess
from pathlib import Path

from suzent.sync.service import GitHubSyncService


def _init_repo(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)


def test_stale_repo_path_redirects_to_canonical(tmp_path, monkeypatch):
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    # Canonical repo exists and is valid:
    canonical = tmp_path / "github-sync"
    _init_repo(canonical)

    # Profile points at a dead temp path:
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    dead = str(tmp_path / "gone" / "pytest-tmp" / "fresh-sync")
    (cfg / "sync_profiles.json").write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "id": "p1",
                        "device_id": "d1",
                        "repo_path": dead,
                        "remote": "origin",
                        "branch": "main",
                    }
                ]
            }
        )
    )

    svc = GitHubSyncService()
    prof = svc.get_profile("p1")
    # Redirected to the canonical repo...
    assert Path(prof.repo_path) == canonical
    # ...and persisted, so the fix survives a reload.
    on_disk = json.loads((cfg / "sync_profiles.json").read_text())
    assert on_disk["profiles"][0]["repo_path"] == str(canonical)


def test_healthy_repo_path_is_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    good = tmp_path / "my-repo"
    _init_repo(good)
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "sync_profiles.json").write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "id": "p1",
                        "device_id": "d1",
                        "repo_path": str(good),
                        "remote": "origin",
                        "branch": "main",
                    }
                ]
            }
        )
    )
    svc = GitHubSyncService()
    assert Path(svc.get_profile("p1").repo_path) == good


def test_no_canonical_leaves_broken_path(tmp_path, monkeypatch):
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    dead = str(tmp_path / "gone")
    (cfg / "sync_profiles.json").write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "id": "p1",
                        "device_id": "d1",
                        "repo_path": dead,
                        "remote": "origin",
                        "branch": "main",
                    }
                ]
            }
        )
    )
    svc = GitHubSyncService()
    # Nothing valid to redirect to → left as-is (surfaced via logs), not crashed.
    assert svc.get_profile("p1").repo_path == dead


def _init_repo_with_remotes(path: Path, remotes: dict[str, str]):
    _init_repo(path)
    for name, url in remotes.items():
        subprocess.run(
            ["git", "-C", str(path), "remote", "add", name, url],
            check=True,
            capture_output=True,
        )


def _write_profile(cfg: Path, repo_path: Path, remote: str):
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "sync_profiles.json").write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "id": "p1",
                        "device_id": "d1",
                        "repo_path": str(repo_path),
                        "remote": remote,
                        "branch": "main",
                    }
                ]
            }
        )
    )


def test_missing_remote_heals_to_origin(tmp_path, monkeypatch):
    """A profile naming a remote the repo lacks repoints to the sole remote.

    This is the exact shape of the leaked-test-profile bug: remote="upstream"
    on a repo that only ever had "origin", which broke every sync op with
    "git remote get-url upstream failed: No such remote".
    """
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    repo = tmp_path / "github-sync"
    _init_repo_with_remotes(repo, {"origin": "https://github.com/alice/brain.git"})
    cfg = tmp_path / "config"
    _write_profile(cfg, repo, "upstream")

    svc = GitHubSyncService()
    assert svc.get_profile("p1").remote == "origin"
    # ...and persisted, so the fix survives a reload.
    on_disk = json.loads((cfg / "sync_profiles.json").read_text())
    assert on_disk["profiles"][0]["remote"] == "origin"


def test_missing_remote_heals_to_sole_remote(tmp_path, monkeypatch):
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    repo = tmp_path / "github-sync"
    _init_repo_with_remotes(repo, {"github": "https://github.com/alice/brain.git"})
    _write_profile(tmp_path / "config", repo, "upstream")

    svc = GitHubSyncService()
    assert svc.get_profile("p1").remote == "github"


def test_existing_remote_is_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    repo = tmp_path / "github-sync"
    _init_repo_with_remotes(
        repo,
        {
            "origin": "https://github.com/alice/fork.git",
            "upstream": "https://github.com/alice/brain.git",
        },
    )
    _write_profile(tmp_path / "config", repo, "upstream")

    svc = GitHubSyncService()
    # "upstream" really exists here — must not be rewritten to origin.
    assert svc.get_profile("p1").remote == "upstream"


def test_ambiguous_remotes_left_alone(tmp_path, monkeypatch):
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    repo = tmp_path / "github-sync"
    _init_repo_with_remotes(
        repo,
        {
            "github": "https://github.com/alice/brain.git",
            "backup": "https://github.com/alice/backup.git",
        },
    )
    _write_profile(tmp_path / "config", repo, "upstream")

    svc = GitHubSyncService()
    # More than one candidate — guessing could push the user's brain to the
    # wrong repo, so the profile is left for manual reconfiguration.
    assert svc.get_profile("p1").remote == "upstream"


def test_repo_with_no_remotes_left_alone(tmp_path, monkeypatch):
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    repo = tmp_path / "github-sync"
    _init_repo(repo)
    _write_profile(tmp_path / "config", repo, "upstream")

    svc = GitHubSyncService()
    assert svc.get_profile("p1").remote == "upstream"


def test_origin_not_preferred_when_other_remotes_exist(tmp_path, monkeypatch):
    """ "origin" alongside other remotes is ambiguous, not a safe default.

    "origin" is conventional, not authoritative — it is often a fork while
    another remote is the real sync destination. Healing to it by name could
    push the user's portable brain to the wrong repository, so a multi-remote
    repo is left for manual reconfiguration even when "origin" is present.
    """
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    repo = tmp_path / "github-sync"
    _init_repo_with_remotes(
        repo,
        {
            "origin": "https://github.com/alice/fork.git",
            "canonical": "https://github.com/acme/brain.git",
        },
    )
    _write_profile(tmp_path / "config", repo, "upstream")

    svc = GitHubSyncService()
    assert svc.get_profile("p1").remote == "upstream"
