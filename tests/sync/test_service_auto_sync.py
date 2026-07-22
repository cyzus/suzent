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

    def content_hashes(self, payload_dir: Path) -> dict[str, str]:
        self.calls.append("hashes")
        return {"memory/MEMORY.md": "cloud"}

    def preview_content_hashes(self, payload_dir: Path) -> dict[str, str]:
        self.calls.append("preview-hashes")
        return {}

    def apply_to_local(
        self, payload_dir: Path, *, replace_memory: bool = False
    ) -> list[str]:
        self.calls.append("apply-replace" if replace_memory else "apply")
        return ["config"]

    def apply_paths_to_local(self, payload_dir: Path, paths: list[str]) -> list[str]:
        self.calls.append(f"apply-paths:{','.join(paths)}")
        return paths

    def resolve_local_path(self, payload_path: str) -> tuple[Path, Path] | None:
        rel = Path(payload_path)
        if rel.parts[0] not in {"config", "skills", "memory"}:
            return None
        return rel, Path("local") / rel

    def has_outgoing_change(self, payload_dir: Path, payload_path: str) -> bool:
        return self.resolve_local_path(payload_path) is not None


class FakeProvider:
    git_output = "pushed"
    meaningful_changes = True
    payload_status_output = ""
    payload_diff_output = ""
    payload_remote_status_output = ""
    payload_remote_diff_output = ""
    calls: list[str] = []

    def __init__(self, repo_path: Path, *, remote: str, branch: str) -> None:
        self.repo_path = repo_path

    def commit_and_push_payload(self, revision_id: str) -> str:
        self.calls.append("push")
        return self.git_output

    def refresh_remote(self) -> None:
        self.calls.append("fetch")

    def has_meaningful_payload_changes(self) -> bool:
        self.calls.append("changed")
        return self.meaningful_changes

    def payload_status(self) -> str:
        self.calls.append("status")
        return self.payload_status_output

    def payload_worktree_diff_patch(self) -> str:
        self.calls.append("diff")
        return self.payload_diff_output

    def payload_diff_name_status(self, left_ref: str, right_ref: str) -> str:
        self.calls.append("remote-status")
        return self.payload_remote_status_output

    def payload_diff_patch(self, left_ref: str, right_ref: str) -> str:
        self.calls.append("remote-diff")
        return self.payload_remote_diff_output

    def pull_ff_only(self) -> str:
        self.calls.append("pull")
        return "pulled"

    def discard_payload_changes(self) -> None:
        self.calls.append("discard")

    def discard_payload_paths(self, paths: list[str]) -> None:
        self.calls.append(f"discard-paths:{','.join(paths)}")


