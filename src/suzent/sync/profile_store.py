"""Read, write and self-heal sync profiles (``config/sync_profiles.json``)."""

from __future__ import annotations

import json
from pathlib import Path

from suzent.config import get_data_dir
from suzent.logger import get_logger
from suzent.sync.git_transport import git_remote_names
from suzent.sync.models import SyncProfile

logger = get_logger(__name__)


class SyncProfileStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def list_all(self) -> list[SyncProfile]:
        return list(self._load().values())

    def get(self, profile_id: str | None = None) -> SyncProfile:
        profiles = self._load()
        if profile_id:
            try:
                return profiles[profile_id]
            except KeyError as exc:
                raise ValueError(f"Unknown sync profile: {profile_id}") from exc
        if not profiles:
            raise ValueError("No sync profile configured")
        return next(iter(profiles.values()))

    def save(self, profile: SyncProfile) -> SyncProfile:
        profiles = self._load()
        profiles[profile.id] = profile
        self._save(profiles)
        return profile

    def _load(self) -> dict[str, SyncProfile]:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        profiles = data.get("profiles", [])
        loaded = {item["id"]: SyncProfile.model_validate(item) for item in profiles}
        if self._heal_profiles(loaded):
            self._save(loaded)
        return loaded

    def _heal_profiles(self, profiles: dict[str, SyncProfile]) -> bool:
        """Repair profiles that can no longer address their repo.

        Runs repo_path healing first: a profile pointing at a missing directory
        has no remotes to inspect, so remote healing would be meaningless until
        the path is corrected. Returns True if any profile was changed.
        """
        healed_paths = self._heal_repo_paths(profiles)
        healed_remotes = self._heal_remotes(profiles)
        return healed_paths or healed_remotes

    def _heal_repo_paths(self, profiles: dict[str, SyncProfile]) -> bool:
        """Self-heal profiles whose repo_path no longer points at a git repo.

        A stray path (e.g. a pytest temp dir that leaked into a real profile, or
        a repo moved/deleted) breaks every sync op with "not a Git repository".
        If the canonical <data_dir>/github-sync is a valid repo, redirect there
        and persist. Returns True if any profile was changed.
        """
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

    def _heal_remotes(self, profiles: dict[str, SyncProfile]) -> bool:
        """Self-heal profiles whose ``remote`` names a remote the repo lacks.

        Every sync op starts with ``git remote get-url <remote>``, so a profile
        naming a remote that was never created (e.g. a leaked test profile that
        set remote="upstream") fails with "No such remote" and no amount of
        retrying helps. Repoint at the repo's real remote, but *only* when there
        is exactly one — then it is the unambiguous sync destination.

        A repo with several remotes is left alone even when one is called
        "origin": the conventional name does not establish that it is the
        intended destination (``origin`` is often a fork while another remote is
        the real target), and picking it would silently push the user's brain to
        the wrong GitHub repository. Being stuck with a clear "No such remote"
        error is recoverable; a sync to the wrong repo is not.
        """
        changed = False
        for prof in profiles.values():
            repo_path = Path(prof.repo_path)
            if not (repo_path / ".git").is_dir():
                continue  # already reported by _heal_repo_paths
            remotes = git_remote_names(repo_path)
            if not remotes or prof.remote in remotes:
                continue
            if len(remotes) != 1:
                logger.warning(
                    "Sync profile %s names remote %r which %s does not have, "
                    "and its remotes (%s) are ambiguous — sync will fail until "
                    "reconfigured.",
                    prof.id,
                    prof.remote,
                    repo_path,
                    ", ".join(remotes),
                )
                continue
            replacement = remotes[0]
            logger.warning(
                "Sync profile %s named missing remote %r; repointing to %r",
                prof.id,
                prof.remote,
                replacement,
            )
            prof.remote = replacement
            changed = True
        return changed

    def _save(self, profiles: dict[str, SyncProfile]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "profiles": [
                profile.model_dump(mode="json")
                for profile in sorted(profiles.values(), key=lambda p: p.id)
            ]
        }
        self.path.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
