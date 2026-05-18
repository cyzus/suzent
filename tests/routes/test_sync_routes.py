from pathlib import Path

from starlette.testclient import TestClient

from suzent.server import app
from suzent.sync.models import SyncProfile
from suzent.sync.payload import PAYLOAD_DIR_NAME
from suzent.sync.service import GitHubSyncService


def test_sync_profile_create_read_status(tmp_path: Path):
    service = GitHubSyncService(profiles_path=tmp_path / "profiles.json")
    app.state.github_sync_service = service
    client = TestClient(app)

    response = client.post(
        "/sync/profiles",
        json={"repo_path": str(tmp_path / "repo"), "branch": "main", "remote": "origin"},
    )

    assert response.status_code == 200
    profile = response.json()
    profiles = client.get("/sync/profiles").json()["profiles"]
    status = client.get("/sync/status").json()
    assert profiles[0]["id"] == profile["id"]
    assert status["configured"] is True
    assert status["profile"]["repo_path"] == str(tmp_path / "repo")


def test_sync_conflict_resolve_preview_uses_portable_files_only(tmp_path: Path):
    service = GitHubSyncService(profiles_path=tmp_path / "profiles.json")
    app.state.github_sync_service = service
    client = TestClient(app)
    repo = tmp_path / "repo"
    payload_dir = repo / PAYLOAD_DIR_NAME
    (payload_dir / "memory").mkdir(parents=True)
    (payload_dir / "_sync" / "secrets").mkdir(parents=True)
    (payload_dir / "memory" / "MEMORY.md").write_text("merged", encoding="utf-8")
    (payload_dir / "_sync" / "secrets" / "bundles.json").write_text(
        '{"ciphertext":"abc"}',
        encoding="utf-8",
    )
    profile = service.create_profile(SyncProfile(repo_path=str(repo)))

    response = client.post(
        "/sync/conflicts/resolve-agent",
        json={
            "profile_id": profile.id,
            "conflicting_paths": [
                "memory/MEMORY.md",
                "_sync/secrets/bundles.json",
            ],
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "preview"
    assert result["changed_paths"] == ["memory/MEMORY.md"]


def test_unlock_shibboleth_endpoint(tmp_path: Path):
    service = GitHubSyncService(profiles_path=tmp_path / "profiles.json")
    app.state.github_sync_service = service
    client = TestClient(app)
    profile = service.create_profile(
        SyncProfile(repo_path=str(tmp_path / "repo"), encrypted_secret_sync_enabled=True)
    )

    response = client.post(
        "/sync/shibboleth/unlock",
        json={"profile_id": profile.id, "shibboleth": "route-test-shibboleth"},
    )

    assert response.status_code == 200
    assert response.json()["shibboleth_unlocked"] is True
    status = client.get("/sync/status").json()
    assert status["shibboleth_unlocked"] is True