def test_watched_plan_does_not_fetch_remote_or_generate_patches(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    FakeProvider.calls = calls
    FakeProvider.payload_remote_status_output = ""
    monkeypatch.setattr(service_module, "GitHubSyncProvider", FakeProvider)
    service = GitHubSyncService(
        profiles_path=tmp_path / "profiles.json",
        payload_builder=FakePayloadBuilder(calls),
    )
    profile = service.save_profile(SyncProfile(repo_path=str(tmp_path / "repo")))

    service.preview_sync_plan("auto", profile.id, refresh_remote=False)

    assert calls == ["hashes", "preview-hashes", "remote-status"]


def test_auto_sync_pushes_local_payload_before_remote_apply(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    FakeProvider.calls = calls
    FakeProvider.git_output = "pushed"
    FakeProvider.meaningful_changes = True
    FakeProvider.payload_status_output = ""
    FakeProvider.payload_diff_output = ""
    FakeProvider.payload_remote_status_output = ""
    FakeProvider.payload_remote_diff_output = ""
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

    assert calls == [
        "fetch",
        "build",
        "validate",
        "status",
        "remote-status",
        "changed",
        "pull",
        "push",
    ]


def test_auto_sync_applies_remote_when_local_payload_has_no_changes(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    FakeProvider.calls = calls
    FakeProvider.git_output = "No sync payload changes to push."
    FakeProvider.meaningful_changes = False
    FakeProvider.payload_status_output = ""
    FakeProvider.payload_diff_output = ""
    FakeProvider.payload_remote_status_output = ""
    FakeProvider.payload_remote_diff_output = ""
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

    assert calls == [
        "fetch",
        "build",
        "validate",
        "status",
        "remote-status",
        "changed",
        "pull",
        "apply",
        "reload",
    ]


def test_auto_sync_blocks_destructive_memory_deletes(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    FakeProvider.calls = calls
    FakeProvider.meaningful_changes = True
    FakeProvider.payload_status_output = " D suzent-sync/memory/archive/2026-07-08.md\n"
    FakeProvider.payload_remote_status_output = ""
    FakeProvider.payload_remote_diff_output = ""
    FakeProvider.payload_diff_output = """diff --git a/suzent-sync/memory/archive/2026-07-08.md b/suzent-sync/memory/archive/2026-07-08.md
deleted file mode 100644
--- a/suzent-sync/memory/archive/2026-07-08.md
+++ /dev/null
@@ -1 +0,0 @@
-old memory
"""
    monkeypatch.setattr(service_module, "GitHubSyncProvider", FakeProvider)

    service = GitHubSyncService(
        profiles_path=tmp_path / "profiles.json",
        payload_builder=FakePayloadBuilder(calls),
    )
    profile = service.save_profile(SyncProfile(repo_path=str(tmp_path / "repo")))

    result = asyncio.run(service.auto_sync(profile.id))

    assert result["success"] is False
    assert result["blocked_review_required"] is True
    assert result["plan"]["requires_confirmation"] is True
    assert result["plan"]["files"][0]["direction"] == "outgoing"
    assert calls == [
        "fetch",
        "build",
        "validate",
        "status",
        "remote-status",
    ]


def test_auto_sync_blocks_mixed_incoming_and_outgoing_changes(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    FakeProvider.calls = calls
    FakeProvider.meaningful_changes = True
    FakeProvider.payload_status_output = " M suzent-sync/config/local.yaml\n"
    FakeProvider.payload_diff_output = ""
    FakeProvider.payload_remote_status_output = (
        "M\tsuzent-sync/skills/remote/SKILL.md\n"
    )
    FakeProvider.payload_remote_diff_output = ""
    monkeypatch.setattr(service_module, "GitHubSyncProvider", FakeProvider)

    service = GitHubSyncService(
        profiles_path=tmp_path / "profiles.json",
        payload_builder=FakePayloadBuilder(calls),
    )
    profile = service.save_profile(SyncProfile(repo_path=str(tmp_path / "repo")))

    result = asyncio.run(service.auto_sync(profile.id, confirm_destructive=True))

    assert result["success"] is False
    assert result["blocked_review_required"] is True
    assert result["plan"]["requires_confirmation"] is True
    assert result["plan"]["warnings"] == [
        "Incoming and outgoing files must be resolved before auto-sync."
    ]
    assert {item["direction"] for item in result["plan"]["files"]} == {
        "incoming",
        "outgoing",
    }
    assert "pull" not in calls
    assert "push" not in calls


def test_discard_outgoing_restores_local_from_cloud_payload(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    FakeProvider.calls = calls
    FakeProvider.payload_status_output = " M suzent-sync/memory/MEMORY.md\n"
    FakeProvider.payload_diff_output = """diff --git a/suzent-sync/memory/MEMORY.md b/suzent-sync/memory/MEMORY.md
--- a/suzent-sync/memory/MEMORY.md
+++ b/suzent-sync/memory/MEMORY.md
@@ -1 +1 @@
-cloud
+local
"""
    FakeProvider.payload_remote_status_output = ""
    FakeProvider.payload_remote_diff_output = ""
    monkeypatch.setattr(service_module, "GitHubSyncProvider", FakeProvider)
    monkeypatch.setattr(
        service_module, "_reload_runtime", lambda: calls.append("reload")
    )

    service = GitHubSyncService(
        profiles_path=tmp_path / "profiles.json",
        payload_builder=FakePayloadBuilder(calls),
    )
    profile = service.save_profile(SyncProfile(repo_path=str(tmp_path / "repo")))

    result = asyncio.run(service.discard_outgoing(profile.id))

    assert result["success"] is True
    assert result["discarded"] == ["memory/MEMORY.md"]
    assert calls == [
        "hashes",
        "preview-hashes",
        "discard",
        "apply-replace",
        "reload",
    ]


def test_discard_outgoing_can_restore_one_selected_path(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    FakeProvider.calls = calls
    FakeProvider.payload_status_output = (
        " M suzent-sync/memory/MEMORY.md\n M suzent-sync/config/providers.json\n"
    )
    FakeProvider.payload_diff_output = ""
    FakeProvider.payload_remote_status_output = ""
    FakeProvider.payload_remote_diff_output = ""
    monkeypatch.setattr(service_module, "GitHubSyncProvider", FakeProvider)
    monkeypatch.setattr(
        service_module,
        "_reload_runtime_for_paths",
        lambda paths: calls.append("reload"),
    )

    service = GitHubSyncService(
        profiles_path=tmp_path / "profiles.json",
        payload_builder=FakePayloadBuilder(calls),
    )
    profile = service.save_profile(SyncProfile(repo_path=str(tmp_path / "repo")))

    result = asyncio.run(
        service.discard_outgoing(profile.id, paths=["config/providers.json"])
    )

    assert result["discarded"] == ["config/providers.json"]
    assert calls == [
        "discard-paths:config/providers.json",
        "apply-paths:config/providers.json",
        "reload",
    ]
