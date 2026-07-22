from __future__ import annotations

import asyncio
import difflib
import json
from datetime import datetime, timezone
from pathlib import Path

from suzent.config import get_data_dir
from suzent.logger import get_logger
from suzent.sync.models import (
    SyncFileChange,
    SyncPlan,
    SyncProfile,
)
from suzent.sync.payload import PAYLOAD_DIR_NAME, SyncPayloadBuilder
from suzent.sync.provider import GitHubSyncProvider
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
        self.payload_builder = payload_builder or SyncPayloadBuilder()
        self._locks: dict[str, asyncio.Lock] = {}

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
            plan = _plan_from_hashes(operation, current_hashes, preview_hashes)
            if operation == "auto":
                if refresh_remote:
                    provider.refresh_remote()
                incoming = _incoming_tracking_plan(provider, profile, "auto")
                plan = _merge_plans("auto", [plan, incoming])
            return plan

        provider.refresh_remote()
        remote_ref = f"{profile.remote}/{profile.branch}"
        diff = provider.payload_diff_name_status("HEAD", remote_ref)
        return _plan_from_name_status("pull", diff)

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
            if _has_mixed_file_changes(plan):
                plan.requires_confirmation = True
                plan.warnings.append(
                    "Incoming and outgoing files must be resolved before auto-sync."
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

    def _lock(self, profile: SyncProfile) -> asyncio.Lock:
        if profile.id not in self._locks:
            self._locks[profile.id] = asyncio.Lock()
        return self._locks[profile.id]

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


def _plan_from_hashes(
    operation: str,
    current_hashes: dict[str, str],
    preview_hashes: dict[str, str],
) -> SyncPlan:
    changes: list[SyncFileChange] = []
    for path in sorted(current_hashes.keys() | preview_hashes.keys()):
        before = current_hashes.get(path)
        after = preview_hashes.get(path)
        if before == after:
            continue
        if before is None:
            change_type = "added"
        elif after is None:
            change_type = "deleted"
        else:
            change_type = "modified"
        changes.append(_make_change(path, change_type, "outgoing"))
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


def _has_mixed_file_changes(plan: SyncPlan) -> bool:
    directions = {change.direction for change in plan.files}
    return directions == {"incoming", "outgoing"}


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
        return plan
    except Exception as exc:
        logger.debug("Unable to preview incoming sync changes: %s", exc)
        return _finalize_plan(operation, [])


def _trim_diff_preview(patch: str) -> str:
    lines = patch.splitlines()
    preview_lines = lines[:120]
    preview = "\n".join(preview_lines)
    if len(lines) > len(preview_lines):
        preview += "\n... diff truncated ..."
    if len(preview) > 12000:
        preview = preview[:12000] + "\n... diff truncated ..."
    return preview


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
    destructive = bool(memory_deletes or any(c.risk == "high" for c in changes))
    return SyncPlan(
        operation=operation,
        files=changes,
        summary=summary,
        destructive=destructive,
        requires_confirmation=destructive,
        warnings=warnings,
    )
