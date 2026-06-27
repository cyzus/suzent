"""Citation source manager for tracking all citable information sources.

Any tool that produces citable information can register a source with the
manager. The manager is the single authority for source IDs (``src_N``) and
generates both the LLM prompt context and the frontend event payload.

LIFECYCLE: one CitationManager is created per agent run (see streaming.py) and
injected into tools via ``AgentDeps.citation_manager``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CitationSourceType(str, Enum):
    """Types of citable information sources."""

    WEB_SEARCH = "search"
    WEBPAGE = "webpage"
    FILE = "file"
    NOTEBOOK = "notebook"
    MEMORY = "memory"
    MCP = "mcp"
    CODE = "code"
    BROWSER = "browser"
    SUBAGENT = "subagent"


@dataclass
class CitationSource:
    """A single citable information source."""

    id: str  # "src_1", "src_2", ...
    type: CitationSourceType
    title: str  # display name
    url: Optional[str] = None  # web URL / file:// path
    snippet: Optional[str] = None  # short summary (<= 200 chars)
    favicon: Optional[str] = None  # icon URL
    metadata: dict = field(default_factory=dict)


class CitationManager:
    """Manages all citable sources for a single agent run.

    The manager assigns IDs (``src_1``, ``src_2``, ...). Tools must NOT invent
    their own IDs — call :meth:`register` and use the returned ID so the prompt
    context, LLM output markers, and frontend sources stay in one ID space.
    """

    def __init__(self, turn: int = 0) -> None:
        self._sources: dict[str, CitationSource] = {}
        self._counter = 0
        # Conversation turn index. Ids are prefixed with it (``t{turn}_src_{n}``)
        # so they are globally unique across the whole chat — a citation that
        # references an earlier turn's source resolves correctly instead of
        # colliding with this turn's ``src_1``.
        self._turn = turn
        # Dedup by (type, url|title) so registering the same page twice across
        # tool calls reuses one ID instead of producing duplicate badges.
        self._dedup: dict[tuple[str, str], str] = {}

    def register(
        self,
        type: CitationSourceType,
        title: str,
        url: Optional[str] = None,
        snippet: Optional[str] = None,
        favicon: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Register a new source and return its ``t{turn}_src_{n}`` ID.

        Re-registering the same source (same type + url, or type + title when no
        url) returns the existing ID instead of allocating a new one.
        """
        dedup_key = (type.value, url or title or "")
        existing = self._dedup.get(dedup_key)
        if existing is not None:
            return existing

        self._counter += 1
        source_id = f"t{self._turn}_src_{self._counter}"
        self._sources[source_id] = CitationSource(
            id=source_id,
            type=type,
            title=title,
            url=url,
            snippet=snippet[:200] if snippet else None,
            favicon=favicon,
            metadata=metadata or {},
        )
        self._dedup[dedup_key] = source_id
        return source_id

    def get_all(self) -> list[CitationSource]:
        """Return all registered sources in registration order."""
        return list(self._sources.values())

    def get(self, source_id: str) -> Optional[CitationSource]:
        """Get a source by ID."""
        return self._sources.get(source_id)

    def to_prompt_context(self) -> str:
        """Render the available-sources block for injection into the prompt."""
        if not self._sources:
            return ""
        lines = []
        for sid, src in self._sources.items():
            desc = src.title
            if src.url:
                desc += f" ({src.url})"
            if src.snippet:
                desc += f": {src.snippet[:150]}"
            lines.append(f"  [{sid}] {desc}")
        return "\n".join(lines)

    def to_event_payload(self) -> list[dict]:
        """Build the payload for the ``citation_sources`` custom event."""
        return [
            {
                "id": src.id,
                "type": src.type.value,
                "title": src.title,
                "url": src.url,
                "snippet": src.snippet,
                "favicon": src.favicon,
            }
            for src in self._sources.values()
        ]

    def clear(self) -> None:
        """Reset for a new run."""
        self._sources.clear()
        self._dedup.clear()
        self._counter = 0
