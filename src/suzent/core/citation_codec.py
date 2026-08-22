"""Transport-safe parsing and rendering for inline citation markers.

PUA markers are useful between the model and the desktop renderer, but they are
not a durable interchange format.  This module is the backend authority for
normalising every supported marker spelling and rendering citations at
boundaries that cannot consume Suzent's rich citation protocol.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping


PUA_START = "\ue200"
PUA_END = "\ue201"
PUA_SEPARATOR = "\ue202"
OBJECT_REPLACEMENT = "\ufffc"

_ASCII_MARKER = r"\[\[([a-zA-Z]+):\s*([^\]\n]+?)\s*\]\]"
_PUA_MARKER = r"\ue200([a-zA-Z]+)\ue202([^\ue201]+)\ue201"
_OBJECT_MARKER = (
    r"\ufffc([a-zA-Z]+)\ufffc"
    r"([a-zA-Z0-9_,\s]+(?:\ufffc[a-zA-Z0-9_,\s]+)*)\ufffc"
)
_LOOSE_CITE_MARKER = (
    r"\bcite[-:]((?:[a-zA-Z0-9_]+_src_\d+)"
    r"(?:\s*,\s*[a-zA-Z0-9_]+_src_\d+)*)\b"
)
CITATION_MARKER_RE = re.compile(
    "|".join((_ASCII_MARKER, _PUA_MARKER, _OBJECT_MARKER, _LOOSE_CITE_MARKER))
)
_PARTIAL_MARKER_RE = re.compile(
    r"(?:\[$|(?:\[\[|\ue200|\ufffc)[a-zA-Z]*"
    r"(?:[:\ue202\ufffc][^\]\ue201]*)?$)"
)
_ID_SEPARATOR_RE = re.compile(r"[,\ue202\ufffc]")
_RESERVED_DELIMITER_RE = re.compile(r"[\ue200-\ue202\ufffc]")


@dataclass(frozen=True)
class CitationMarker:
    """One parsed inline rich-content marker."""

    marker_type: str
    source_ids: tuple[str, ...]


def _parse_match(match: re.Match[str]) -> CitationMarker:
    marker_type = (
        match.group(1)
        or match.group(3)
        or match.group(5)
        or ("cite" if match.group(7) else "")
    ).lower()
    payload = match.group(2) or match.group(4) or match.group(6) or match.group(7) or ""
    source_ids = tuple(
        token.strip() for token in _ID_SEPARATOR_RE.split(payload) if token.strip()
    )
    return CitationMarker(marker_type=marker_type, source_ids=source_ids)


def strip_trailing_partial_marker(text: str) -> str:
    """Hide a marker that was truncated or is incomplete while streaming."""
    return _PARTIAL_MARKER_RE.sub("", text)


def rewrite_citation_ids(
    text: str,
    id_map: Mapping[str, str],
    *,
    drop_unknown: bool = True,
) -> str:
    """Rewrite citations into debuggable ASCII markers using ``id_map``."""

    def replace(match: re.Match[str]) -> str:
        marker = _parse_match(match)
        if marker.marker_type != "cite":
            return ""
        rewritten = [
            id_map[source_id] for source_id in marker.source_ids if source_id in id_map
        ]
        if not rewritten and not drop_unknown:
            rewritten = list(marker.source_ids)
        return f"[[cite:{','.join(rewritten)}]]" if rewritten else ""

    return strip_trailing_partial_marker(CITATION_MARKER_RE.sub(replace, text))


def namespace_sources(
    sources: Iterable[Mapping[str, object]], namespace: str
) -> tuple[list[dict], dict[str, str]]:
    """Give sources collision-safe IDs for transport into another agent run."""
    safe_namespace = re.sub(r"[^a-zA-Z0-9_]", "_", namespace).strip("_")
    safe_namespace = safe_namespace or "agent"
    namespaced: list[dict] = []
    id_map: dict[str, str] = {}
    for index, source in enumerate(sources, 1):
        old_id = str(source.get("id") or "").strip()
        if not old_id or old_id in id_map:
            continue
        new_id = f"sa_{safe_namespace}_src_{index}"
        copied = dict(source)
        copied["id"] = new_id
        copied.setdefault("type", "subagent")
        namespaced.append(copied)
        id_map[old_id] = new_id
    return namespaced, id_map


def truncate_citation_text(text: str, limit: int) -> str:
    """Truncate without ever cutting through a citation marker."""
    if limit <= 0:
        return ""
    output: list[str] = []
    length = 0
    cursor = 0
    for match in CITATION_MARKER_RE.finditer(text):
        plain = text[cursor : match.start()]
        remaining = limit - length
        if len(plain) >= remaining:
            return "".join(output) + plain[: max(0, remaining - 1)].rstrip() + "…"
        output.append(plain)
        length += len(plain)
        marker = match.group(0)
        if length + len(marker) > limit:
            return "".join(output).rstrip() + "…"
        output.append(marker)
        length += len(marker)
        cursor = match.end()
    tail = strip_trailing_partial_marker(text[cursor:])
    remaining = limit - length
    if len(tail) <= remaining:
        return "".join(output) + tail
    return "".join(output) + tail[: max(0, remaining - 1)].rstrip() + "…"


def render_citations_plain_text(
    text: str,
    sources: Iterable[Mapping[str, object]] = (),
    *,
    include_sources: bool = True,
) -> str:
    """Render rich citations as portable numbered references and URLs."""
    sources_by_id = {
        str(source.get("id")): dict(source) for source in sources if source.get("id")
    }
    ordered_ids: list[str] = []
    numbers: dict[str, int] = {}

    def replace(match: re.Match[str]) -> str:
        marker = _parse_match(match)
        if marker.marker_type != "cite":
            return ""
        labels: list[str] = []
        for source_id in marker.source_ids:
            if source_id not in numbers:
                ordered_ids.append(source_id)
                numbers[source_id] = len(ordered_ids)
            labels.append(str(numbers[source_id]))
        if not labels:
            return ""
        prefix = ""
        if match.start() > 0 and not text[match.start() - 1].isspace():
            prefix = " "
        return f"{prefix}[{', '.join(labels)}]"

    body = strip_trailing_partial_marker(CITATION_MARKER_RE.sub(replace, text))
    # A malformed marker must still never leak Suzent's reserved protocol
    # characters to an external text surface.
    body = _RESERVED_DELIMITER_RE.sub("", body).rstrip()
    if not include_sources or not ordered_ids:
        return body

    lines: list[str] = []
    for source_id in ordered_ids:
        source = sources_by_id.get(source_id)
        number = numbers[source_id]
        if source is None:
            lines.append(f"[{number}] Source unavailable ({source_id})")
            continue
        title = str(source.get("title") or source_id).strip()
        url = str(source.get("url") or "").strip()
        lines.append(f"[{number}] {title} — {url}" if url else f"[{number}] {title}")
    return f"{body}\n\nSources:\n" + "\n".join(lines)


class CitationStreamRenderer:
    """Incrementally remove rich markers while preserving streamed text."""

    def __init__(self) -> None:
        self._raw = ""
        self._rendered_body = ""
        self._sources: dict[str, dict] = {}

    def add_sources(self, sources: Iterable[Mapping[str, object]]) -> None:
        for source in sources:
            source_id = str(source.get("id") or "")
            if source_id:
                self._sources[source_id] = dict(source)

    def feed(self, chunk: str) -> str:
        self._raw += chunk
        rendered = render_citations_plain_text(
            self._raw, self._sources.values(), include_sources=False
        )
        if not rendered.startswith(self._rendered_body):
            # Defensive fallback: never leak protocol characters if an upstream
            # transport rewrote an already-emitted prefix.
            self._rendered_body = rendered
            return ""
        delta = rendered[len(self._rendered_body) :]
        self._rendered_body = rendered
        return delta

    def finish(self) -> str:
        final = render_citations_plain_text(self._raw, self._sources.values())
        if final.startswith(self._rendered_body):
            delta = final[len(self._rendered_body) :]
            self._rendered_body = final
            return delta
        return ""
