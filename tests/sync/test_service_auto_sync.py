import asyncio
from pathlib import Path

from suzent.sync import service as service_module
from suzent.sync.models import SyncManifest, SyncProfile
from suzent.sync.payload import PAYLOAD_DIR_NAME
from suzent.sync.service import GitHubSyncService


class FakePayloadBuilder:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def build(self, repo_path: Path, profile: SyncProfile) -> SyncManifest:
        self.calls.append("build")
        (repo_path / PAYLOAD_DIR_NAME).mkdir(parents=True, exist_ok=True)
        return SyncManifest(
            revision_id="rev-local",
            source_device=profile.device_id,
            included_paths=[],
            content_hashes={},
        )

    def validate_no_forbidden_paths(self, payload_dir: Path) -> list[str]:
        self.calls.append("validate")
        return []

    def apply_to_local(self, payload_dir: Path) -> list[str]:
        self.calls.append("apply")
        return ["config"]


class FakeProvider:
    git_output = "pushed"
    meaningful_changes = True
    calls: list[str] = []

    def __init__(self, repo_path: Path, *, remote: str, branch: str) -> None:
        self.repo_path = repo_path

    def commit_and_push_payload(self, revision_id: str) -> str:
        self.calls.append("push")
        return self.git_output

    def has_meaningful_payload_changes(self) -> bool:
        self.calls.append("changed")
        return self.meaningful_changes

    def pull_ff_only(self) -> str:
        self.calls.append("pull")
        return "pulled"


def test_auto_sync_pushes_local_payload_before_remote_apply(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    FakeProvider.calls = calls
    FakeProvider.git_output = "pushed"
    FakeProvider.meaningful_changes = True
    monkeypatch.setattr(service_module, "GitHubSyncProvider", FakeProvider)
    monkeypatch.setattr(
        service_module, "_reload_runtime", lambda: calls.append("reload")
    )

    service = GitHubSyncService(
        profiles_path=tmp_path / "profiles.json",
        payload_builder=FakePayloadBuilder(calls),
    )
    profile = service.save_profile(SyncProfile(repo_path=str(tmp_path / "repo")))

    asyncio.run(service.auto_sync(profile.id))

    assert calls == ["build", "validate", "changed", "pull", "push"]


def test_auto_sync_applies_remote_when_local_payload_has_no_changes(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    FakeProvider.calls = calls
    FakeProvider.git_output = "No sync payload changes to push."
    FakeProvider.meaningful_changes = False
    monkeypatch.setattr(service_module, "GitHubSyncProvider", FakeProvider)
    monkeypatch.setattr(
        service_module, "_reload_runtime", lambda: calls.append("reload")
    )

    service = GitHubSyncService(
        profiles_path=tmp_path / "profiles.json",
        payload_builder=FakePayloadBuilder(calls),
    )
    profile = service.save_profile(SyncProfile(repo_path=str(tmp_path / "repo")))

    asyncio.run(service.auto_sync(profile.id))

    assert calls == ["build", "validate", "changed", "pull", "apply", "reload"]
