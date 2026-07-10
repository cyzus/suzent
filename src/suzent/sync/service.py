from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from suzent.config import get_data_dir
from suzent.logger import get_logger
from suzent.sync.conflicts import SyncConflictResolver
from suzent.sync.models import (
    SecretBundlesFile,
    SyncFileChange,
    SyncManifest,
    SyncPlan,
    SyncProfile,
)
from suzent.sync.payload import MANIFEST_PATH, PAYLOAD_DIR_NAME, SyncPayloadBuilder
from suzent.sync.provider import GitHubSyncProvider
from suzent.sync.quickstart import (
    DEFAULT_REPO_NAME,
    default_repo_path,
    quickstart_github_sync,
)
from suzent.sync.secrets import SECRET_BUNDLES_PATH, EncryptedSecretSync

logger = get_logger(__name__)


class DestructiveSyncPlanError(ValueError):
    def __init__(self, plan: SyncPlan) -> None:
        super().__init__("Sync requires confirmation before destructive changes")
        self.plan = plan


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

    def remove_vault_keys(self, profile: SyncProfile, keys: list[str]) -> list[str]:
        """Remove keys from the shared vault bundle and drop them from local sync
        selection. Requires an unlocked session (it mutates the vault). The caller
        should Push afterwards to propagate the removal to other devices."""
        from suzent.sync.secrets import EncryptedSecretSync

        if not self._try_load_from_keyring(profile):
            raise ValueError("Unlock the vault before removing keys")
        bundle_path = Path(profile.repo_path) / PAYLOAD_DIR_NAME / SECRET_BUNDLES_PATH
        secret_sync = EncryptedSecretSync()
        updated, removed = secret_sync.remove_keys_from_vault(
            bundle_path, profile, keys
        )
        secret_sync.write_bundles_file(bundle_path, updated)
        # Also drop removed keys from this device's sync selection so they don't get
        # re-pushed on the next sync.
        if profile.synced_keys is not None:
            profile.synced_keys = [k for k in profile.synced_keys if k not in removed]
            self.save_profile(profile)
        return removed

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

    def preview_sync_plan(
        self,
        operation: str,
        profile_id: str | None = None,
    ) -> SyncPlan:
        if operation not in {"push", "pull", "auto"}:
            raise ValueError(f"Unknown sync operation: {operation}")
        profile = self.get_profile(profile_id)
        repo_path = Path(profile.repo_path)
        provider = GitHubSyncProvider(
            repo_path, remote=profile.remote, branch=profile.branch
        )

        if operation in {"push", "auto"}:
            self.payload_builder.build(repo_path, profile)
            status = provider.payload_status()
            plan = _plan_from_status(operation, status)
            _attach_diff_previews(plan, provider.payload_worktree_diff_patch())
            _attach_added_file_previews(plan, repo_path)
            if operation == "auto":
                incoming = _incoming_tracking_plan(provider, profile, "auto")
                plan = _merge_plans("auto", [plan, incoming])
            return plan

        preview = provider.preview_pull()
        remote_ref = f"{profile.remote}/{profile.branch}"
        diff = provider.payload_diff_name_status("HEAD", remote_ref)
        plan = _plan_from_name_status("pull", diff)
        _attach_diff_previews(plan, provider.payload_diff_patch("HEAD", remote_ref))
        behind = int(preview.get("behind") or 0)
        if behind and not plan.files:
            plan.warnings.append(f"{behind} remote commit(s) have no payload changes.")
        return plan

    async def pull(
        self,
        profile_id: str | None = None,
        *,
        shibboleth: str | None = None,
        confirm_destructive: bool = False,
        prefer_cloud: bool = False,
        paths: list[str] | None = None,
    ) -> dict:
        profile = self.get_profile(profile_id)
        async with self._lock(profile):
            provider = GitHubSyncProvider(
                Path(profile.repo_path), remote=profile.remote, branch=profile.branch
            )
            plan = await asyncio.to_thread(self.preview_sync_plan, "pull", profile.id)
            if plan.requires_confirmation and not confirm_destructive:
                raise DestructiveSyncPlanError(plan)
            git_output = await asyncio.to_thread(provider.pull_ff_only)
            payload_dir = Path(profile.repo_path) / PAYLOAD_DIR_NAME
            phrase = self._require_shibboleth_for_pull(profile, payload_dir, shibboleth)
            if paths:
                restored = await asyncio.to_thread(
                    self.payload_builder.apply_paths_to_local,
                    payload_dir,
                    paths,
                )
            else:
                restored = await asyncio.to_thread(
                    self.payload_builder.apply_to_local,
                    payload_dir,
                    replace_memory=prefer_cloud,
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
                "prefer_cloud": prefer_cloud,
                "paths": paths or [],
            }

    async def discard_outgoing(
        self, profile_id: str | None = None, *, paths: list[str] | None = None
    ) -> dict:
        profile = self.get_profile(profile_id)
        async with self._lock(profile):
            repo_path = Path(profile.repo_path)
            provider = GitHubSyncProvider(
                repo_path, remote=profile.remote, branch=profile.branch
            )
            plan = await asyncio.to_thread(self.preview_sync_plan, "push", profile.id)
            outgoing = [
                change for change in plan.files if change.direction == "outgoing"
            ]
            allowed_paths = {change.path for change in outgoing}
            selected_paths = [
                path
                for path in (paths or sorted(allowed_paths))
                if path in allowed_paths
            ]
            if paths and len(selected_paths) != len(paths):
                unknown = sorted(set(paths) - allowed_paths)
                raise ValueError(f"Unknown outgoing sync path(s): {', '.join(unknown)}")
            if selected_paths:
                await asyncio.to_thread(provider.discard_payload_paths, selected_paths)
            payload_dir = repo_path / PAYLOAD_DIR_NAME
            restored = await asyncio.to_thread(
                self.payload_builder.apply_paths_to_local,
                payload_dir,
                selected_paths,
            )
            await asyncio.to_thread(_reload_runtime)
            return {
                "success": True,
                "discarded": selected_paths,
                "restored": restored,
                "plan": plan.model_dump(mode="json"),
            }

    async def push(
        self,
        profile_id: str | None = None,
        *,
        shibboleth: str | None = None,
        confirm_destructive: bool = False,
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
            plan = _plan_from_status("push", provider.payload_status())
            _attach_diff_previews(plan, provider.payload_worktree_diff_patch())
            _attach_added_file_previews(plan, repo_path)
            if plan.requires_confirmation and not confirm_destructive:
                raise DestructiveSyncPlanError(plan)
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
        self,
        profile_id: str | None = None,
        *,
        shibboleth: str | None = None,
        confirm_destructive: bool = False,
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

            plan = _plan_from_status("auto", provider.payload_status())
            _attach_diff_previews(plan, provider.payload_worktree_diff_patch())
            _attach_added_file_previews(plan, repo_path)
            incoming = _incoming_tracking_plan(provider, profile, "auto")
            plan = _merge_plans("auto", [plan, incoming])
            if plan.requires_confirmation and not confirm_destructive:
                return {
                    "success": False,
                    "blocked_review_required": True,
                    "plan": plan.model_dump(mode="json"),
                }

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


def _plan_from_status(operation: str, porcelain_output: str) -> SyncPlan:
    changes: list[SyncFileChange] = []
    for line in porcelain_output.splitlines():
        if not line.strip():
            continue
        status = line[:2]
        path = _status_path(line).removeprefix(f"{PAYLOAD_DIR_NAME}/")
        changes.append(_make_change(path, _change_type_from_status(status), "outgoing"))
    return _finalize_plan(operation, changes)


def _plan_from_name_status(operation: str, diff_output: str) -> SyncPlan:
    changes: list[SyncFileChange] = []
    for line in diff_output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        path = parts[-1].replace("\\", "/").removeprefix(f"{PAYLOAD_DIR_NAME}/")
        changes.append(
            _make_change(path, _change_type_from_name_status(status), "incoming")
        )
    return _finalize_plan(operation, changes)


def _merge_plans(operation: str, plans: list[SyncPlan]) -> SyncPlan:
    changes: list[SyncFileChange] = []
    warnings: list[str] = []
    for plan in plans:
        changes.extend(plan.files)
        warnings.extend(plan.warnings)
    merged = _finalize_plan(operation, changes)
    merged.warnings = list(dict.fromkeys([*merged.warnings, *warnings]))
    return merged


def _incoming_tracking_plan(
    provider: GitHubSyncProvider,
    profile: SyncProfile,
    operation: str,
) -> SyncPlan:
    remote_ref = f"{profile.remote}/{profile.branch}"
    try:
        plan = _plan_from_name_status(
            operation,
            provider.payload_diff_name_status("HEAD", remote_ref),
        )
        _attach_diff_previews(plan, provider.payload_diff_patch("HEAD", remote_ref))
        return plan
    except Exception as exc:
        logger.debug("Unable to preview incoming sync changes: %s", exc)
        return _finalize_plan(operation, [])


def _attach_diff_previews(plan: SyncPlan, diff_output: str) -> None:
    if not diff_output.strip():
        return
    patches = _split_diff_by_path(diff_output)
    for change in plan.files:
        if change.category == "secrets":
            continue
        patch = patches.get(change.path)
        if patch:
            change.diff_preview = _trim_diff_preview(patch)


def _attach_added_file_previews(plan: SyncPlan, repo_path: Path) -> None:
    for change in plan.files:
        if (
            change.diff_preview
            or change.change_type != "added"
            or change.category in {"secrets", "sync"}
        ):
            continue
        path = repo_path / PAYLOAD_DIR_NAME / change.path
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw:
            continue
        text = raw[:12000].decode("utf-8", errors="replace")
        if len(raw) > len(raw[:12000]):
            text += "\n... file truncated ..."
        change.diff_preview = f"+++ {change.path}\n{text}"


def _split_diff_by_path(diff_output: str) -> dict[str, str]:
    result: dict[str, str] = {}
    current_path: str | None = None
    current_lines: list[str] = []
    for line in diff_output.splitlines():
        if line.startswith("diff --git "):
            if current_path and current_lines:
                result[current_path] = "\n".join(current_lines)
            current_path = _path_from_diff_header(line)
            current_lines = [line]
            continue
        if current_path:
            current_lines.append(line)
    if current_path and current_lines:
        result[current_path] = "\n".join(current_lines)
    return result


def _path_from_diff_header(line: str) -> str | None:
    parts = line.split()
    if len(parts) < 4:
        return None
    path = parts[3]
    if path.startswith("b/"):
        path = path[2:]
    return path.replace("\\", "/").removeprefix(f"{PAYLOAD_DIR_NAME}/")


def _trim_diff_preview(patch: str) -> str:
    lines = patch.splitlines()
    preview_lines = lines[:120]
    preview = "\n".join(preview_lines)
    if len(lines) > len(preview_lines):
        preview += "\n... diff truncated ..."
    if len(preview) > 12000:
        preview = preview[:12000] + "\n... diff truncated ..."
    return preview


def _status_path(line: str) -> str:
    value = line[3:] if len(line) > 3 else line
    if " -> " in value:
        value = value.split(" -> ", 1)[1]
    return value.strip().replace("\\", "/")


def _change_type_from_status(status: str) -> str:
    if "D" in status:
        return "deleted"
    if "A" in status or "?" in status:
        return "added"
    return "modified"


def _change_type_from_name_status(status: str) -> str:
    if status.startswith("D"):
        return "deleted"
    if status.startswith("A"):
        return "added"
    return "modified"


def _make_change(path: str, change_type: str, direction: str) -> SyncFileChange:
    category = _sync_category(path)
    risk = _risk_for_change(path, category, change_type)
    return SyncFileChange(
        path=path,
        category=category,
        change_type=change_type,
        risk=risk,
        direction=direction,
    )


def _sync_category(path: str) -> str:
    if path.startswith("config/"):
        return "config"
    if path.startswith("skills/"):
        return "skills"
    if path.startswith("memory/"):
        return "memory"
    if path == SECRET_BUNDLES_PATH:
        return "secrets"
    if path.startswith("_sync/"):
        return "sync"
    return "other"


def _risk_for_change(path: str, category: str, change_type: str) -> str:
    if category == "memory" and change_type == "deleted":
        return "high"
    if category == "memory" and path in {
        "memory/MEMORY.md",
        "memory/persona.md",
        "memory/user.md",
    }:
        return "high"
    if category == "secrets" and change_type == "deleted":
        return "high"
    if category == "secrets":
        return "medium"
    if change_type == "deleted":
        return "medium"
    return "low"


def _finalize_plan(operation: str, changes: list[SyncFileChange]) -> SyncPlan:
    summary = {"added": 0, "modified": 0, "deleted": 0, "high_risk": 0}
    for change in changes:
        summary[change.change_type] += 1
        if change.risk == "high":
            summary["high_risk"] += 1

    memory_deletes = [
        change
        for change in changes
        if change.category == "memory" and change.change_type == "deleted"
    ]
    warnings: list[str] = []
    if memory_deletes:
        warnings.append(f"{len(memory_deletes)} memory file(s) would be deleted.")
    if len(memory_deletes) >= 5:
        warnings.append("Large memory deletion detected; review before syncing.")
    secret_deletes = [
        change
        for change in changes
        if change.category == "secrets" and change.change_type == "deleted"
    ]
    if secret_deletes:
        warnings.append("The shared encrypted key vault would be deleted.")

    destructive = bool(
        memory_deletes or secret_deletes or any(c.risk == "high" for c in changes)
    )
    return SyncPlan(
        operation=operation,
        files=changes,
        summary=summary,
        destructive=destructive,
        requires_confirmation=destructive,
        warnings=warnings,
    )


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
