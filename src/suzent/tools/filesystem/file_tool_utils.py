"""
Shared helpers for file-oriented tools.
"""

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suzent.core.agent_deps import AgentDeps


def get_or_create_path_resolver(deps: "AgentDeps"):
    """Return a cached resolver from deps or create one lazily."""
    if deps.path_resolver:
        return deps.path_resolver

    from suzent.tools.filesystem.path_resolver import PathResolver
    from suzent.config import CONFIG

    resolver = PathResolver(
        deps.chat_id,
        deps.sandbox_enabled,
        sandbox_data_path=CONFIG.sandbox_data_path,
        custom_volumes=deps.custom_volumes,
        workspace_root=deps.workspace_root,
    )
    deps.path_resolver = resolver
    return resolver


def is_windows_unc_path(path: str) -> bool:
    """Detect UNC-style paths on Windows hosts."""
    if os.name != "nt":
        return False
    return path.startswith("\\\\") or path.startswith("//")


def detect_text_encoding(raw: bytes) -> str:
    """Detect text encoding from BOM with UTF-8 fallback."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return "utf-16"
    return "utf-8"


def is_binary_content(raw: bytes, encoding: str) -> bool:
    """Binary heuristic for text tools.

    UTF-16 naturally contains null bytes, so the null-byte heuristic applies only to UTF-8 mode.
    """
    return encoding == "utf-8" and b"\x00" in raw
