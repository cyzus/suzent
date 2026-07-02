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
