from pathlib import Path

from suzent.sync.models import SyncProfile
from suzent.sync.payload import PAYLOAD_DIR_NAME, SyncPayloadBuilder


def test_sync_payload_excludes_plaintext_secrets_runtime_chats_and_indexes(tmp_path: Path):
    data_dir = tmp_path / ".suzent"
    config_dir = data_dir / "config"
    skills_dir = data_dir / "skills"
    memory_dir = data_dir / "sandbox" / "shared" / "memory"
    repo = tmp_path / "repo"
    repo.mkdir()

    config_dir.mkdir(parents=True)
    (config_dir / "default.yaml").write_text("model: ok\n", encoding="utf-8")
    (config_dir / ".env").write_text("OPENAI_API_KEY=plain", encoding="utf-8")
    (config_dir / "sync_profiles.json").write_text(
        '{"profiles": [{"repo_path": "device-local"}]}',
        encoding="utf-8",
    )
    skills_dir.mkdir()
    (skills_dir / "writer.md").write_text("enabled", encoding="utf-8")
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text("remember", encoding="utf-8")
    (memory_dir / "sessions" / "abc").mkdir(parents=True)
    (memory_dir / "sessions" / "abc" / "context.md").write_text("local", encoding="utf-8")
    (data_dir / "runtime").mkdir()
    (data_dir / "cache").mkdir()
    (data_dir / "exports").mkdir()
    (data_dir / "backups").mkdir()
    (data_dir / "chats.db").write_text("chat", encoding="utf-8")
    (data_dir / "secrets.db").write_text("encrypted-local-db", encoding="utf-8")
    (data_dir / ".secret_key").write_text("local-key", encoding="utf-8")

    builder = SyncPayloadBuilder(
        data_dir=data_dir,
        user_config_dir=config_dir,
        user_skills_dir=skills_dir,
        sandbox_data_path=data_dir / "sandbox",
    )
    manifest = builder.build(repo, SyncProfile(repo_path=str(repo)))

    payload_dir = repo / PAYLOAD_DIR_NAME
    included = set(manifest.included_paths)
    assert "config/default.yaml" in included
    assert "skills/writer.md" in included
    assert "memory/MEMORY.md" in included
    assert not builder.validate_no_forbidden_paths(payload_dir)
    assert not (payload_dir / "config" / ".env").exists()
    assert not (payload_dir / "config" / "sync_profiles.json").exists()
    assert not (payload_dir / "memory" / "sessions").exists()
    assert not (payload_dir / "chats.db").exists()
    assert not (payload_dir / "secrets.db").exists()


def test_manifest_hashes_change_when_portable_file_changes(tmp_path: Path):
    config_dir = tmp_path / "config"
    skills_dir = tmp_path / "skills"
    memory_dir = tmp_path / "sandbox" / "shared" / "memory"
    repo = tmp_path / "repo"
    config_dir.mkdir()
    skills_dir.mkdir()
    memory_dir.mkdir(parents=True)
    repo.mkdir()
    config_file = config_dir / "default.yaml"
    config_file.write_text("a: 1\n", encoding="utf-8")

    builder = SyncPayloadBuilder(
        user_config_dir=config_dir,
        user_skills_dir=skills_dir,
        sandbox_data_path=tmp_path / "sandbox",
    )
    profile = SyncProfile(repo_path=str(repo))
    first = builder.build(repo, profile)
    config_file.write_text("a: 2\n", encoding="utf-8")
    second = builder.build(repo, profile)

    assert (
        first.content_hashes["config/default.yaml"]
        != second.content_hashes["config/default.yaml"]
    )


def test_apply_to_local_preserves_device_local_sync_profile(tmp_path: Path):
    payload_dir = tmp_path / "payload"
    source_config = payload_dir / "config"
    target_config = tmp_path / "local" / "config"
    source_config.mkdir(parents=True)
    target_config.mkdir(parents=True)
    (source_config / "config.yaml").write_text("remote: true\n", encoding="utf-8")
    (source_config / "sync_profiles.json").write_text(
        '{"profiles": [{"repo_path": "remote-device"}]}',
        encoding="utf-8",
    )
    (target_config / "config.yaml").write_text("local: true\n", encoding="utf-8")
    (target_config / "sync_profiles.json").write_text(
        '{"profiles": [{"repo_path": "local-device"}]}',
        encoding="utf-8",
    )

    builder = SyncPayloadBuilder(
        user_config_dir=target_config,
        user_skills_dir=tmp_path / "local" / "skills",
        sandbox_data_path=tmp_path / "local" / "sandbox",
    )

    restored = builder.apply_to_local(payload_dir)

    assert restored == ["config"]
    assert (target_config / "config.yaml").read_text(encoding="utf-8") == "remote: true\n"
    assert "local-device" in (target_config / "sync_profiles.json").read_text(
        encoding="utf-8"
    )
