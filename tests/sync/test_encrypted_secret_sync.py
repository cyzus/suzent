from pathlib import Path

import pytest

from suzent.sync.models import SyncProfile
from suzent.sync.payload import PAYLOAD_DIR_NAME, SyncPayloadBuilder
from suzent.sync.secrets import EncryptedSecretSync, SECRET_BUNDLES_PATH
from suzent.sync import service as sync_service
from suzent.sync.service import GitHubSyncService

SHIBBOLETH = "my-shibboleth-phrase"


class FakeSecretManager:
    backend_name = "fake"

    def __init__(self) -> None:
        self.values = {"OPENAI_API_KEY": "sk-plaintext-value"}

    def list_keys(self) -> list[str]:
        return list(self.values)

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value


def test_encrypted_secret_bundles_do_not_contain_plaintext(tmp_path: Path):
    manager = FakeSecretManager()
    sync = EncryptedSecretSync(secret_manager=manager)
    profile = SyncProfile(
        repo_path=str(tmp_path),
        encrypted_secret_sync_enabled=True,
    )

    bundles_file = sync.export_bundles(profile, SHIBBOLETH)

    assert len(bundles_file.bundles) == 1
    assert bundles_file.bundles[0].key_name == "OPENAI_API_KEY"
    assert "sk-plaintext-value" not in bundles_file.bundles[0].ciphertext
    assert bundles_file.kdf.salt


def test_second_device_imports_with_same_shibboleth(tmp_path: Path):
    manager = FakeSecretManager()
    sync = EncryptedSecretSync(secret_manager=manager)
    profile = SyncProfile(
        repo_path=str(tmp_path),
        encrypted_secret_sync_enabled=True,
    )
    bundles_file = sync.export_bundles(profile, SHIBBOLETH)

    target_manager = FakeSecretManager()
    target_manager.values = {}
    target_sync = EncryptedSecretSync(secret_manager=target_manager)

    imported = target_sync.import_bundles(bundles_file, SHIBBOLETH)

    assert imported == ["OPENAI_API_KEY"]
    assert target_manager.values["OPENAI_API_KEY"] == "sk-plaintext-value"


def test_wrong_shibboleth_fails_verification(tmp_path: Path):
    manager = FakeSecretManager()
    sync = EncryptedSecretSync(secret_manager=manager)
    profile = SyncProfile(
        repo_path=str(tmp_path),
        encrypted_secret_sync_enabled=True,
    )
    bundles_file = sync.export_bundles(profile, SHIBBOLETH)
    bundle_path = tmp_path / "bundles.json"
    sync.write_bundles_file(bundle_path, bundles_file)

    assert not sync.verify_shibboleth(bundle_path, "wrong-passphrase-xx")


def test_secret_sync_payload_file_contains_only_ciphertext(monkeypatch, tmp_path: Path):
    class FakeEncryptedSecretSync:
        def export_bundles(self, profile: SyncProfile, shibboleth: str, **kwargs):
            sync = EncryptedSecretSync(
                secret_manager=FakeSecretManager(),
            )
            return sync.export_bundles(profile, shibboleth, **kwargs)

        def read_bundles_file(self, bundle_path: Path):
            sync = EncryptedSecretSync(secret_manager=FakeSecretManager())
            return sync.read_bundles_file(bundle_path)

        def write_bundles_file(self, bundle_path: Path, payload):
            sync = EncryptedSecretSync(secret_manager=FakeSecretManager())
            sync.write_bundles_file(bundle_path, payload)

    monkeypatch.setattr(sync_service, "EncryptedSecretSync", FakeEncryptedSecretSync)
    repo = tmp_path / "repo"
    repo.mkdir()
    config_dir = tmp_path / "config"
    skills_dir = tmp_path / "skills"
    sandbox_dir = tmp_path / "sandbox"
    config_dir.mkdir()
    skills_dir.mkdir()
    (sandbox_dir / "shared" / "memory").mkdir(parents=True)
    builder = SyncPayloadBuilder(
        user_config_dir=config_dir,
        user_skills_dir=skills_dir,
        sandbox_data_path=sandbox_dir,
    )
    service = GitHubSyncService(
        profiles_path=tmp_path / "profiles.json",
        payload_builder=builder,
    )
    profile = SyncProfile(
        repo_path=str(repo),
        encrypted_secret_sync_enabled=True,
    )
    builder.build(repo, profile)

    manifest = service._write_secret_bundles(repo, profile, "rev", SHIBBOLETH)

    bundle_file = repo / PAYLOAD_DIR_NAME / SECRET_BUNDLES_PATH
    content = bundle_file.read_text(encoding="utf-8")
    assert SECRET_BUNDLES_PATH in manifest.included_paths
    assert "sk-plaintext-value" not in content
    assert "ciphertext" in content
    assert "kdf" in content


def test_sync_secret_key_is_never_in_payload(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text("ok", encoding="utf-8")
    (config_dir / "sync_secret.key").write_bytes(b"legacy-local-key-material")
    repo = tmp_path / "repo"
    repo.mkdir()

    builder = SyncPayloadBuilder(user_config_dir=config_dir, user_skills_dir=tmp_path / "skills")
    builder.build(repo, SyncProfile(repo_path=str(repo)))

    payload_dir = repo / PAYLOAD_DIR_NAME
    assert not (payload_dir / "config" / "sync_secret.key").exists()
    assert not builder.validate_no_forbidden_paths(payload_dir)


def test_shibboleth_too_short_raises(tmp_path: Path):
    sync = EncryptedSecretSync(secret_manager=FakeSecretManager())
    profile = SyncProfile(
        repo_path=str(tmp_path),
        encrypted_secret_sync_enabled=True,
    )
    with pytest.raises(ValueError, match="at least"):
        sync.export_bundles(profile, "short")
