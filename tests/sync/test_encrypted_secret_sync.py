from pathlib import Path

import pytest

from suzent.sync.models import SyncProfile
from suzent.sync.payload import PAYLOAD_DIR_NAME, SyncPayloadBuilder
from suzent.sync.secrets import EncryptedSecretSync, SECRET_BUNDLES_PATH
from suzent.sync import service as sync_service
from suzent.sync.service import GitHubSyncService

SHIBBOLETH = "my-shibboleth-phrase"
# Valid BIP39 12-word mnemonic for tests that use the mnemonic (format_version 2) API
TEST_MNEMONIC = (
    "monkey hazard provide target lazy fine peace danger asthma noodle annual game"
)


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


def test_inspect_vault_reports_key_diff_and_devices(tmp_path: Path):
    # Exporting device has two keys; write a mnemonic (v2) bundle for them.
    manager = FakeSecretManager()
    manager.values = {"OPENAI_API_KEY": "sk-a", "DEEPSEEK_API_KEY": "sk-b"}
    sync = EncryptedSecretSync(secret_manager=manager)
    profile = SyncProfile(repo_path=str(tmp_path), encrypted_secret_sync_enabled=True)
    bundle_path = tmp_path / PAYLOAD_DIR_NAME / SECRET_BUNDLES_PATH
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundles_file = sync.export_bundles_mnemonic(profile, TEST_MNEMONIC)
    sync.write_bundles_file(bundle_path, bundles_file)

    # A different device inspecting: it holds GEMINI locally (not in vault) and is
    # missing DEEPSEEK (in vault, not local). This is exactly the diff the UI needs.
    other = FakeSecretManager()
    other.values = {"OPENAI_API_KEY": "sk-a", "GEMINI_API_KEY": "sk-g"}
    other_sync = EncryptedSecretSync(secret_manager=other)
    other_profile = SyncProfile(
        repo_path=str(tmp_path), encrypted_secret_sync_enabled=True
    )

    info = other_sync.inspect_vault(bundle_path, other_profile)

    assert info["exists"] is True
    assert set(info["vault_keys"]) == {"OPENAI_API_KEY", "DEEPSEEK_API_KEY"}
    assert info["local_only_keys"] == ["GEMINI_API_KEY"]
    assert info["vault_only_keys"] == ["DEEPSEEK_API_KEY"]
    assert info["this_device_enrolled"] is False  # other device never wrote it
    assert info["mnemonic_version"] >= 1


def test_export_merges_other_devices_keys_on_subset_push(tmp_path: Path):
    # Device A writes the vault with KEY_A. Device B, syncing only KEY_B, pushes —
    # the vault must KEEP KEY_A (merge) and still be decryptable for both.
    a = FakeSecretManager()
    a.values = {"KEY_A": "val-a"}
    sync_a = EncryptedSecretSync(secret_manager=a)
    profile_a = SyncProfile(repo_path=str(tmp_path), encrypted_secret_sync_enabled=True)
    bundle_path = tmp_path / "bundles.json"
    v1 = sync_a.export_bundles_mnemonic(profile_a, TEST_MNEMONIC, keys=["KEY_A"])
    sync_a.write_bundles_file(bundle_path, v1)

    b = FakeSecretManager()
    b.values = {"KEY_B": "val-b"}
    sync_b = EncryptedSecretSync(secret_manager=b)
    profile_b = SyncProfile(repo_path=str(tmp_path), encrypted_secret_sync_enabled=True)
    existing = sync_b.read_bundles_file(bundle_path)
    v2 = sync_b.export_bundles_mnemonic(
        profile_b, TEST_MNEMONIC, keys=["KEY_B"], existing_file=existing
    )

    names = {bundle.key_name for bundle in v2.bundles}
    assert names == {"KEY_A", "KEY_B"}  # KEY_A preserved via merge
    # And both decrypt with the same phrase.
    target = FakeSecretManager()
    target.values = {}
    imported = EncryptedSecretSync(secret_manager=target).import_bundles_mnemonic(
        v2, TEST_MNEMONIC
    )
    assert set(imported) == {"KEY_A", "KEY_B"}
    assert target.values["KEY_A"] == "val-a"
    assert target.values["KEY_B"] == "val-b"


def test_import_respects_only_keys_opt_in(tmp_path: Path):
    src = FakeSecretManager()
    src.values = {"KEY_A": "val-a", "KEY_B": "val-b"}
    sync = EncryptedSecretSync(secret_manager=src)
    profile = SyncProfile(repo_path=str(tmp_path), encrypted_secret_sync_enabled=True)
    bundles = sync.export_bundles_mnemonic(profile, TEST_MNEMONIC)

    target = FakeSecretManager()
    target.values = {}
    imported = EncryptedSecretSync(secret_manager=target).import_bundles_mnemonic(
        bundles, TEST_MNEMONIC, only_keys=["KEY_A"]
    )
    assert imported == ["KEY_A"]
    assert "KEY_B" not in target.values  # opted out — left untouched


