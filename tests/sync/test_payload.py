from pathlib import Path

from suzent.sync.models import SyncProfile
from suzent.sync.payload import PAYLOAD_DIR_NAME, SyncPayloadBuilder


def test_sync_payload_excludes_plaintext_secrets_runtime_chats_and_indexes(
    tmp_path: Path,
):
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
    # Node-mesh device/auth state is machine-local and must not sync.
    (config_dir / "node_devices.json").write_text('{"devices": []}', encoding="utf-8")
    (config_dir / "node_host_devices.json").write_text(
        '{"tokens": ["secret-token"]}', encoding="utf-8"
    )
    (config_dir / "node_peers.json").write_text('{"peers": []}', encoding="utf-8")
    (config_dir / "permission-audit.jsonl").write_text("{}\n", encoding="utf-8")
    skills_dir.mkdir()
    (skills_dir / "writer.md").write_text("enabled", encoding="utf-8")
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text("remember", encoding="utf-8")
    (memory_dir / "sessions" / "abc").mkdir(parents=True)
    (memory_dir / "sessions" / "abc" / "context.md").write_text(
        "local", encoding="utf-8"
    )
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
    assert not (payload_dir / "config" / "node_devices.json").exists()
    assert not (payload_dir / "config" / "node_host_devices.json").exists()
    assert not (payload_dir / "config" / "node_peers.json").exists()
    assert not (payload_dir / "config" / "permission-audit.jsonl").exists()


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


def test_build_preserves_existing_payload_memory_when_local_memory_is_partial(
    tmp_path: Path,
):
    config_dir = tmp_path / "config"
    skills_dir = tmp_path / "skills"
    memory_dir = tmp_path / "sandbox" / "shared" / "memory"
    repo = tmp_path / "repo"
    payload_memory = repo / PAYLOAD_DIR_NAME / "memory"
    config_dir.mkdir()
    skills_dir.mkdir()
    memory_dir.mkdir(parents=True)
    payload_memory.mkdir(parents=True)
    (payload_memory / "MEMORY.md").write_text("remote summary\n", encoding="utf-8")
    (payload_memory / "archive" / "2026-07-08.md").parent.mkdir()
    (payload_memory / "archive" / "2026-07-08.md").write_text(
        "older fact\n",
        encoding="utf-8",
    )
    (memory_dir / "archive").mkdir()
    (memory_dir / "archive" / "2026-07-09.md").write_text(
        "new fact\n",
        encoding="utf-8",
    )

    builder = SyncPayloadBuilder(
        user_config_dir=config_dir,
        user_skills_dir=skills_dir,
        sandbox_data_path=tmp_path / "sandbox",
    )

    manifest = builder.build(repo, SyncProfile(repo_path=str(repo)))

    included = set(manifest.included_paths)
    assert "memory/MEMORY.md" in included
    assert "memory/archive/2026-07-08.md" in included
    assert "memory/archive/2026-07-09.md" in included
    assert (payload_memory / "MEMORY.md").read_text(
        encoding="utf-8"
    ) == "remote summary\n"


def test_build_removes_legacy_secret_bundle_from_portable_payload(tmp_path: Path):
    config_dir = tmp_path / "config"
    skills_dir = tmp_path / "skills"
    memory_dir = tmp_path / "sandbox" / "shared" / "memory"
    repo = tmp_path / "repo"
    bundles_path = repo / PAYLOAD_DIR_NAME / "_sync" / "secrets" / "bundles.json"
    config_dir.mkdir()
    skills_dir.mkdir()
    memory_dir.mkdir(parents=True)
    bundles_path.parent.mkdir(parents=True)
    bundles_path.write_text('{"format_version":2,"bundles":[]}\n', encoding="utf-8")

    builder = SyncPayloadBuilder(
        user_config_dir=config_dir,
        user_skills_dir=skills_dir,
        sandbox_data_path=tmp_path / "sandbox",
    )

    manifest = builder.build(repo, SyncProfile(repo_path=str(repo)))

    assert not bundles_path.exists()
    assert "_sync/secrets/bundles.json" not in manifest.included_paths


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
    assert (target_config / "config.yaml").read_text(
        encoding="utf-8"
    ) == "remote: true\n"
    assert "local-device" in (target_config / "sync_profiles.json").read_text(
        encoding="utf-8"
    )


