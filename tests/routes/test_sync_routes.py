from pathlib import Path

from starlette.testclient import TestClient

from suzent.server import app
from suzent.sync.models import SyncPlan, SyncProfile
from suzent.sync.payload import PAYLOAD_DIR_NAME
from suzent.sync.service import DestructiveSyncPlanError, GitHubSyncService


def _review_plan(operation: str = "push") -> SyncPlan:
    return SyncPlan(
        operation=operation,
        files=[
            {
                "path": "memory/archive/2026-07-08.md",
                "category": "memory",
                "change_type": "deleted",
                "risk": "high",
            }
        ],
        summary={"added": 0, "modified": 0, "deleted": 1, "high_risk": 1},
        destructive=True,
        requires_confirmation=True,
        warnings=["1 memory file(s) would be deleted."],
    )


def test_sync_profile_create_read_status(tmp_path: Path):
    service = GitHubSyncService(profiles_path=tmp_path / "profiles.json")
    app.state.github_sync_service = service
    client = TestClient(app)

    response = client.post(
        "/sync/profiles",
        json={
            "repo_path": str(tmp_path / "repo"),
            "branch": "main",
            "remote": "origin",
        },
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
        SyncProfile(
            repo_path=str(tmp_path / "repo"), encrypted_secret_sync_enabled=True
        )
    )

    response = client.post(
        "/sync/shibboleth/unlock",
        json={"profile_id": profile.id, "shibboleth": "route-test-shibboleth"},
    )

    assert response.status_code == 200
    assert response.json()["shibboleth_unlocked"] is True
    status = client.get("/sync/status").json()
    assert status["shibboleth_unlocked"] is True


def test_sync_plan_endpoint_returns_review_plan():
    class FakeService:
        def preview_sync_plan(self, operation: str, profile_id: str | None = None):
            assert operation == "push"
            assert profile_id == "profile-1"
            return _review_plan(operation)

    app.state.github_sync_service = FakeService()
    client = TestClient(app)

    response = client.post(
        "/sync/plan",
        json={"operation": "push", "profile_id": "profile-1"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["requires_confirmation"] is True
    assert result["files"][0]["path"] == "memory/archive/2026-07-08.md"
    assert result["files"][0]["risk"] == "high"


def test_push_sync_returns_409_when_review_is_required():
    class FakeService:
        async def push(
            self,
            profile_id: str | None = None,
            *,
            shibboleth: str | None = None,
            confirm_destructive: bool = False,
        ):
            assert profile_id == "profile-1"
            assert shibboleth is None
            assert confirm_destructive is False
            raise DestructiveSyncPlanError(_review_plan("push"))

    app.state.github_sync_service = FakeService()
    client = TestClient(app)

    response = client.post("/sync/push", json={"profile_id": "profile-1"})

    assert response.status_code == 409
    result = response.json()
    assert result["review_required"] is True
    assert result["plan"]["operation"] == "push"
    assert result["plan"]["warnings"] == ["1 memory file(s) would be deleted."]


def test_confirmed_sync_routes_pass_destructive_confirmation():
    calls: list[tuple[str, bool, bool]] = []

    class FakeService:
        async def pull(
            self,
            profile_id: str | None = None,
            *,
            shibboleth: str | None = None,
            confirm_destructive: bool = False,
            prefer_cloud: bool = False,
            paths: list[str] | None = None,
        ):
            assert profile_id == "profile-1"
            assert paths is None
            calls.append(("pull", confirm_destructive, prefer_cloud))
            return {"success": True}

        async def push(
            self,
            profile_id: str | None = None,
            *,
            shibboleth: str | None = None,
            confirm_destructive: bool = False,
        ):
            assert profile_id == "profile-1"
            calls.append(("push", confirm_destructive, False))
            return {"success": True}

        async def auto_sync(
            self,
            profile_id: str | None = None,
            *,
            shibboleth: str | None = None,
            confirm_destructive: bool = False,
        ):
            assert profile_id == "profile-1"
            calls.append(("auto", confirm_destructive, False))
            return {"success": True}

    app.state.github_sync_service = FakeService()
    client = TestClient(app)

    for route in ("/sync/pull", "/sync/push", "/sync/auto/run"):
        response = client.post(
            route,
            json={"profile_id": "profile-1", "confirm_destructive": True},
        )
        assert response.status_code == 200

    assert calls == [
        ("pull", True, False),
        ("push", True, False),
        ("auto", True, False),
    ]


def test_pull_sync_passes_prefer_cloud():
    class FakeService:
        async def pull(
            self,
            profile_id: str | None = None,
            *,
            shibboleth: str | None = None,
            confirm_destructive: bool = False,
            prefer_cloud: bool = False,
            paths: list[str] | None = None,
        ):
            assert profile_id == "profile-1"
            assert confirm_destructive is True
            assert prefer_cloud is True
            assert paths == ["memory/MEMORY.md"]
            return {"success": True, "prefer_cloud": prefer_cloud, "paths": paths}

    app.state.github_sync_service = FakeService()
    client = TestClient(app)

    response = client.post(
        "/sync/pull",
        json={
            "profile_id": "profile-1",
            "confirm_destructive": True,
            "prefer_cloud": True,
            "paths": ["memory/MEMORY.md"],
        },
    )

    assert response.status_code == 200
    assert response.json()["prefer_cloud"] is True
    assert response.json()["paths"] == ["memory/MEMORY.md"]


def test_discard_outgoing_route_calls_service():
    class FakeService:
        async def discard_outgoing(
            self,
            profile_id: str | None = None,
            *,
            paths: list[str] | None = None,
        ):
            assert profile_id == "profile-1"
            assert paths == ["memory/MEMORY.md"]
            return {"success": True, "discarded": paths}

    app.state.github_sync_service = FakeService()
    client = TestClient(app)

    response = client.post(
        "/sync/discard-outgoing",
        json={"profile_id": "profile-1", "paths": ["memory/MEMORY.md"]},
    )

    assert response.status_code == 200
    assert response.json()["discarded"] == ["memory/MEMORY.md"]
