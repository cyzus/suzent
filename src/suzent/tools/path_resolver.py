"""
PathResolver - Unified path resolution for sandbox and non-sandbox contexts.

This module provides a shared utility for resolving virtual paths to host
filesystem paths, abstracting the difference between sandbox and non-sandbox
execution environments.
"""

import re
from pathlib import Path
from typing import Optional, List, Dict

from suzent.logger import get_logger

logger = get_logger(__name__)


class PathResolver:
    """
    Unified path resolution for sandbox and non-sandbox contexts.

    In sandbox mode:
      - /persistence/* → sandbox-data/sessions/{chat_id}/*
      - /shared/*      → sandbox-data/shared/*
      - /uploads/*     → sandbox-data/sessions/{chat_id}/uploads/*
      - [Custom Mounts] → mapped host paths

    In non-sandbox mode:
      - Paths are relative to data/uploads/{chat_id}/
      - Absolute paths are allowed if within allowed directories
    """

    def __init__(
        self,
        chat_id: str,
        sandbox_enabled: bool,
        sandbox_data_path: str = "sandbox-data",
        uploads_path: str = "data/uploads",
        custom_volumes: Optional[List[str]] = None,
    ):
        """
        Initialize the path resolver.

        Args:
            chat_id: The chat session identifier
            sandbox_enabled: Whether sandbox mode is active
            sandbox_data_path: Base path for sandbox data (default: "sandbox-data")
            uploads_path: Base path for non-sandbox uploads (default: "data/uploads")
            custom_volumes: List of "host:container" volume mapping strings
        """
        self.chat_id = chat_id
        self.sandbox_enabled = sandbox_enabled
        self.sandbox_data_path = Path(sandbox_data_path).resolve()
        self.uploads_path = Path(uploads_path).resolve()
        self.custom_mounts: Dict[str, Path] = {}  # container_path -> host_path

        # Parse custom volumes if in sandbox mode
        if self.sandbox_enabled and custom_volumes:
            self._parse_custom_volumes(custom_volumes)

        # Ensure directories exist
        self._ensure_directories()

    def _parse_custom_volumes(self, volumes: List[str]) -> None:
        """Parse list of 'host:container' strings into a mapping."""
        for vol in volumes:
            try:
                if ":" not in vol:
                    continue

                # Handle Windows drive letters (e.g. D:/host:/container)
                # Find the LAST colon which separates host and container
                last_colon = vol.rfind(":")
                if last_colon == -1:
                    continue

                host_part = vol[:last_colon]
                container_part = vol[last_colon + 1 :]

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
            if self.sandbox_enabled:
                (self.sandbox_data_path / "sessions" / self.chat_id).mkdir(
                    parents=True, exist_ok=True
                )
                (self.sandbox_data_path / "shared").mkdir(parents=True, exist_ok=True)
            else:
                (self.uploads_path / self.chat_id).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create directories: {e}")

    def get_working_dir(self) -> Path:
        """
        Get the working directory for this context.

        Returns:
            Path to the working directory
        """
        if self.sandbox_enabled:
            return self.sandbox_data_path / "sessions" / self.chat_id
        else:
            return self.uploads_path / self.chat_id

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
        # Normalize path separators
        virtual_path = virtual_path.replace("\\", "/").strip()

        if self.sandbox_enabled:
            return self._resolve_sandbox_path(virtual_path)
        else:
            return self._resolve_non_sandbox_path(virtual_path)

    def _resolve_sandbox_path(self, virtual_path: str) -> Path:
        """Resolve path in sandbox mode."""
        # 1. Check custom mounts
        # check for longest matching prefix to handle nested mounts correctly
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

        # 2. Standard Sandbox Paths
        if virtual_path.startswith("/persistence/") or virtual_path == "/persistence":
            rel_path = virtual_path[len("/persistence") :].lstrip("/")
            base = self.sandbox_data_path / "sessions" / self.chat_id
            resolved = (base / rel_path).resolve() if rel_path else base.resolve()

        elif virtual_path.startswith("/shared/") or virtual_path == "/shared":
            rel_path = virtual_path[len("/shared") :].lstrip("/")
            base = self.sandbox_data_path / "shared"
            resolved = (base / rel_path).resolve() if rel_path else base.resolve()

        elif virtual_path.startswith("/uploads/") or virtual_path == "/uploads":
            # Map /uploads to /persistence/uploads for convenience
            rel_path = virtual_path[len("/uploads") :].lstrip("/")
            base = self.sandbox_data_path / "sessions" / self.chat_id / "uploads"
            base.mkdir(parents=True, exist_ok=True)
            resolved = (base / rel_path).resolve() if rel_path else base.resolve()

        elif virtual_path.startswith("/"):
            # Absolute paths default to /persistence if no other match
            rel_path = virtual_path.lstrip("/")
            base = self.sandbox_data_path / "sessions" / self.chat_id
            resolved = (base / rel_path).resolve()

        else:
            # Relative paths are relative to /persistence
            base = self.sandbox_data_path / "sessions" / self.chat_id
            resolved = (base / virtual_path).resolve()

        # Security check: ensure resolved path is within allowed directories
        self._validate_sandbox_path(resolved)
        return resolved

    def _resolve_non_sandbox_path(self, virtual_path: str) -> Path:
        """Resolve path in non-sandbox mode."""
        working_dir = self.uploads_path / self.chat_id

        if virtual_path.startswith("/"):
            # Treat absolute-looking paths as relative to working dir
            rel_path = virtual_path.lstrip("/")
            resolved = (working_dir / rel_path).resolve()
        else:
            resolved = (working_dir / virtual_path).resolve()

        # Security check
        self._validate_non_sandbox_path(resolved)
        return resolved

    def _validate_sandbox_path(self, resolved: Path) -> None:
        """Validate that path is within allowed sandbox directories."""
        # Allowed roots include standard dirs AND all custom volume host paths
        allowed_roots = [
            self.sandbox_data_path / "sessions" / self.chat_id,
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

    def _validate_non_sandbox_path(self, resolved: Path) -> None:
        """Validate that path is within allowed non-sandbox directories."""
        allowed_root = self.uploads_path / self.chat_id

        try:
            resolved.relative_to(allowed_root.resolve())
        except ValueError:
            raise ValueError(
                f"Path traversal detected: {resolved} is outside {allowed_root}"
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
            if self.sandbox_enabled:
                self._validate_sandbox_path(path.resolve())
            else:
                self._validate_non_sandbox_path(path.resolve())
            return True
        except ValueError:
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

        if self.sandbox_enabled:
            # 1. Check custom mounts (reverse lookup)
            for mount_point, mount_host_path in self.custom_mounts.items():
                try:
                    rel = host_path.relative_to(mount_host_path)
                    if str(rel) == ".":
                        return mount_point
                    return f"{mount_point}/{rel}".replace("\\", "/")
                except ValueError:
                    continue

            # 2. Check /persistence
            persistence_root = (
                self.sandbox_data_path / "sessions" / self.chat_id
            ).resolve()
            try:
                rel = host_path.relative_to(persistence_root)
                return f"/persistence/{rel}".rstrip("/")
            except ValueError:
                pass

            # 3. Check /shared
            shared_root = (self.sandbox_data_path / "shared").resolve()
            try:
                rel = host_path.relative_to(shared_root)
                return f"/shared/{rel}".rstrip("/")
            except ValueError:
                pass
        else:
            working_dir = (self.uploads_path / self.chat_id).resolve()
            try:
                rel = host_path.relative_to(working_dir)
                return str(rel).replace("\\", "/")
            except ValueError:
                pass

        return None