def test_apply_to_local_merges_memory_without_deleting_local_only_files(
    tmp_path: Path,
):
    payload_dir = tmp_path / "payload"
    source_memory = payload_dir / "memory"
    target_sandbox = tmp_path / "local" / "sandbox"
    target_memory = target_sandbox / "shared" / "memory"
    source_memory.mkdir(parents=True)
    target_memory.mkdir(parents=True)
    (source_memory / "archive").mkdir()
    (source_memory / "archive" / "2026-07-09.md").write_text(
        "remote today\n",
        encoding="utf-8",
    )
    (target_memory / "MEMORY.md").write_text("local summary\n", encoding="utf-8")
    (target_memory / "archive").mkdir(exist_ok=True)
    (target_memory / "archive" / "2026-07-08.md").write_text(
        "local older fact\n",
        encoding="utf-8",
    )

    builder = SyncPayloadBuilder(
        user_config_dir=tmp_path / "local" / "config",
        user_skills_dir=tmp_path / "local" / "skills",
        sandbox_data_path=target_sandbox,
    )

    restored = builder.apply_to_local(payload_dir)

    assert restored == ["memory"]
    assert (target_memory / "MEMORY.md").read_text(
        encoding="utf-8"
    ) == "local summary\n"
    assert (target_memory / "archive" / "2026-07-08.md").read_text(
        encoding="utf-8"
    ) == "local older fact\n"
    assert (target_memory / "archive" / "2026-07-09.md").read_text(
        encoding="utf-8"
    ) == "remote today\n"


def test_apply_to_local_can_replace_memory_when_cloud_is_authority(tmp_path: Path):
    payload_dir = tmp_path / "payload"
    source_memory = payload_dir / "memory"
    target_sandbox = tmp_path / "local" / "sandbox"
    target_memory = target_sandbox / "shared" / "memory"
    source_memory.mkdir(parents=True)
    target_memory.mkdir(parents=True)
    (source_memory / "MEMORY.md").write_text("cloud summary\n", encoding="utf-8")
    (target_memory / "MEMORY.md").write_text("local summary\n", encoding="utf-8")
    (target_memory / "local-only.md").write_text("local only\n", encoding="utf-8")
    (target_memory / "sessions" / "abc").mkdir(parents=True)
    (target_memory / "sessions" / "abc" / "context.md").write_text(
        "device local\n",
        encoding="utf-8",
    )

    builder = SyncPayloadBuilder(
        user_config_dir=tmp_path / "local" / "config",
        user_skills_dir=tmp_path / "local" / "skills",
        sandbox_data_path=target_sandbox,
    )

    restored = builder.apply_to_local(payload_dir, replace_memory=True)

    assert restored == ["memory"]
    assert (target_memory / "MEMORY.md").read_text(
        encoding="utf-8"
    ) == "cloud summary\n"
    assert not (target_memory / "local-only.md").exists()
    assert (target_memory / "sessions" / "abc" / "context.md").read_text(
        encoding="utf-8"
    ) == "device local\n"


def test_apply_paths_to_local_restores_only_selected_files(tmp_path: Path):
    payload_dir = tmp_path / "payload"
    source_config = payload_dir / "config"
    target_config = tmp_path / "local" / "config"
    source_config.mkdir(parents=True)
    target_config.mkdir(parents=True)
    (source_config / "providers.json").write_text('{"cloud": true}\n', encoding="utf-8")
    (target_config / "providers.json").write_text('{"local": true}\n', encoding="utf-8")
    (target_config / "other.json").write_text(
        '{"local": "unchanged"}\n', encoding="utf-8"
    )

    builder = SyncPayloadBuilder(
        user_config_dir=target_config,
        user_skills_dir=tmp_path / "local" / "skills",
        sandbox_data_path=tmp_path / "local" / "sandbox",
    )

    restored = builder.apply_paths_to_local(payload_dir, ["config/providers.json"])

    assert restored == ["config/providers.json"]
    assert (target_config / "providers.json").read_text(
        encoding="utf-8"
    ) == '{"cloud": true}\n'
    assert (target_config / "other.json").read_text(
        encoding="utf-8"
    ) == '{"local": "unchanged"}\n'


def test_preview_hashes_preserve_committed_memory_without_copying_payload(
    tmp_path: Path,
):
    payload_dir = tmp_path / "repo" / PAYLOAD_DIR_NAME
    payload_memory = payload_dir / "memory"
    local_config = tmp_path / "local" / "config"
    payload_memory.mkdir(parents=True)
    local_config.mkdir(parents=True)
    (payload_memory / "committed.md").write_text("keep\n", encoding="utf-8")
    (local_config / "default.yaml").write_text("model: local\n", encoding="utf-8")

    builder = SyncPayloadBuilder(
        user_config_dir=local_config,
        user_skills_dir=tmp_path / "local" / "skills",
        sandbox_data_path=tmp_path / "local" / "sandbox",
    )

    hashes = builder.preview_content_hashes(payload_dir)

    assert set(hashes) == {"config/default.yaml", "memory/committed.md"}
    assert (payload_memory / "committed.md").read_text(encoding="utf-8") == "keep\n"