def test_overwrite_diff_reports_only_changed(tmp_path: Path):
    src = FakeSecretManager()
    src.values = {"KEY_A": "new", "KEY_B": "same"}
    sync = EncryptedSecretSync(secret_manager=src)
    profile = SyncProfile(repo_path=str(tmp_path), encrypted_secret_sync_enabled=True)
    bundles = sync.export_bundles_mnemonic(profile, TEST_MNEMONIC)

    local = FakeSecretManager()
    local.values = {"KEY_A": "old", "KEY_B": "same"}  # A differs, B identical
    diff = EncryptedSecretSync(secret_manager=local).overwrite_diff_mnemonic(
        bundles, TEST_MNEMONIC
    )
    assert diff == ["KEY_A"]


def test_export_stamps_per_key_writer_metadata(tmp_path: Path):
    manager = FakeSecretManager()
    manager.values = {"OPENAI_API_KEY": "sk-a"}
    sync = EncryptedSecretSync(secret_manager=manager)
    profile = SyncProfile(repo_path=str(tmp_path), encrypted_secret_sync_enabled=True)
    bundles = sync.export_bundles_mnemonic(profile, TEST_MNEMONIC)
    meta = bundles.bundles[0].metadata
    assert meta.get("written_by")  # device name stamped
    assert meta.get("written_at")  # timestamp stamped

    # And inspect_vault surfaces it per key.
    bundle_path = tmp_path / PAYLOAD_DIR_NAME / SECRET_BUNDLES_PATH
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    sync.write_bundles_file(bundle_path, bundles)
    info = sync.inspect_vault(bundle_path, profile)
    assert info["key_meta"]["OPENAI_API_KEY"]["written_by"] == meta["written_by"]


def test_remove_keys_from_vault(tmp_path: Path):
    manager = FakeSecretManager()
    manager.values = {"MIMO_API_KEY": "x", "OPENAI_API_KEY": "y"}
    sync = EncryptedSecretSync(secret_manager=manager)
    profile = SyncProfile(repo_path=str(tmp_path), encrypted_secret_sync_enabled=True)
    bundle_path = tmp_path / "bundles.json"
    sync.write_bundles_file(
        bundle_path, sync.export_bundles_mnemonic(profile, TEST_MNEMONIC)
    )

    updated, removed = sync.remove_keys_from_vault(
        bundle_path, profile, ["MIMO_API_KEY"]
    )
    assert removed == ["MIMO_API_KEY"]
    assert {b.key_name for b in updated.bundles} == {"OPENAI_API_KEY"}
    assert updated.rotated_by == profile.device_id


def test_inspect_vault_when_no_bundle(tmp_path: Path):
    manager = FakeSecretManager()
    sync = EncryptedSecretSync(secret_manager=manager)
    profile = SyncProfile(repo_path=str(tmp_path))
    info = sync.inspect_vault(tmp_path / "nope.json", profile)
    assert info["exists"] is False
    assert info["vault_keys"] == []
    assert info["local_only_keys"] == ["OPENAI_API_KEY"]


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
        def export_bundles_mnemonic(
            self, profile: SyncProfile, mnemonic: str, **kwargs
        ):
            sync = EncryptedSecretSync(
                secret_manager=FakeSecretManager(),
            )
            return sync.export_bundles_mnemonic(profile, mnemonic, **kwargs)

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

    manifest = service._write_secret_bundles(repo, profile, "rev", TEST_MNEMONIC)

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

    builder = SyncPayloadBuilder(
        user_config_dir=config_dir, user_skills_dir=tmp_path / "skills"
    )
    builder.build(repo, SyncProfile(repo_path=str(repo)))

    payload_dir = repo / PAYLOAD_DIR_NAME
    assert not (payload_dir / "config" / "sync_secret.key").exists()
    assert not builder.validate_no_forbidden_paths(payload_dir)


def test_pull_requires_shibboleth_when_remote_has_secret_bundles(tmp_path: Path):
    repo = tmp_path / "repo"
    payload_dir = repo / PAYLOAD_DIR_NAME
    payload_dir.mkdir(parents=True)
    sync = EncryptedSecretSync(secret_manager=FakeSecretManager())
    profile = SyncProfile(repo_path=str(repo), encrypted_secret_sync_enabled=True)
    bundles_file = sync.export_bundles(profile, SHIBBOLETH)
    sync.write_bundles_file(payload_dir / SECRET_BUNDLES_PATH, bundles_file)

    service = GitHubSyncService(profiles_path=tmp_path / "profiles.json")
    fresh_profile = SyncProfile(
        repo_path=str(repo), encrypted_secret_sync_enabled=False
    )

    with pytest.raises(ValueError, match="Shibboleth"):
        service._require_shibboleth_for_pull(fresh_profile, payload_dir, None)


def test_shibboleth_too_short_raises(tmp_path: Path):
    sync = EncryptedSecretSync(secret_manager=FakeSecretManager())
    profile = SyncProfile(
        repo_path=str(tmp_path),
        encrypted_secret_sync_enabled=True,
    )
    with pytest.raises(ValueError, match="at least"):
        sync.export_bundles(profile, "short")
