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

    assert first.content_hashes["config/default.yaml"] != second.content_hashes["config/default.yaml"]
