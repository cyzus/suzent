"""
PathResolver - Unified path resolution for sandbox and non-sandbox contexts.

This module provides a shared utility for resolving virtual paths to host
filesystem paths, abstracting the difference between sandbox and non-sandbox
execution environments.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger


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

        # Parse custom volumes (supported in both modes for consistency)
        if custom_volumes:
            self._parse_custom_volumes(custom_volumes)

        # Ensure directories exist
        self._ensure_directories()

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
        import os
        if os.name != 'nt':
            return path
            
        path = path.replace("\\", "/")
        if ":" in path:
            drive, rest = path.split(":", 1)
            return f"/mnt/{drive.lower()}{rest}"
        return path

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
            # Always use the consistent sandbox-style structure
            (self.sandbox_data_path / "sessions" / self.chat_id).mkdir(
                parents=True, exist_ok=True
            )
            (self.sandbox_data_path / "shared").mkdir(parents=True, exist_ok=True)
            
            # In legacy mode, we might still want to ensure uploads path exists if used,
            # but for unification we prefer the sandbox structure.
            # We'll leave uploads_path unused to enforce the new standard.
        except Exception as e:
            logger.warning(f"Could not create directories: {e}")

    def get_working_dir(self) -> Path:
        """
        Get the working directory for this context.

        Returns:
            Path to the working directory
        """
        return self.sandbox_data_path / "sessions" / self.chat_id

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

        return self._resolve_path(virtual_path)

    def _resolve_path(self, virtual_path: str) -> Path:
        """Resolve path using unified logic (custom mounts, persistence, shared)."""
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
        self._validate_path(resolved)
        return resolved

    def _validate_path(self, resolved: Path) -> None:
        """Validate that path is within allowed directories."""
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
            self._validate_path(path.resolve())
            return True
        except ValueError:
            return False

    def get_virtual_roots(self) -> List[Tuple[str, Path]]:
        """
        Get all top-level virtual roots and their host paths.
        
        Returns:
            List of (virtual_path, host_path) tuples.
            e.g. [("/persistence", D:/.../sessions/123), ("/mnt/skills", D:/skills), ...]
        """
        roots = []
        
        # 1. Standard Roots
        roots.append(("/persistence", self.sandbox_data_path / "sessions" / self.chat_id))
        roots.append(("/shared", self.sandbox_data_path / "shared"))
        
        # 2. Custom Mounts
        # Sort by length descending to handle nested mounts correctly
        sorted_mounts = sorted(self.custom_mounts.items(), key=lambda x: len(x[0]), reverse=True)
        for v_path, h_path in sorted_mounts:
            roots.append((v_path, h_path))
            
        return roots

    def is_shadowed(self, virtual_path: str) -> bool:
        """
        Check if a file at this virtual path would be hidden by a mount.
        
        Example: if /persistence/data is a mount point, then a file at
        host path .../persistence/data/file.txt (from base layer) is shadowed.
        """
        # Ensure consistent separator
        virtual_path = virtual_path.replace("\\", "/")
        
        for mount_point in self.custom_mounts.keys():
            # If the path equals a mount point, it's the mount itself (not shadowed)
            if virtual_path == mount_point:
                continue
                
            # If path is inside a mount point, it belongs to that mount
            if virtual_path.startswith(f"{mount_point}/"):
                continue
                
            # If we are here, the path is NOT inside this mount.
            # But we need to check if this mount sits ON TOP of our path.
            # In a flat virtual root list this is subtle, but primarily we care about
            # base persistence vs custom mounts.
            
            # Implementation for now: 
            # If we are scanning a base root (like /persistence) and encounter a directory
            # that is ALSO a mount point, we should stop descending into it if we are
            # representing the base layer.
            # However, `is_shadowed` is asked about a specific FILE.
            
            # The tool logic will generally be:
            # 1. List files in /persistence (Host: .../sessions/123)
            # 2. If we find .../sessions/123/mnt/data/file.txt
            #    Virtual Path: /persistence/mnt/data/file.txt
            # 3. BUT if /persistence/mnt/data IS a custom mount point,
            #    then that file.txt is physically shadowed by the mount in the container.
            
            if mount_point == virtual_path or mount_point.startswith(f"{virtual_path}/"):
                 # This logic is for avoiding traversal INTO a mount point from below, 
                 # not exactly shadowing.
                 pass

        return False # TODO: Implement robust shadowing check if complex nesting is needed.
                     # For now, strict mount lists in get_virtual_roots + standard resolution is safe.

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
        potential_parents.append(((self.sandbox_data_path / "sessions" / self.chat_id).resolve(), "/persistence"))
        potential_parents.append(((self.sandbox_data_path / "shared").resolve(), "/shared"))
        
        for root_path, v_prefix in potential_parents:
            try:
                # check if host_path is relative to this root
                if host_path == root_path or root_path in host_path.parents:
                    rel = host_path.relative_to(root_path)
                    v_path = f"{v_prefix}/{rel}".replace("\\", "/").rstrip("/.")
                    if v_path.endswith("/."): v_path = v_path[:-2]
                    
                    # Store the one with the longest prefix (most specific mount)
                    if len(v_prefix) > best_candidate_len:
                        best_candidate = v_path
                        best_candidate_len = len(v_prefix)
            except ValueError:
                continue
                
        return best_candidate
