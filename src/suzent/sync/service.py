from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from suzent.config import get_data_dir
from suzent.logger import get_logger
from suzent.sync.conflicts import SyncConflictResolver
from suzent.sync.models import SecretBundlesFile, SyncManifest, SyncProfile
from suzent.sync.payload import MANIFEST_PATH, PAYLOAD_DIR_NAME, SyncPayloadBuilder
from suzent.sync.provider import GitHubSyncProvider
from suzent.sync.quickstart import (
    DEFAULT_REPO_NAME,
    default_repo_path,
    quickstart_github_sync,
)
from suzent.sync.secrets import SECRET_BUNDLES_PATH, EncryptedSecretSync

logger = get_logger(__name__)


class GitHubSyncService:
    def __init__(
        self,
        *,
        profiles_path: Path | None = None,
        payload_builder: SyncPayloadBuilder | None = None,
    ) -> None:
        # Resolve the config dir at construction time (honors SUZENT_DATA_DIR),
        # not from the module-frozen USER_CONFIG_DIR constant — otherwise a test
        # that sets SUZENT_DATA_DIR after import would still write sync_profiles
        # into the real ~/.suzent/config (this actually happened).
        self.profiles_path = (
            profiles_path or get_data_dir() / "config" / "sync_profiles.json"
        )
        self.payload_builder = payload_builder or SyncPayloadBuilder()
        self.conflict_resolver = SyncConflictResolver()
        self._locks: dict[str, asyncio.Lock] = {}
        self._shibboleth_unlocks: dict[str, str] = {}

    def list_profiles(self) -> list[SyncProfile]:
        return list(self._load_profiles().values())

    def save_profile(self, profile: SyncProfile) -> SyncProfile:
        profiles = self._load_profiles()
        profiles[profile.id] = profile
        self._save_profiles(profiles)
        return profile

    def create_profile(self, profile: SyncProfile) -> SyncProfile:
        return self.save_profile(profile)

    def get_profile(self, profile_id: str | None = None) -> SyncProfile:
        profiles = self._load_profiles()
        if profile_id:
            try:
                return profiles[profile_id]
            except KeyError as exc:
                raise ValueError(f"Unknown sync profile: {profile_id}") from exc
        if not profiles:
            raise ValueError("No sync profile configured")
        return next(iter(profiles.values()))

    def is_shibboleth_unlocked(self, profile_id: str) -> bool:
        return profile_id in self._shibboleth_unlocks

    def lock_shibboleth(self, profile_id: str | None = None) -> None:
        if profile_id:
            self._shibboleth_unlocks.pop(profile_id, None)
            return
        self._shibboleth_unlocks.clear()

    def unlock_shibboleth(self, profile: SyncProfile, shibboleth: str) -> None:
        bundle_path = Path(profile.repo_path) / PAYLOAD_DIR_NAME / SECRET_BUNDLES_PATH
        secret_sync = EncryptedSecretSync()
        if not secret_sync.verify_shibboleth(bundle_path, shibboleth):
            raise ValueError("Incorrect passphrase")
        self._shibboleth_unlocks[profile.id] = shibboleth

    def unlock_mnemonic(self, profile: SyncProfile, mnemonic: str) -> None:
        bundle_path = Path(profile.repo_path) / PAYLOAD_DIR_NAME / SECRET_BUNDLES_PATH
        secret_sync = EncryptedSecretSync()
        payload = secret_sync.read_bundles_file(bundle_path)
        if payload is None or not payload.bundles:
            self._shibboleth_unlocks[profile.id] = mnemonic
            _store_mnemonic_in_keyring(profile.id, mnemonic)
            return
        if payload.format_version != 2:
            # Legacy format_version 1 bundle — accept the mnemonic and migrate on next push
            self._shibboleth_unlocks[profile.id] = mnemonic
            _store_mnemonic_in_keyring(profile.id, mnemonic)
            return
        if not secret_sync.verify_mnemonic(payload, mnemonic):
            raise ValueError("Incorrect mnemonic phrase")
        self._shibboleth_unlocks[profile.id] = mnemonic
        _store_mnemonic_in_keyring(profile.id, mnemonic)

    def enable_mnemonic_secret_sync(
        self, profile: SyncProfile, mnemonic: str
    ) -> tuple[SyncProfile, SecretBundlesFile]:
        from suzent.sync.secrets import EncryptedSecretSync

        bundle_path = Path(profile.repo_path) / PAYLOAD_DIR_NAME / SECRET_BUNDLES_PATH
        secret_sync = EncryptedSecretSync()
        existing = secret_sync.read_bundles_file(bundle_path)
        bundles_file = secret_sync.export_bundles_mnemonic(
            profile, mnemonic, existing_file=existing
        )
        secret_sync.write_bundles_file(bundle_path, bundles_file)
        self._shibboleth_unlocks[profile.id] = mnemonic
        _store_mnemonic_in_keyring(profile.id, mnemonic)
        profile.encrypted_secret_sync_enabled = True
        profile.secret_sync_available = True
        self.save_profile(profile)
        return profile, bundles_file

    def rotate_mnemonic(
        self, profile: SyncProfile, new_mnemonic: str
    ) -> SecretBundlesFile:
        from suzent.sync.secrets import EncryptedSecretSync

        old_mnemonic = self._shibboleth_unlocks.get(profile.id)
        if not old_mnemonic:
            raise ValueError("Session must be unlocked before rotating the mnemonic")
        bundle_path = Path(profile.repo_path) / PAYLOAD_DIR_NAME / SECRET_BUNDLES_PATH
        secret_sync = EncryptedSecretSync()
        existing = secret_sync.read_bundles_file(bundle_path)
        bundles_file = secret_sync.export_bundles_mnemonic(
            profile, new_mnemonic, existing_file=existing
        )
        secret_sync.write_bundles_file(bundle_path, bundles_file)
        self._shibboleth_unlocks[profile.id] = new_mnemonic
        _store_mnemonic_in_keyring(profile.id, new_mnemonic)
        return bundles_file

    async def register_device_mnemonic(
        self, profile: SyncProfile, mnemonic: str
    ) -> None:
        from suzent.sync.secrets import EncryptedSecretSync

        bundle_path = Path(profile.repo_path) / PAYLOAD_DIR_NAME / SECRET_BUNDLES_PATH
        provider = GitHubSyncProvider(
            Path(profile.repo_path), remote=profile.remote, branch=profile.branch
        )
        if not bundle_path.exists():
            # Bundle not local — pull to get it from remote
            await asyncio.to_thread(provider.pull_ff_only)
            await asyncio.to_thread(
                self.payload_builder.apply_to_local,
                Path(profile.repo_path) / PAYLOAD_DIR_NAME,
            )
            await asyncio.to_thread(_reload_runtime)
        secret_sync = EncryptedSecretSync()
        if not bundle_path.exists():
            # Not on remote either — treat as fresh first-time setup
            self.enable_mnemonic_secret_sync(profile, mnemonic)
            return
        updated = await asyncio.to_thread(
            secret_sync.register_device, bundle_path, profile, mnemonic
        )
        secret_sync.write_bundles_file(bundle_path, updated)
        self._shibboleth_unlocks[profile.id] = mnemonic
        _store_mnemonic_in_keyring(profile.id, mnemonic)
        profile.encrypted_secret_sync_enabled = True
        profile.secret_sync_available = True
        self.save_profile(profile)

    def status(self, profile_id: str | None = None) -> dict:
        try:
            profile = self.get_profile(profile_id)
        except ValueError:
            return {"configured": False, "profiles": []}

        # Auto-unlock from OS keyring if not already in memory
        self._try_load_from_keyring(profile)

        payload_dir = Path(profile.repo_path) / PAYLOAD_DIR_NAME
        provider = GitHubSyncProvider(
            Path(profile.repo_path), remote=profile.remote, branch=profile.branch
        )
        validation: dict | None
        try:
            validation = provider.validate(require_clean=False)
        except Exception as exc:
            validation = {"valid": False, "error": str(exc)}

        bundle_path = payload_dir / SECRET_BUNDLES_PATH
        has_secret_bundles = bundle_path.is_file()

        secret_sync = EncryptedSecretSync()
        rotation_info = (
            secret_sync.rotation_detected(bundle_path, profile)
            if has_secret_bundles
            else None
        )
        vault_info = secret_sync.inspect_vault(bundle_path, profile)

        profile_dict = profile.model_dump(mode="json")
        # Derive secret_sync_available from whether the bundle file exists in the
        # local payload dir — the stored flag is excluded from the sync payload so
        # other devices would never see it set to True.
        if has_secret_bundles:
            profile_dict["secret_sync_available"] = True

        return {
            "configured": True,
            "profile": profile_dict,
            "payload_dir": str(payload_dir),
            "payload_hashes": self.payload_builder.content_hashes(payload_dir),
            "forbidden_paths": self.payload_builder.validate_no_forbidden_paths(
                payload_dir
            ),
            "git": validation,
            "requires_shibboleth": profile.encrypted_secret_sync_enabled,
            "shibboleth_unlocked": self.is_shibboleth_unlocked(profile.id),
            "has_secret_bundles": has_secret_bundles,
            "rotation_detected": rotation_info,
            "vault": vault_info,
        }

    def validate(self, profile: SyncProfile) -> dict:
        return GitHubSyncProvider(
            Path(profile.repo_path), remote=profile.remote, branch=profile.branch
        ).validate(require_clean=False)

    def quickstart_info(self) -> dict:
        from suzent.sync.github_api import resolve_github_token

        return {
            "default_repo_path": str(default_repo_path()),
            "default_repo_name": DEFAULT_REPO_NAME,
            "github_authenticated": bool(resolve_github_token()),
        }

    def quickstart(
        self,
        *,
        repo_name: str | None = None,
        repo_path: str | None = None,
        branch: str | None = None,
        remote: str | None = None,
        auto_sync_enabled: bool = True,
        auto_resolve_enabled: bool = True,
        interval_hours: int = 4,
    ) -> dict:
        return quickstart_github_sync(
            repo_name=repo_name or DEFAULT_REPO_NAME,
            repo_path=Path(repo_path) if repo_path else None,
            branch=branch,
            remote=remote or "origin",
            auto_sync_enabled=auto_sync_enabled,
            auto_resolve_enabled=auto_resolve_enabled,
            interval_hours=interval_hours,
        )

    def preview_pull(self, profile_id: str | None = None) -> dict:
        profile = self.get_profile(profile_id)
        provider = GitHubSyncProvider(
            Path(profile.repo_path), remote=profile.remote, branch=profile.branch
        )
        result = provider.preview_pull()
        payload_dir = Path(profile.repo_path) / PAYLOAD_DIR_NAME
        result["payload_hashes"] = self.payload_builder.content_hashes(payload_dir)
        return result

    async def pull(
        self, profile_id: str | None = None, *, shibboleth: str | None = None
    ) -> dict:
        profile = self.get_profile(profile_id)
        async with self._lock(profile):
            provider = GitHubSyncProvider(
                Path(profile.repo_path), remote=profile.remote, branch=profile.branch
            )
            git_output = await asyncio.to_thread(provider.pull_ff_only)
            payload_dir = Path(profile.repo_path) / PAYLOAD_DIR_NAME
            phrase = self._require_shibboleth_for_pull(profile, payload_dir, shibboleth)
            restored = await asyncio.to_thread(
                self.payload_builder.apply_to_local, payload_dir
            )
            imported_keys: list[str] = []
            changed_keys: list[str] = []
            if phrase:
                # Compute which local key VALUES the vault will overwrite, before
                # applying — so the UI can report "N keys changed from vault".
                changed_keys = await asyncio.to_thread(
                    self._secret_overwrite_diff,
                    payload_dir,
                    phrase,
                    profile.synced_keys,
                )
                imported_keys = await asyncio.to_thread(
                    self._import_secret_bundles,
                    payload_dir,
                    phrase,
                    only_keys=profile.synced_keys,
                )
                if imported_keys and not profile.encrypted_secret_sync_enabled:
                    profile.encrypted_secret_sync_enabled = True
                    profile.secret_sync_available = True
                    self.save_profile(profile)
            await asyncio.to_thread(_reload_runtime)
            return {
                "success": True,
                "git": git_output,
                "restored": restored,
                "imported_secret_keys": imported_keys,
                "changed_secret_keys": changed_keys,
            }

    async def push(
        self, profile_id: str | None = None, *, shibboleth: str | None = None
    ) -> dict:
        profile = self.get_profile(profile_id)
        async with self._lock(profile):
            repo_path = Path(profile.repo_path)
            manifest = await asyncio.to_thread(
                self.payload_builder.build, repo_path, profile
            )
            payload_dir = repo_path / PAYLOAD_DIR_NAME
            if profile.encrypted_secret_sync_enabled:
                # Raises if locked — never a false success. This is the fix for the
                # class of bug where a push reported success while the secret vault
                # was left untouched (locked / not exporting).
                phrase = self._require_shibboleth(profile, shibboleth)
                manifest = await asyncio.to_thread(
                    self._write_secret_bundles,
                    repo_path,
                    profile,
                    manifest.revision_id,
                    phrase,
                )
                secrets_status = "pushed"
            elif self._has_secret_bundles(payload_dir):
                # A vault exists but this device isn't set up to contribute keys to
                # it. Push the rest, but tell the caller loudly so the UI doesn't
                # imply the vault was updated.
                logger.warning(
                    "Push: a secret vault exists but encrypted secret sync is not "
                    "enabled on this device — API keys were NOT pushed."
                )
                secrets_status = "skipped_not_enabled"
            else:
                secrets_status = "none"

            forbidden = self.payload_builder.validate_no_forbidden_paths(payload_dir)
            if forbidden:
                raise ValueError(f"Sync payload contains forbidden paths: {forbidden}")

            provider = GitHubSyncProvider(
                repo_path, remote=profile.remote, branch=profile.branch
            )
            git_output = await asyncio.to_thread(
                provider.commit_and_push_payload, manifest.revision_id
            )
            profile.last_revision = manifest.revision_id
            profile.last_sync_at = manifest.created_at
            self.save_profile(profile)
            return {
                "success": True,
                "git": git_output,
                "manifest": manifest.model_dump(mode="json"),
                "secrets": secrets_status,
            }

    async def auto_sync(
        self, profile_id: str | None = None, *, shibboleth: str | None = None
    ) -> dict:
        profile = self.get_profile(profile_id)
        async with self._lock(profile):
            repo_path = Path(profile.repo_path)
            payload_dir = repo_path / PAYLOAD_DIR_NAME
            provider = GitHubSyncProvider(
                repo_path, remote=profile.remote, branch=profile.branch
            )
            phrase = self._optional_shibboleth(profile, shibboleth)

            manifest = await asyncio.to_thread(
                self.payload_builder.build, repo_path, profile
            )
            if profile.encrypted_secret_sync_enabled:
                if phrase:
                    manifest = await asyncio.to_thread(
                        self._write_secret_bundles,
                        repo_path,
                        profile,
                        manifest.revision_id,
                        phrase,
                    )
                else:
                    logger.warning(
                        "Skipping Shibboleth secret export on auto-sync: not unlocked"
                    )

            forbidden = self.payload_builder.validate_no_forbidden_paths(payload_dir)
            if forbidden:
                raise ValueError(f"Sync payload contains forbidden paths: {forbidden}")

            restored: list[str] = []
            imported: list[str] = []
            local_payload_changed = await asyncio.to_thread(
                provider.has_meaningful_payload_changes
            )

            if local_payload_changed:
                with tempfile.TemporaryDirectory() as temp_dir:
                    snapshot_dir = Path(temp_dir) / PAYLOAD_DIR_NAME
                    await asyncio.to_thread(shutil.copytree, payload_dir, snapshot_dir)
                    await asyncio.to_thread(provider.pull_ff_only)
                    await asyncio.to_thread(_replace_tree, snapshot_dir, payload_dir)
                git_output = await asyncio.to_thread(
                    provider.commit_and_push_payload, manifest.revision_id
                )
            else:
                git_output = "No sync payload changes to push."
                await asyncio.to_thread(provider.pull_ff_only)
                restored = await asyncio.to_thread(
                    self.payload_builder.apply_to_local, payload_dir
                )
                await asyncio.to_thread(_reload_runtime)

                has_bundles = self._has_secret_bundles(payload_dir)
                if profile.encrypted_secret_sync_enabled or has_bundles:
                    if phrase:
                        imported = await asyncio.to_thread(
                            self._import_secret_bundles,
                            payload_dir,
                            phrase,
                            only_keys=profile.synced_keys,
                        )
                        if imported and not profile.encrypted_secret_sync_enabled:
                            profile.encrypted_secret_sync_enabled = True
                            profile.secret_sync_available = True
                    else:
                        logger.warning(
                            "Skipping Shibboleth secret import on auto-sync: not unlocked"
                        )

            profile.last_revision = manifest.revision_id
            profile.last_sync_at = manifest.created_at
            self.save_profile(profile)
            return {
                "success": True,
                "git": git_output,
                "restored": restored,
                "imported_secret_keys": imported,
                "manifest": manifest.model_dump(mode="json"),
            }

    def stop_conflict_resolution(self) -> dict:
        self.conflict_resolver.reset()
        return {"success": True}

    def _lock(self, profile: SyncProfile) -> asyncio.Lock:
        if profile.id not in self._locks:
            self._locks[profile.id] = asyncio.Lock()
        return self._locks[profile.id]

    def _require_shibboleth(self, profile: SyncProfile, explicit: str | None) -> str:
        if explicit:
            return explicit
        cached = self._try_load_from_keyring(profile)
        if cached:
            return cached
        raise ValueError(
            "Shibboleth (passphrase) required. Unlock in Settings → Data before sync."
        )

    def _optional_shibboleth(
        self, profile: SyncProfile, explicit: str | None
    ) -> str | None:
        if explicit:
            return explicit
        return self._try_load_from_keyring(profile)

    def _try_load_from_keyring(self, profile: SyncProfile) -> str | None:
        """Return the cached mnemonic, loading from the OS keyring if not yet in memory.

        Tries the keyring unconditionally — the second device may have registered
        its mnemonic before encrypted_secret_sync_enabled was set on its local profile.
        """
        cached = self._shibboleth_unlocks.get(profile.id)
        if cached:
            return cached
        stored = _load_mnemonic_from_keyring(profile.id)
        if stored:
            self._shibboleth_unlocks[profile.id] = stored
            return stored
        return None

    def _require_shibboleth_for_pull(
        self, profile: SyncProfile, payload_dir: Path, explicit: str | None
    ) -> str | None:
        if not profile.encrypted_secret_sync_enabled and not self._has_secret_bundles(
            payload_dir
        ):
            return None
        return self._require_shibboleth(profile, explicit)

    def _write_secret_bundles(
        self,
        repo_path: Path,
        profile: SyncProfile,
        revision_id: str,
        shibboleth: str,
    ) -> SyncManifest:
        payload_dir = repo_path / PAYLOAD_DIR_NAME
        bundle_path = payload_dir / SECRET_BUNDLES_PATH
        secret_sync = EncryptedSecretSync()
        existing = secret_sync.read_bundles_file(bundle_path)
        bundles_file = secret_sync.export_bundles_mnemonic(
            profile,
            shibboleth,
            keys=profile.synced_keys,
            existing_file=existing
            if existing and existing.format_version == 2
            else None,
        )
        secret_sync.write_bundles_file(bundle_path, bundles_file)

        hashes = self.payload_builder.content_hashes(payload_dir)
        manifest = SyncManifest(
            revision_id=revision_id,
            source_device=profile.device_id,
            included_paths=sorted(hashes),
            content_hashes=hashes,
        )
        (payload_dir / MANIFEST_PATH).write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return manifest

    def _secret_overwrite_diff(
        self,
        payload_dir: Path,
        shibboleth: str,
        only_keys: list[str] | None,
    ) -> list[str]:
        bundle_path = payload_dir / SECRET_BUNDLES_PATH
        secret_sync = EncryptedSecretSync()
        payload = secret_sync.read_bundles_file(bundle_path)
        if payload is None or not payload.bundles or payload.format_version != 2:
            return []
        return secret_sync.overwrite_diff_mnemonic(
            payload, shibboleth, only_keys=only_keys
        )

    def _import_secret_bundles(
        self,
        payload_dir: Path,
        shibboleth: str,
        *,
        only_keys: list[str] | None = None,
    ) -> list[str]:
        bundle_path = payload_dir / SECRET_BUNDLES_PATH
        secret_sync = EncryptedSecretSync()
        payload = secret_sync.read_bundles_file(bundle_path)
        if payload is None or not payload.bundles:
            return []
        if payload.format_version == 2:
            return secret_sync.import_bundles_mnemonic(
                payload, shibboleth, only_keys=only_keys
            )
        if not secret_sync.verify_shibboleth(bundle_path, shibboleth):
            raise ValueError("Incorrect Shibboleth (passphrase)")
        return secret_sync.import_bundles(payload, shibboleth)

    def _has_secret_bundles(self, payload_dir: Path) -> bool:
        bundle_path = payload_dir / SECRET_BUNDLES_PATH
        payload = EncryptedSecretSync().read_bundles_file(bundle_path)
        return bool(payload and payload.bundles)

    def _load_profiles(self) -> dict[str, SyncProfile]:
        if not self.profiles_path.exists():
            return {}
        data = json.loads(self.profiles_path.read_text(encoding="utf-8"))
        profiles = data.get("profiles", [])
        loaded = {item["id"]: SyncProfile.model_validate(item) for item in profiles}
        if self._heal_repo_paths(loaded):
            self._save_profiles(loaded)
        return loaded

    def _heal_repo_paths(self, profiles: dict[str, SyncProfile]) -> bool:
        """Self-heal profiles whose repo_path no longer points at a git repo.

        A stray path (e.g. a pytest temp dir that leaked into a real profile, or
        a repo moved/deleted) breaks every sync op with "not a Git repository".
        If the canonical <data_dir>/github-sync is a valid repo, redirect there
        and persist. Returns True if any profile was changed.
        """
        from suzent.config import get_data_dir

        canonical = get_data_dir() / "github-sync"
        canonical_ok = (canonical / ".git").is_dir()
        changed = False
        for prof in profiles.values():
            if (Path(prof.repo_path) / ".git").is_dir():
                continue  # healthy
            if canonical_ok and Path(prof.repo_path) != canonical:
                logger.warning(
                    "Sync profile %s had a stale repo_path (%s); redirecting to %s",
                    prof.id,
                    prof.repo_path,
                    canonical,
                )
                prof.repo_path = str(canonical)
                changed = True
            else:
                logger.warning(
                    "Sync profile %s points at a missing repo (%s) and no "
                    "canonical repo exists — sync will fail until reconfigured.",
                    prof.id,
                    prof.repo_path,
                )
        return changed

    def _save_profiles(self, profiles: dict[str, SyncProfile]) -> None:
        self.profiles_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "profiles": [
                profile.model_dump(mode="json")
                for profile in sorted(profiles.values(), key=lambda p: p.id)
            ]
        }
        self.profiles_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )


def _reload_runtime() -> None:
    """Reload config and skills from disk after a pull so changes take effect immediately."""
    try:
        from suzent.config import CONFIG

        CONFIG.reload()
    except Exception:
        pass
    try:
        from suzent.skills.manager import get_skill_manager

        get_skill_manager().reload()
    except Exception:
        pass


def _replace_tree(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


_KEYRING_SERVICE = "suzent-sync-mnemonic"


def _store_mnemonic_in_keyring(profile_id: str, mnemonic: str) -> None:
    try:
        import keyring

        keyring.set_password(_KEYRING_SERVICE, profile_id, mnemonic)
    except Exception:
        pass  # keyring unavailable — user will be prompted on next session


def _load_mnemonic_from_keyring(profile_id: str) -> str | None:
    try:
        import keyring

        return keyring.get_password(_KEYRING_SERVICE, profile_id)
    except Exception:
        return None


def _clear_mnemonic_from_keyring(profile_id: str) -> None:
    try:
        import keyring

        keyring.delete_password(_KEYRING_SERVICE, profile_id)
    except Exception:
        pass
