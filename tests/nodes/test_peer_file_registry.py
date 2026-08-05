from datetime import datetime, timedelta, timezone

from suzent.nodes.peer_files import PeerFileRegistry


def test_registry_returns_unknown_and_expired_artifacts_as_missing(tmp_path):
    registry = PeerFileRegistry()

    assert registry.get("pf_unknown") is None

    artifact_path = tmp_path / "artifact.txt"
    artifact_path.write_text("peer data", encoding="utf-8")
    artifact = registry.register(artifact_path, ttl_seconds=60)
    registry._artifacts[artifact.file_id].expires_at = datetime.now(
        timezone.utc
    ) - timedelta(seconds=1)

    assert registry.get(artifact.file_id) is None
    assert artifact.file_id not in registry._artifacts


def test_registry_invalidates_artifact_when_file_disappears(tmp_path):
    registry = PeerFileRegistry()
    artifact_path = tmp_path / "artifact.txt"
    artifact_path.write_text("peer data", encoding="utf-8")
    artifact = registry.register(artifact_path)
    artifact_path.unlink()

    assert registry.get(artifact.file_id) is None
    assert artifact.file_id not in registry._artifacts
