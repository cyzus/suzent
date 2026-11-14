"""
Shared helpers for file-oriented tools.
"""

import difflib
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
        cwd=getattr(deps, "cwd", None),
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


# Past this many changed lines the exact diff stops being cheap (Myers is
# O((N + M) * D)); that is a rewrite, where rough counts are fine.
_EXACT_DIFF_MAX_EDITS = 1000


def _edit_distance(a: list[str], b: list[str], max_d: int) -> int | None:
    """Fewest line inserts plus deletes turning ``a`` into ``b`` (Myers), or None past ``max_d``."""
    n, m = len(a), len(b)
    offset = max_d + 1
    furthest = [0] * (2 * max_d + 3)
    for d in range(max_d + 1):
        for k in range(-d, d + 1, 2):
            if k == -d or (
                k != d and furthest[offset + k - 1] < furthest[offset + k + 1]
            ):
                x = furthest[offset + k + 1]
            else:
                x = furthest[offset + k - 1] + 1
            y = x - k
            while x < n and y < m and a[x] == b[y]:
                x += 1
                y += 1
            furthest[offset + k] = x
            if x >= n and y >= m:
                return d
    return None


def count_changed_lines(old: str, new: str) -> tuple[int, int]:
    """Return ``(added, removed)`` line counts between two versions of a file.

    Computed here so the chat UI can show "+N -M" without diffing whole files
    in the browser for every edit it renders. Exact for edits: difflib's
    autojunk would drop lines repeated across a 200+ line file as anchors and
    count a one-line edit as hundreds.
    """
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    distance = _edit_distance(old_lines, new_lines, _EXACT_DIFF_MAX_EDITS)
    if distance is not None:
        common = (len(old_lines) + len(new_lines) - distance) // 2
        return len(new_lines) - common, len(old_lines) - common

    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    added = removed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed += i2 - i1
        if tag in ("replace", "insert"):
            added += j2 - j1
    return added, removed
