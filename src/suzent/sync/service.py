from __future__ import annotations

import asyncio
import difflib
from datetime import datetime, timezone
from pathlib import Path

from suzent.config import get_data_dir
from suzent.logger import get_logger
from suzent.sync.models import SyncPlan, SyncProfile
from suzent.sync.payload import PAYLOAD_DIR_NAME, SyncPayloadBuilder
from suzent.sync.planner import (
    finalize_plan,
    merge_plans,
    overlapping_paths,
    plan_incoming,
    plan_outgoing,
)
from suzent.sync.profile_store import SyncProfileStore
from suzent.sync.provider import GitHubSyncProvider, SyncConflictError
from suzent.sync.quickstart import (
    DEFAULT_REPO_NAME,
    default_repo_path,
    quickstart_github_sync,
)

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
        self.profiles = SyncProfileStore(self.profiles_path)
        self.payload_builder = payload_builder or SyncPayloadBuilder()
        self._locks: dict[str, asyncio.Lock] = {}

    def list_profiles(self) -> list[SyncProfile]:
        return self.profiles.list_all()

    def save_profile(self, profile: SyncProfile) -> SyncProfile:
        return self.profiles.save(profile)

    def create_profile(self, profile: SyncProfile) -> SyncProfile:
        return self.save_profile(profile)

    def get_profile(self, profile_id: str | None = None) -> SyncProfile:
        return self.profiles.get(profile_id)

    def status(self, profile_id: str | None = None) -> dict:
        try:
            profile = self.get_profile(profile_id)
        except ValueError:
            return {"configured": False, "profiles": []}

        provider = GitHubSyncProvider(
            Path(profile.repo_path), remote=profile.remote, branch=profile.branch
        )
        validation: dict | None
        try:
            validation = provider.validate(require_clean=False)
        except Exception as exc:
            validation = {"valid": False, "error": str(exc)}

        return {
            "configured": True,
            "profile": profile.model_dump(mode="json"),
            "git": validation,
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
        interval_hours: int = 4,
    ) -> dict:
        return quickstart_github_sync(
            repo_name=repo_name or DEFAULT_REPO_NAME,
            repo_path=Path(repo_path) if repo_path else None,
            branch=branch,
            remote=remote or "origin",
            auto_sync_enabled=auto_sync_enabled,
            interval_hours=interval_hours,
        )

    def preview_sync_plan(
        self,
        operation: str,
        profile_id: str | None = None,
        *,
        refresh_remote: bool = True,
    ) -> SyncPlan:
        if operation not in {"push", "pull", "auto"}:
            raise ValueError(f"Unknown sync operation: {operation}")
        profile = self.get_profile(profile_id)
        repo_path = Path(profile.repo_path)
        provider = GitHubSyncProvider(
            repo_path, remote=profile.remote, branch=profile.branch
        )

        if operation in {"push", "auto"}:
            payload_dir = repo_path / PAYLOAD_DIR_NAME
            current_hashes = self.payload_builder.content_hashes(payload_dir)
            preview_hashes = self.payload_builder.preview_content_hashes(payload_dir)
            plan = plan_outgoing(operation, current_hashes, preview_hashes)
            if operation == "auto":
                if refresh_remote:
                    provider.refresh_remote()
                incoming = _incoming_tracking_plan(provider, profile, "auto")
                plan = merge_plans("auto", [plan, incoming])
            return plan

        provider.refresh_remote()
        remote_ref = f"{profile.remote}/{profile.branch}"
        diff = provider.payload_diff_name_status("HEAD", remote_ref)
        return plan_incoming("pull", diff)

    async def preview_sync_plan_safe(
        self,
        operation: str,
        profile_id: str | None = None,
        *,
        refresh_remote: bool = True,
    ) -> SyncPlan:
        profile = self.get_profile(profile_id)
        async with self._lock(profile):
            return await asyncio.to_thread(
                self.preview_sync_plan,
                operation,
                profile.id,
                refresh_remote=refresh_remote,
            )

    async def preview_file_diff_safe(
        self,
        path: str,
        direction: str,
        profile_id: str | None = None,
    ) -> str:
        profile = self.get_profile(profile_id)
        async with self._lock(profile):
            return await asyncio.to_thread(
                self.preview_file_diff,
                path,
                direction,
                profile.id,
            )

    def preview_file_diff(
        self,
        path: str,
        direction: str,
        profile_id: str | None = None,
    ) -> str:
        if direction not in {"outgoing", "incoming"}:
            raise ValueError(f"Unknown sync direction: {direction}")
        profile = self.get_profile(profile_id)
        repo_path = Path(profile.repo_path)
        resolved = self.payload_builder.resolve_local_path(path)
        if resolved is None:
            raise ValueError(f"Invalid portable sync path: {path}")

        rel, local_path = resolved
        provider = GitHubSyncProvider(
            repo_path, remote=profile.remote, branch=profile.branch
        )
        if direction == "incoming":
            return _trim_diff_preview(
                provider.payload_file_diff_patch(
                    "HEAD",
                    f"{profile.remote}/{profile.branch}",
                    rel.as_posix(),
                )
            )

        payload_path = repo_path / PAYLOAD_DIR_NAME / rel
        before = _read_text_file(payload_path)
        after = _read_text_file(local_path)
        if rel.parts[0] == "memory" and after is None:
            after = before
        return _unified_file_diff(rel.as_posix(), before, after)

    async def pull(
        self,
        profile_id: str | None = None,
        *,
        confirm_destructive: bool = False,
        prefer_cloud: bool = False,
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
            restored = await asyncio.to_thread(
                self.payload_builder.apply_to_local,
                payload_dir,
                replace_memory=prefer_cloud,
            )
            await asyncio.to_thread(_reload_runtime)
            return {
                "success": True,
                "git": git_output,
                "restored": restored,
                "prefer_cloud": prefer_cloud,
            }

    async def discard_outgoing(
        self,
        profile_id: str | None = None,
        *,
        paths: list[str] | None = None,
    ) -> dict:
        profile = self.get_profile(profile_id)
        async with self._lock(profile):
            repo_path = Path(profile.repo_path)
            provider = GitHubSyncProvider(
                repo_path, remote=profile.remote, branch=profile.branch
            )
            if paths is not None:
                discarded = sorted(set(paths))
                invalid = [
                    path
                    for path in discarded
                    if not self.payload_builder.has_outgoing_change(
                        repo_path / PAYLOAD_DIR_NAME,
                        path,
                    )
                ]
                if invalid:
                    raise ValueError(
                        f"Unknown outgoing sync path(s): {', '.join(invalid)}"
                    )
                await asyncio.to_thread(provider.discard_payload_paths, discarded)
                restored = await asyncio.to_thread(
                    self.payload_builder.apply_paths_to_local,
                    repo_path / PAYLOAD_DIR_NAME,
                    discarded,
                )
                await asyncio.to_thread(_reload_runtime_for_paths, discarded)
                return {
                    "success": True,
                    "discarded": discarded,
                    "restored": restored,
                }

            plan = await asyncio.to_thread(self.preview_sync_plan, "push", profile.id)
            outgoing = [
                change for change in plan.files if change.direction == "outgoing"
            ]
            outgoing_paths = {change.path for change in outgoing}
            discarded = sorted(paths if paths is not None else outgoing_paths)
            unknown = sorted(set(discarded) - outgoing_paths)
            if unknown:
                raise ValueError(f"Unknown outgoing sync path(s): {', '.join(unknown)}")

            payload_dir = repo_path / PAYLOAD_DIR_NAME
            await asyncio.to_thread(provider.discard_payload_changes)
            restored = await asyncio.to_thread(
                self.payload_builder.apply_to_local,
                payload_dir,
                replace_memory=True,
            )
            await asyncio.to_thread(_reload_runtime)
            return {
                "success": True,
                "discarded": discarded,
                "restored": restored,
                "plan": plan.model_dump(mode="json"),
            }

    async def push(
        self,
        profile_id: str | None = None,
        *,
        confirm_destructive: bool = False,
    ) -> dict:
        profile = self.get_profile(profile_id)
        async with self._lock(profile):
            repo_path = Path(profile.repo_path)
            plan = await asyncio.to_thread(self.preview_sync_plan, "push", profile.id)
            if plan.requires_confirmation and not confirm_destructive:
                raise DestructiveSyncPlanError(plan)

            await asyncio.to_thread(self.payload_builder.build, repo_path)
            payload_dir = repo_path / PAYLOAD_DIR_NAME
            forbidden = self.payload_builder.validate_no_forbidden_paths(payload_dir)
            if forbidden:
                raise ValueError(f"Sync payload contains forbidden paths: {forbidden}")

            provider = GitHubSyncProvider(
                repo_path, remote=profile.remote, branch=profile.branch
            )
            git_output = await asyncio.to_thread(provider.commit_and_push_payload)
            profile.last_sync_at = datetime.now(timezone.utc)
            self.save_profile(profile)
            return {
                "success": True,
                "git": git_output,
            }

    async def auto_sync(
        self,
        profile_id: str | None = None,
        *,
        confirm_destructive: bool = False,
    ) -> dict:
        profile = self.get_profile(profile_id)
        async with self._lock(profile):
            repo_path = Path(profile.repo_path)
            payload_dir = repo_path / PAYLOAD_DIR_NAME
            provider = GitHubSyncProvider(
                repo_path, remote=profile.remote, branch=profile.branch
            )
            await asyncio.to_thread(provider.refresh_remote)
            plan = await asyncio.to_thread(
                self.preview_sync_plan,
                "auto",
                profile.id,
                refresh_remote=False,
            )
            overlapping = overlapping_paths(plan)
            if overlapping:
                plan.requires_confirmation = True
                plan.warnings.append(
                    "Changed on both devices, resolve before auto-sync: "
                    + ", ".join(overlapping)
                )
                return {
                    "success": False,
                    "blocked_review_required": True,
                    "plan": plan.model_dump(mode="json"),
                }
            if plan.requires_confirmation and not confirm_destructive:
                return {
                    "success": False,
                    "blocked_review_required": True,
                    "plan": plan.model_dump(mode="json"),
                }

            restored: list[str] = []
            directions = {change.direction for change in plan.files}
            if directions == {"incoming"}:
                await asyncio.to_thread(provider.pull_ff_only)
                restored = await asyncio.to_thread(
                    self.payload_builder.apply_to_local, payload_dir
                )
                await asyncio.to_thread(_reload_runtime)
                git_output = "Pulled incoming portable files."
            elif directions == {"incoming", "outgoing"}:
                # Each side changed different files. HEAD is the last synced
                # state, so commit the local side, rebase it onto the remote
                # (no shared files, so no conflicts), apply the merged payload
                # locally and push it.
                try:
                    await asyncio.to_thread(
                        self._merge_disjoint_changes, provider, repo_path
                    )
                except SyncConflictError:
                    plan.requires_confirmation = True
                    plan.warnings.append(
                        "Local and remote changes conflict; review before syncing."
                    )
                    return {
                        "success": False,
                        "blocked_review_required": True,
                        "plan": plan.model_dump(mode="json"),
                    }
                restored = await asyncio.to_thread(
                    self.payload_builder.apply_to_local, payload_dir
                )
                await asyncio.to_thread(_reload_runtime)
                git_output = await asyncio.to_thread(provider.push_payload)
            elif directions == {"outgoing"}:
                await asyncio.to_thread(provider.pull_ff_only)
                await asyncio.to_thread(self.payload_builder.build, repo_path)
                forbidden = self.payload_builder.validate_no_forbidden_paths(
                    payload_dir
                )
                if forbidden:
                    raise ValueError(
                        f"Sync payload contains forbidden paths: {forbidden}"
                    )
                git_output = await asyncio.to_thread(provider.commit_and_push_payload)
            else:
                git_output = "No portable file changes to sync."

            profile.last_sync_at = datetime.now(timezone.utc)
            self.save_profile(profile)
            return {
                "success": True,
                "git": git_output,
                "restored": restored,
            }

    def _merge_disjoint_changes(
        self, provider: GitHubSyncProvider, repo_path: Path
    ) -> None:
        """Commit local payload changes and rebase them onto the remote.

        On conflict the payload is reset to the last synced commit, leaving the
        live files untouched, and SyncConflictError is raised.
        """
        base = provider.head()
        self.payload_builder.build(repo_path)
        forbidden = self.payload_builder.validate_no_forbidden_paths(
            repo_path / PAYLOAD_DIR_NAME
        )
        if forbidden:
            provider.reset_hard(base)
            raise ValueError(f"Sync payload contains forbidden paths: {forbidden}")
        provider.commit_payload()
        try:
            provider.pull_ff_only()
        except SyncConflictError:
            provider.reset_hard(base)
            raise

    def _lock(self, profile: SyncProfile) -> asyncio.Lock:
        if profile.id not in self._locks:
            self._locks[profile.id] = asyncio.Lock()
        return self._locks[profile.id]


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


def _reload_runtime_for_paths(paths: list[str]) -> None:
    if any(path.startswith("config/") for path in paths):
        try:
            from suzent.config import CONFIG

            CONFIG.reload()
        except Exception:
            pass
    if any(path.startswith("skills/") for path in paths):
        try:
            from suzent.skills.manager import get_skill_manager

            get_skill_manager().reload()
        except Exception:
            pass


def _read_text_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    raw = path.read_bytes()
    if b"\x00" in raw:
        return None
    return raw.decode("utf-8", errors="replace")


def _unified_file_diff(path: str, before: str | None, after: str | None) -> str:
    if before == after:
        return ""
    patch = difflib.unified_diff(
        (before or "").splitlines(),
        (after or "").splitlines(),
        fromfile=f"a/{path}" if before is not None else "/dev/null",
        tofile=f"b/{path}" if after is not None else "/dev/null",
        lineterm="",
    )
    return _trim_diff_preview("\n".join(patch))


def _incoming_tracking_plan(
    provider: GitHubSyncProvider,
    profile: SyncProfile,
    operation: str,
) -> SyncPlan:
    remote_ref = f"{profile.remote}/{profile.branch}"
    try:
        plan = plan_incoming(
            operation,
            provider.payload_diff_name_status("HEAD", remote_ref),
        )
        return plan
    except Exception as exc:
        logger.debug("Unable to preview incoming sync changes: %s", exc)
        return finalize_plan(operation, [])


def _trim_diff_preview(patch: str) -> str:
    lines = patch.splitlines()
    preview_lines = lines[:120]
    preview = "\n".join(preview_lines)
    if len(lines) > len(preview_lines):
        preview += "\n... diff truncated ..."
    if len(preview) > 12000:
        preview = preview[:12000] + "\n... diff truncated ..."
    return preview
