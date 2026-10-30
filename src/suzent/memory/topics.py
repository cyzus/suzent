"""What a memory is (its kind) and what it is about (its topics), read off its metadata.

Both are derived from fields every indexed row already stores — the `key:value` tags
on a daily-log line, the path and tags of a vault page — rather than written at index
time, so rows indexed before this existed get them too without re-embedding anything.
"""

import re
from pathlib import PurePosixPath
from typing import Any

MAX_TOPICS = 6
UNTYPED = "untyped"
# Vault pages and core files carry no kind tag; these categories are about the user.
ABOUT_USER_CATEGORIES = frozenset({"profile", "personal"})


def normalize_topics(raw: list[str]) -> list[str]:
    """Lowercase, hyphen-joined and deduplicated, so "Suzent repo" and "suzent-repo" meet."""
    topics: list[str] = []
    for item in raw:
        topic = re.sub(r"[\s_]+", "-", str(item).strip().lower()).strip("-")
        if topic and topic not in topics:
            topics.append(topic)
    return topics[:MAX_TOPICS]


def describe(meta: dict[str, Any]) -> dict[str, Any]:
    """`kind`, `source` (when typed) and `topics` for one row's metadata.

    Kinds match typed capture: `user`, `experience`, `world`. A daily-log line
    written before typed capture has no `kind:` tag and reports as untyped: the
    memory page shows those as early records, not curated memory.
    """
    tags = [str(t) for t in meta.get("tags") or [] if t]
    if meta.get("source_type") != "archive_log":
        about_user = meta.get("category") in ABOUT_USER_CATEGORIES
        return {
            "kind": "user" if about_user else "world",
            "topics": _page_topics(meta, tags),
        }

    fields: dict[str, Any] = {"kind": UNTYPED}
    scopes: list[str] = []
    for tag in tags:
        key, _, value = tag.partition(":")
        if key in ("kind", "source") and value:
            fields[key] = value
        elif key == "scope" and value:
            scopes.append(value)
    fields["topics"] = normalize_topics(scopes)
    return fields


def _page_topics(meta: dict[str, Any], tags: list[str]) -> list[str]:
    """A project page is about its project; any page is also about its own tags."""
    parts = PurePosixPath(str(meta.get("source_file") or "").replace("\\", "/")).parts
    project = (
        [PurePosixPath(parts[1]).stem]
        if meta.get("source_type") == "notebook"
        and len(parts) > 1
        and parts[0] == "1_Projects"
        else []
    )
    return normalize_topics(project + tags)
