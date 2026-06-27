"""
PathResolver - Unified path resolution for sandbox and non-sandbox contexts.

This module provides a shared utility for resolving virtual paths to host
filesystem paths, abstracting the difference between sandbox and non-sandbox
execution environments.
"""

import fnmatch
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger

# Directories pruned from recursive walks. Searching these (a Rust target dir,
# node_modules, .venv, .git, etc.) is almost never intended and can multiply the
# number of paths visited by orders of magnitude — enough to time out grep/glob.
# They are still searched when the caller explicitly targets a path inside one.
DEFAULT_PRUNED_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "target",
        "dist",
        "build",
        ".next",
        ".cargo",
    }
)


class PathResolver:
    """
    Unified path resolution for sandbox and non-sandbox contexts.

    In sandbox mode:
      - project cwd → data/sandbox-data/projects/{slug}/  (mounted at /workspace)
      - /shared/*   → data/sandbox-data/shared/*           (mounted at /shared)
      - /workspace/uploads/* → data/sandbox-data/projects/{slug}/uploads/*
      - /persistence/* → data/sandbox-data/projects/{slug}/* (legacy alias)
      - [Custom Mounts] → mapped host paths

    In non-sandbox mode:
      - The same project directories back virtual /workspace and /shared.
      - Absolute paths are allowed if within allowed directories.

    All chat-related files (heartbeat.md, context.md, plan.md, images/, uploads/)
    live in the project directory and are shared across all chats in the project.
    """

    def __init__(
        self,
        chat_id: str,
        sandbox_enabled: bool,
        project_slug: Optional[str] = None,
        sandbox_data_path: Optional[str] = None,
        uploads_path: Optional[str] = None,
        custom_volumes: Optional[List[str]] = None,
        workspace_root: Optional[str] = None,
    ):
        """
        Initialize the path resolver.

        Args:
            chat_id: The chat session identifier
            sandbox_enabled: Whether sandbox mode is active
            project_slug: The slug of the project this chat belongs to. If None,
                resolved from chat_id via the database (defaulting to the default project).
            sandbox_data_path: Base path for sandbox data (default: from CONFIG)
            uploads_path: Deprecated; uploads live under the project workspace
            custom_volumes: List of "host:container" volume mapping strings
            workspace_root: Root directory for host mode execution (default: from CONFIG)
        """
        from suzent.config import CONFIG

        self.chat_id = chat_id
        self.sandbox_enabled = sandbox_enabled
        self.sandbox_data_path = Path(
            sandbox_data_path or CONFIG.sandbox_data_path
        ).resolve()
        self.uploads_path = Path(
            uploads_path or CONFIG.sandbox_data_path
        ).resolve()  # Use sandbox path for consistency
        self.workspace_root = Path(workspace_root or CONFIG.workspace_root).resolve()
        self.custom_mounts: Dict[str, Path] = {}  # container_path -> host_path

        # Resolve project slug if not supplied
        if project_slug is None:
            project_slug = self._resolve_project_slug(chat_id)
        self.project_slug = project_slug
        self.project_dir = (
            self.sandbox_data_path / "projects" / project_slug
        ).resolve()

        # Parse custom volumes (supported in both modes for consistency)
        if custom_volumes:
            self._parse_custom_volumes(custom_volumes)

        # Ensure directories exist
        self._ensure_directories()

    @staticmethod
    def _resolve_project_slug(chat_id: str) -> str:
        """Resolve a chat's project slug via the database, falling back to default."""
        try:
            from suzent.database import get_database

            return get_database().get_chat_project_slug(chat_id)
        except Exception as e:
            logger.debug(f"Could not resolve project slug for chat {chat_id}: {e}")
            from suzent.database import ChatDatabase

            return ChatDatabase.DEFAULT_PROJECT_SLUG

    @staticmethod
    def parse_volume_string(vol: str) -> Optional[Tuple[str, str]]:
        """
        Parse a volume string 'host:container' into components.
        Handles Windows drive letters (e.g. D:/path:/container).
        Returns (host_path, container_path) or None if invalid.
        """
        if ":" not in vol:
            return None

        # Handle Windows drive letters (e.g. D:/host:/container)
        # Find the LAST colon which separates host and container
        last_colon = vol.rfind(":")
        if last_colon == -1:
            return None

        host_part = vol[:last_colon]
        container_part = vol[last_colon + 1 :]
        return host_part, container_part

    @staticmethod
    def to_linux_path(path: str) -> str:
        """
        Convert Windows path to Linux/WSL path if applicable.
        E.g. D:\\workspace -> /mnt/d/workspace
        """
        if os.name != "nt":
            return path

        path = path.replace("\\", "/")
        if ":" in path:
            drive, rest = path.split(":", 1)
            return f"/mnt/{drive.lower()}{rest}"
        return path

    @staticmethod
    def get_skill_virtual_path(skill_name: str) -> str:
        """
        Get the virtual path for a skill's definition file.
        Fallback for legacy flat skill mounts; loaded Skill objects carry the
        authoritative virtual_path for official/user/external buckets.
        """
        return f"/mnt/skills/{skill_name}/SKILL.md"

    def _parse_custom_volumes(self, volumes: List[str]) -> None:
        """Parse list of 'host:container' strings into a mapping."""
        for vol in volumes:
            try:
                parsed = self.parse_volume_string(vol)
                if not parsed:
                    continue

                host_part, container_part = parsed

                # Handle WSL-style mounts (/mnt/c/...) -> drive letter
                if host_part.startswith("/mnt/"):
                    match = re.match(r"^/mnt/([a-zA-Z])/(.*)", host_part)
                    if match:
                        drive = match.group(1).upper()
                        rest = match.group(2)
                        host_part = f"{drive}:/{rest}"

                # Resolve host path
                host_path = Path(host_part).resolve()

                # Normalize container path
                container_path = container_part.strip().replace("\\", "/")
                if not container_path.startswith("/"):
                    container_path = "/" + container_path

                # Store mapping
                self.custom_mounts[container_path] = host_path
                logger.debug(f"Mapped custom volume: {container_path} -> {host_path}")

            except Exception as e:
                logger.warning(f"Failed to parse custom volume '{vol}': {e}")

    def _ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""

        try:
            self.project_dir.mkdir(parents=True, exist_ok=True)
            (self.sandbox_data_path / "shared").mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create directories: {e}")

    def get_working_dir(self) -> Path:
        """Project directory — the agent's cwd, shared across all chats in the project."""
        return self.project_dir

    def resolve(self, virtual_path: str) -> Path:
        """
        Resolve a virtual path to an actual host filesystem path.

        Args:
            virtual_path: The path as specified by the user/agent

        Returns:
            Resolved Path object pointing to actual filesystem location

        Raises:
            ValueError: If path traversal is detected or path is not allowed
        """
        # Treat UNC-style paths as disallowed regardless of host OS.
        # This blocks network-share style inputs such as \\server\share\file
        # and //server/share/file before any normalization occurs.
        if virtual_path.startswith("\\\\") or virtual_path.startswith("//"):
            raise ValueError("UNC paths are not supported")

        # Normalize path separators
        virtual_path = virtual_path.replace("\\", "/").strip()

        return self._resolve_path(virtual_path)

    def _resolve_path(self, virtual_path: str) -> Path:
        """Resolve path using unified logic (custom mounts, workspace, shared)."""
        # 1. Check custom mounts first (works in both sandbox and host modes)
        # Check for longest matching prefix to handle nested mounts correctly
        best_match = None
        best_match_len = 0

        for mount_point, host_path in self.custom_mounts.items():
            # Check exact match or prefix match with /
            if virtual_path == mount_point or virtual_path.startswith(
                f"{mount_point}/"
            ):
                if len(mount_point) > best_match_len:
                    best_match = mount_point
                    best_match_len = len(mount_point)

        if best_match:
            rel_path = virtual_path[len(best_match) :].lstrip("/")
            host_root = self.custom_mounts[best_match]
            resolved = (
                (host_root / rel_path).resolve() if rel_path else host_root.resolve()
            )
            # Validate ensuring it's still inside that volume
            try:
                resolved.relative_to(host_root)
                return resolved
            except ValueError:
                raise ValueError(
                    f"Path traversal detected in custom volume: {resolved}"
                )

        # 2. Branch based on sandbox mode for absolute host paths
        if not self.sandbox_enabled:
            # HOST MODE: check for absolute host paths first
            is_windows_absolute = len(virtual_path) > 1 and virtual_path[1] == ":"
            is_unix_absolute = virtual_path.startswith("/") and not any(
                virtual_path.startswith(prefix)
                for prefix in [
                    "/shared",
                    "/uploads",
                    "/mnt",
                    "/workspace",
                    "/persistence",
                ]
            )
            if is_windows_absolute or is_unix_absolute:
                resolved = Path(virtual_path).resolve()
                return self._validate_within_workspace(resolved)

        # 3. Resolve virtual paths (same logic for both sandbox and host modes)
        resolved = self._resolve_virtual_path(virtual_path)

        # Security check: ensure resolved path is within allowed directories
        self._validate_path(resolved)
        return resolved

    def _resolve_virtual_path(self, path: str) -> Path:
        """
        Resolve virtual paths into host filesystem paths.

        Mapping:
          /workspace/*  → project_dir/*  (project cwd inside sandbox)
          /shared/*     → sandbox_data_path/shared/*
          /uploads/*    → project_dir/uploads/* (legacy alias)
          /persistence/* → project_dir/* (legacy alias)
          /mnt/*        → custom mount (must be registered)
          other paths   → resolved relative to project_dir
        """
        if (
            path.startswith("/workspace/")
            or path == "/workspace"
            or path.startswith("/persistence/")
            or path == "/persistence"
        ):
            prefix = "/persistence" if path.startswith("/persistence") else "/workspace"
            rel_path = path[len(prefix) :].lstrip("/")
            return (
                (self.project_dir / rel_path).resolve()
                if rel_path
                else self.project_dir
            )

        if path.startswith("/shared/") or path == "/shared":
            rel_path = path[len("/shared") :].lstrip("/")
            base = self.sandbox_data_path / "shared"
            return (base / rel_path).resolve() if rel_path else base.resolve()

        if path.startswith("/uploads/") or path == "/uploads":
            rel_path = path[len("/uploads") :].lstrip("/")
            base = self.project_dir / "uploads"
            base.mkdir(parents=True, exist_ok=True)
            return (base / rel_path).resolve() if rel_path else base.resolve()

        if path.startswith("/mnt"):
            # /mnt paths are only valid if registered as a custom mount.
            # No match means the mount is not configured — raise clearly.
            raise ValueError(
                f"Path '{path}' is under /mnt but no matching custom mount is registered. "
                "Register the volume via custom_volumes to allow access."
            )

        if path.startswith("/"):
            # Absolute paths default to project_dir if no other match
            rel_path = path.lstrip("/")
            return (self.project_dir / rel_path).resolve()

        # Relative paths are relative to project_dir (the agent's cwd)
        return (self.project_dir / path).resolve()

    def _validate_within_workspace(self, resolved: Path) -> Path:
        """
        Ensure resolved path is within workspace, sandbox-data, or custom volumes.

        Used for validating absolute host paths in host mode.

        Args:
            resolved: The resolved absolute path to validate

        Returns:
            The validated path if within allowed boundaries

        Raises:
            ValueError: If path is outside all allowed directories
        """
        # Check if within workspace
        try:
            resolved.relative_to(self.workspace_root)
            return resolved
        except ValueError:
            pass

        # Check if within sandbox data directories (same validation as sandbox mode)
        allowed_sandbox_roots = [
            self.project_dir,
            self.sandbox_data_path / "shared",
        ]
        for root in allowed_sandbox_roots:
            try:
                resolved.relative_to(root.resolve())
                return resolved
            except ValueError:
                continue

        # Check if within any custom volume host path
        for host_path in self.custom_mounts.values():
            try:
                resolved.relative_to(host_path.resolve())
                return resolved  # Within custom volume
            except ValueError:
                continue

        raise ValueError(
            f"Path '{resolved}' is outside workspace, sandbox-data, and custom volumes. "
            f"Workspace: {self.workspace_root}, Sandbox: {self.sandbox_data_path}"
        )

    def _validate_path(self, resolved: Path) -> None:
        """Validate that path is within allowed directories."""
        # Allowed roots: project_dir (covers /workspace and legacy /uploads), shared, custom mounts
        allowed_roots = [
            self.project_dir,
            self.sandbox_data_path / "shared",
        ]
        allowed_roots.extend(self.custom_mounts.values())

        for root in allowed_roots:
            try:
                resolved.relative_to(root.resolve())
                return  # Path is valid
            except ValueError:
                continue

        raise ValueError(
            f"Path traversal detected: {resolved} is outside allowed directories"
        )

    def is_path_allowed(self, path: Path) -> bool:
        """
        Check if a path is within allowed boundaries.

        Args:
            path: Path to check

        Returns:
            True if path is allowed, False otherwise
        """
        try:
            self._validate_path(path.resolve())
            return True
        except ValueError:
            return False

    def get_virtual_roots(self) -> List[Tuple[str, Path]]:
        """
        Get all top-level virtual roots and their host paths.

        Returns:
            List of (virtual_path, host_path) tuples.
            e.g. [("/workspace", D:/.../projects/default), ("/mnt/skills", D:/skills), ...]
        """
        roots = []

        # 1. Standard Roots
        roots.append(("/workspace", self.project_dir))
        roots.append(("/shared", self.sandbox_data_path / "shared"))

        # 2. Custom Mounts
        # Sort by length descending to handle nested mounts correctly
        sorted_mounts = sorted(
            self.custom_mounts.items(), key=lambda x: len(x[0]), reverse=True
        )
        for v_path, h_path in sorted_mounts:
            roots.append((v_path, h_path))

        return roots

    def is_shadowed(self, virtual_path: str) -> bool:
        """
        Check if a file at this virtual path would be hidden by a mount.

        Note: This is a stub implementation that returns False.
        Complex mount shadowing detection is not yet implemented.
        """
        # TODO: Implement robust shadowing check if complex nesting is needed.
        # For now, strict mount lists in get_virtual_roots + standard resolution is safe.
        return False

    def to_virtual_path(self, host_path: Path) -> Optional[str]:
        """
        Convert a host path back to a virtual path.

        Args:
            host_path: Absolute path on host filesystem

        Returns:
            Virtual path string, or None if path is not in a known mount
        """
        host_path = host_path.resolve()

        # 1. Check custom mounts (reverse lookup)
        # Prioritize longest match to handle nesting correctly
        # e.g. /mnt/data vs /mnt/data/nested

        # Invert map: host_path -> virtual_path (careful of duplicates?)
        # Better: iterate and find best match.

        best_candidate = None
        best_candidate_len = 0

        # Check all potential parents
        potential_parents = [
            (path, v_path) for v_path, path in self.custom_mounts.items()
        ]

        # Add standard roots
        potential_parents.append((self.project_dir.resolve(), "/workspace"))
        potential_parents.append(
            ((self.sandbox_data_path / "shared").resolve(), "/shared")
        )

        for root_path, v_prefix in potential_parents:
            try:
                # check if host_path is relative to this root
                if host_path == root_path or root_path in host_path.parents:
                    rel = host_path.relative_to(root_path)
                    v_path = f"{v_prefix}/{rel}".replace("\\", "/").rstrip("/.")
                    if v_path.endswith("/."):
                        v_path = v_path[:-2]

                    # Store the one with the longest prefix (most specific mount)
                    if len(v_prefix) > best_candidate_len:
                        best_candidate = v_path
                        best_candidate_len = len(v_prefix)
            except ValueError:
                continue

        return best_candidate

    def _glob_with_pruning(
        self, root: Path, pattern: str, allow_pruned: bool
    ) -> List[Path]:
        """Glob ``pattern`` under ``root``, pruning heavy directories.

        For recursive patterns (containing ``**``) this walks the tree with
        ``os.walk`` and removes pruned directories in place so they are never
        descended into — the key to keeping grep/glob fast on large repos.
        Non-recursive patterns fall back to the cheap ``Path.glob`` since they
        don't descend deeply.

        ``allow_pruned`` keeps the pruned directories when the caller explicitly
        targeted a path inside one (e.g. root already sits in node_modules).
        """
        if "**" not in pattern:
            try:
                return list(root.glob(pattern))
            except Exception:
                return []

        # Split the recursive pattern into the part before "**" (a directory
        # prefix to enter) and the part after (the per-file match).
        before, _, after = pattern.partition("**")
        prefix = before.strip("/")
        suffix = after.strip("/") or "*"

        start = root
        if prefix:
            start = root / prefix
            if not start.is_dir():
                # Prefix may itself contain wildcards; fall back to plain glob.
                try:
                    return list(root.glob(pattern))
                except Exception:
                    return []

        results: List[Path] = []
        for dirpath, dirnames, filenames in os.walk(start):
            if not allow_pruned:
                # Prune in place so os.walk never descends into these dirs.
                dirnames[:] = [d for d in dirnames if d not in DEFAULT_PRUNED_DIRS]
            base = Path(dirpath)
            # "**/x" matches across directories, so test both files and dirs.
            for name in filenames + dirnames:
                if fnmatch.fnmatch(name, suffix):
                    results.append(base / name)
            # A bare "**" (suffix defaulted to "*") should also yield the dirs
            # themselves; fnmatch above already covers that via dirnames.
        return results

    def find_files(
        self, pattern: str, search_path: Optional[str] = "/"
    ) -> List[Tuple[Path, str]]:
        """
        Find files matching a glob pattern, handling virtual roots transparently.
        """
        results = []
        seen_virtual_paths = set()

        # Determine roots to search
        search_roots = []

        if search_path == "/" or (search_path is None and pattern.startswith("/")):
            # Search all virtual roots
            search_roots = self.get_virtual_roots()
        else:
            # Search specific path — resolve() enforces workspace/custom-mount boundaries
            resolved = self.resolve(search_path or "/")
            if resolved.exists() and resolved.is_dir():
                search_roots = [(None, resolved)]

                # Also include custom mounts that are children of this path
                # to allow globbing into them
                # e.g. search_path="/mnt", mount="/mnt/saipre"
                search_path_clean = (search_path or "/").rstrip("/")
                for v_mount, h_mount in self.custom_mounts.items():
                    if v_mount.startswith(f"{search_path_clean}/"):
                        search_roots.append((v_mount, h_mount))

        for v_root_prefix, h_root in search_roots:
            if not h_root.exists():
                continue

            # Determine effective pattern for this root
            local_pattern = pattern

            if pattern.startswith("/"):
                # Absolute virtual pattern
                if v_root_prefix:
                    # 1. Check if the root itself matches the pattern (e.g. pattern="/mnt/*", root="/mnt/saipre")
                    # Normalize pattern to ignore trailing slash for directory matching
                    check_pattern = pattern.rstrip("/")
                    if fnmatch.fnmatch(v_root_prefix, check_pattern):
                        if v_root_prefix not in seen_virtual_paths:
                            seen_virtual_paths.add(v_root_prefix)
                            results.append((h_root, v_root_prefix))

                    # 2. Check if we should glob INSIDE this root
                    # We can descend if the pattern starts with the root prefix
                    if pattern.startswith(v_root_prefix + "/"):
                        local_pattern = pattern[len(v_root_prefix) + 1 :]
                    elif v_root_prefix == pattern:
                        # Exact match of directory, usually implies listing contents if it was a dir glob?
                        # But glob("/dir") returns the dir.
                        local_pattern = None  # Already handled by step 1
                    else:
                        # Pattern does not start with this root.
                        # e.g. pattern="/mnt/*/*", root="/mnt/saipre"
                        # Do we skip?
                        # We can try to handle overlap if "mnt/*" matches "mnt/saipre"?
                        # For now, simplistic prefix check.
                        local_pattern = None
                else:
                    # v_root_prefix is None or empty (shouldn't happen for roots list)
                    pass

            if not local_pattern:
                continue

            # Keep pruned dirs only when the search root itself sits inside one
            # (the caller explicitly targeted e.g. node_modules/foo).
            allow_pruned = any(part in DEFAULT_PRUNED_DIRS for part in h_root.parts)

            # Glob with directory pruning so heavy trees (.git, node_modules,
            # .venv, target, ...) are never walked unless explicitly targeted.
            matches = self._glob_with_pruning(h_root, local_pattern, allow_pruned)

            # h_root was already validated as inside an allowed boundary and the
            # walker only descends within it, so every match is allowed — skip
            # the per-file resolve()/relative_to() that was the prior hot path.
            # Resolve the root's virtual prefix once and derive children from it
            # by cheap string joins instead of one to_virtual_path() per match.
            root_prefix = v_root_prefix or self.to_virtual_path(h_root)
            for match in matches:
                v_path = None
                if root_prefix is not None:
                    try:
                        rel = match.relative_to(h_root)
                    except ValueError:
                        rel = None
                    if rel is not None:
                        v_path = (
                            root_prefix
                            if str(rel) == "."
                            else f"{root_prefix}/{rel}".replace("\\", "/")
                        )
                if not v_path:
                    # The root has no virtual mapping (a plain host path search).
                    # Use the host path itself — host-mode callers display the host
                    # path anyway, and it's a stable, cheap dedup key. Avoid the
                    # per-file to_virtual_path()/resolve() that dominated runtime.
                    v_path = str(match).replace("\\", "/")

                if v_path not in seen_virtual_paths:
                    seen_virtual_paths.add(v_path)
                    results.append((match, v_path))

        return results
