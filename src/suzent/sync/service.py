from __future__ import annotations

import asyncio
import json
from pathlib import Path

from suzent.config import USER_CONFIG_DIR
from suzent.logger import get_logger
from suzent.sync.conflicts import SyncConflictResolver
from suzent.sync.models import SyncManifest, SyncProfile
from suzent.sync.payload import MANIFEST_PATH, PAYLOAD_DIR_NAME, SyncPayloadBuilder
from suzent.sync.provider import GitHubSyncProvider
from suzent.sync.quickstart import (
    DEFAULT_REPO_NAME,
    default_repo_path,
    gh_cli_available,
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
        self.profiles_path = profiles_path or USER_CONFIG_DIR / "sync_profiles.json"
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
            raise ValueError("Incorrect Shibboleth (passphrase)")
        self._shibboleth_unlocks[profile.id] = shibboleth

    def status(self, profile_id: str | None = None) -> dict:
        try:
            profile = self.get_profile(profile_id)
        except ValueError:
            return {"configured": False, "profiles": []}

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

        return {
            "configured": True,
            "profile": profile.model_dump(mode="json"),
            "payload_dir": str(payload_dir),
            "payload_hashes": self.payload_builder.content_hashes(payload_dir),
            "forbidden_paths": self.payload_builder.validate_no_forbidden_paths(payload_dir),
            "git": validation,
            "requires_shibboleth": profile.encrypted_secret_sync_enabled,
            "shibboleth_unlocked": self.is_shibboleth_unlocked(profile.id),
            "has_secret_bundles": has_secret_bundles,
        }

    def validate(self, profile: SyncProfile) -> dict:
        return GitHubSyncProvider(
            Path(profile.repo_path), remote=profile.remote, branch=profile.branch
        ).validate(require_clean=False)

    def quickstart_info(self) -> dict:
        from suzent.sync.github_token import github_token_configured
        from suzent.sync.quickstart import (
            DEFAULT_REPO_NAME,
            gh_is_authenticated,
        )

        return {
            "default_repo_path": str(default_repo_path()),
            "default_repo_name": DEFAULT_REPO_NAME,
            "gh_available": gh_cli_available(),
            "github_authenticated": gh_is_authenticated() or github_token_configured(),
            "github_token_configured": github_token_configured(),
        }

    def quickstart(
        self,
        *,
        repo_name: str | None = None,
        authenticate_github: bool = True,
        github_token: str | None = None,
        repo_path: str | None = None,
        branch: str | None = None,
        remote: str | None = None,
        auto_sync_enabled: bool = False,
        auto_resolve_enabled: bool = True,
        interval_hours: int = 4,
    ) -> dict:
        return quickstart_github_sync(
            repo_name=repo_name or DEFAULT_REPO_NAME,
            authenticate_github=authenticate_github,
            github_token=github_token,
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
            phrase = self._require_shibboleth_for_pull(
                profile, payload_dir, shibboleth
            )
            restored = await asyncio.to_thread(
                self.payload_builder.apply_to_local, payload_dir
            )
            imported_keys: list[str] = []
            if phrase:
                imported_keys = await asyncio.to_thread(
                    self._import_secret_bundles, payload_dir, phrase
                )
            return {
                "success": True,
                "git": git_output,
                "restored": restored,
                "imported_secret_keys": imported_keys,
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
            if profile.encrypted_secret_sync_enabled:
                phrase = self._require_shibboleth(profile, shibboleth)
                manifest = await asyncio.to_thread(
                    self._write_secret_bundles,
                    repo_path,
                    profile,
                    manifest.revision_id,
                    phrase,
                )
            forbidden = self.payload_builder.validate_no_forbidden_paths(
                repo_path / PAYLOAD_DIR_NAME
            )
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
            }

    async def auto_sync(
        self, profile_id: str | None = None, *, shibboleth: str | None = None
    ) -> dict:
        profile = self.get_profile(profile_id)
        async with self._lock(profile):
            provider = GitHubSyncProvider(
                Path(profile.repo_path), remote=profile.remote, branch=profile.branch
            )
            await asyncio.to_thread(provider.pull_ff_only)
            payload_dir = Path(profile.repo_path) / PAYLOAD_DIR_NAME
            if profile.encrypted_secret_sync_enabled:
                phrase = self._optional_shibboleth(profile, shibboleth)
                if phrase:
                    await asyncio.to_thread(
                        self._import_secret_bundles, payload_dir, phrase
                    )
                else:
                    logger.warning(
                        "Skipping Shibboleth secret import on auto-sync: not unlocked"
                    )
            manifest = await asyncio.to_thread(
                self.payload_builder.build, Path(profile.repo_path), profile
            )
            if profile.encrypted_secret_sync_enabled:
                phrase = self._optional_shibboleth(profile, shibboleth)
                if phrase:
                    manifest = await asyncio.to_thread(
                        self._write_secret_bundles,
                        Path(profile.repo_path),
                        profile,
                        manifest.revision_id,
                        phrase,
                    )
                else:
                    logger.warning(
                        "Skipping Shibboleth secret export on auto-sync: not unlocked"
                    )
            await asyncio.to_thread(
                provider.commit_and_push_payload, manifest.revision_id
            )
            profile.last_revision = manifest.revision_id
            profile.last_sync_at = manifest.created_at
            self.save_profile(profile)
            return {"success": True, "manifest": manifest.model_dump(mode="json")}

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
        cached = self._shibboleth_unlocks.get(profile.id)
        if cached:
            return cached
        raise ValueError(
            "Shibboleth (passphrase) required. Unlock in Settings → Data before sync."
        )

    def _optional_shibboleth(self, profile: SyncProfile, explicit: str | None) -> str | None:
        if explicit:
            return explicit
        return self._shibboleth_unlocks.get(profile.id)

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
        bundles_file = secret_sync.export_bundles(
            profile, shibboleth, existing_file=existing
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

    def _import_secret_bundles(self, payload_dir: Path, shibboleth: str) -> list[str]:
        bundle_path = payload_dir / SECRET_BUNDLES_PATH
        secret_sync = EncryptedSecretSync()
        payload = secret_sync.read_bundles_file(bundle_path)
        if payload is None or not payload.bundles:
            return []
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
        return {item["id"]: SyncProfile.model_validate(item) for item in profiles}

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
