"""Typed capture: the prompt, schema and gate that propose candidate memories.

The old extractor wrote one untyped fact per thing it noticed and could not tell the
user's words from the agent's or a tool's. Capture labels every candidate with what
kind of memory it is, where it came from and the exact words behind it, and a
deterministic gate then drops what the labels prove is not a memory: the agent's own
words, task-only requests, user facts with no user line behind them.

The prompt and schema were checked offline against the 2026-10-14..22 batches before
they came here; see docs/08-developing/architecture/memory-architecture.md.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

type Kind = Literal["user", "experience", "world"]
type Source = Literal["user_said", "user_did", "outcome", "agent_said", "tool_output"]
type Horizon = Literal["durable", "dated", "ephemeral"]
type Category = Literal["personal", "preference", "goal", "context", "technical"]

MAX_CANDIDATES = 5
# Share of the evidence's character bigrams that must appear in one USER line. Exact
# matching dropped real quotes the model had re-spaced or trimmed of punctuation.
EVIDENCE_MATCH = 0.8
# A candidate this close to a memory already on record says nothing new.
RESTATEMENT_MATCH = 0.9
# Dated facts are written with a review date this far out.
DATED_STALE_DAYS = 90

_CATEGORY_ALIASES = {
    "project": "context",
    "work": "context",
    "other": "context",
    "general": "context",
    "identity": "personal",
    "relationship": "personal",
    "habit": "preference",
    "plan": "goal",
    "skill": "technical",
    "tech": "technical",
}
_SOURCE_ALIASES = {
    "user": "user_said",
    "user_stated": "user_said",
    "user_action": "user_did",
    "assistant": "agent_said",
    "agent": "agent_said",
    "tool": "tool_output",
    "action": "tool_output",
    "result": "outcome",
}
_HORIZON_ALIASES = {"permanent": "durable", "temporary": "dated", "task": "ephemeral"}
_KIND_ALIASES = {"lesson": "experience", "knowledge": "world", "fact": "user"}


def _alias(value: Any, aliases: dict[str, str]) -> Any:
    if isinstance(value, str):
        key = value.strip().lower()
        return aliases.get(key, key)
    return value


class CapturedFact(BaseModel):
    """One candidate memory, labelled so the gate can check it."""

    content: str = Field(
        ..., description="One sentence, subject first: 'User …' or 'Agent …'"
    )
    kind: Kind
    source: Source
    evidence: str = Field(
        ..., description="Verbatim excerpt from the batch, in its original language"
    )
    horizon: Horizon
    category: Category = "context"
    importance: float = Field(0.5, ge=0.0, le=1.0)

    @field_validator("category", mode="before")
    @classmethod
    def _category(cls, v: Any) -> Any:
        return _alias(v, _CATEGORY_ALIASES)

    @field_validator("source", mode="before")
    @classmethod
    def _source(cls, v: Any) -> Any:
        return _alias(v, _SOURCE_ALIASES)

    @field_validator("horizon", mode="before")
    @classmethod
    def _horizon(cls, v: Any) -> Any:
        return _alias(v, _HORIZON_ALIASES)

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, v: Any) -> Any:
        return _alias(v, _KIND_ALIASES)


class CaptureResponse(BaseModel):
    facts: list[CapturedFact] = Field(default_factory=list)


CAPTURE_SYSTEM_PROMPT = """You are the capture step of a personal agent's memory. You read a batch of
conversation turns and propose a few candidate memories. A later step decides where they go.
Most batches hold nothing worth keeping; an empty list is the normal answer.

The batch has lines of three kinds:
- USER: what the user typed. The only place facts about the user come from.
- ASSISTANT: what the agent wrote. Never evidence about the user, even when it states
  something about the user: it is usually repeating memory it was given.
- ACTION: a tool call the agent made and its output. File contents, search results and
  command output are not things the user said, even when they describe the user
  (a persona file, a profile page, a config, a git log).

## Three kinds of memory
- user: what the user would say about themselves: identity, relationships, preferences
  and working style, long-running goals at the level the user would describe them,
  decisions with their reason, life events. Only from USER lines.
- experience: a lesson tied to an outcome. A separate step reads failures and their fixes
  for these; never propose one here.
- world: how something works, why it is built that way, or where to look, learned in
  this batch, with the file path or URL it came from. Only what the source itself does
  not already say.

## Never memory
- Anything readable from the repo, git, CI or an issue tracker: versions, commits, PR or
  issue numbers and their status, release readiness, file lists, test counts, which tools
  exist or are deferred.
- Transient state: what the agent is doing now, blockers, failures of a delivery or a
  login, "task done", "currently on branch X".
- System, scheduler or protocol instructions, and the spec of a scheduled task.
- The agent's own analysis, news summaries or drafts, unless the user took a position
  on them; then store the user's position, not the content.

## Fields
- content: one sentence, subject first ("User prefers …", "Agent proposed … and the user
  rejected it because …"). Keep who said or did what. The examples in this prompt show
  the shape, not the language.
- source: where it came from.
  user_said = a USER line states it; user_did = the user's action shows it (accepted,
  rejected, chose); outcome = a result (tests, completion, user verdict);
  agent_said = an ASSISTANT line; tool_output = an ACTION output.
  Label honestly: agent_said and tool_output are allowed labels.
- evidence: copy the exact words from the batch that support it, in the original
  language, 5 to 40 words. For user_said and user_did, copy from a USER line.
- horizon: durable = true until something changes it; dated = true now but will expire
  (a trip next month, the current release); ephemeral = true only for this task.
  A request to do something now is ephemeral, however it is phrased: "rename the export
  button", "make the report match last week's layout", "find conferences I could
  submit to" are tasks, not goals. A plan with a date is dated. Only a
  statement about how things should be from now on is durable ("I want this app to
  stay offline-first", "always run the linter before committing").
- category: personal, preference, goal, context or technical.
- importance: 0.0-1.0.

## Rules
- Do not go beyond the user's words. One question is not a preference. Do not add
  places, dates, reasons or details the user did not give.
- A task request is ephemeral, but a requirement attached to it may not be. When the
  user adds a condition that would hold for the next task of the same kind ("keep the
  summary under one page", "no emoji in the commit"), store
  the condition as a durable preference, not the task.
- A choice names what was chosen and among what: "User chose the two-column layout
  over the tabbed one for settings", never "User chose option 1". If the batch does not
  say what the option was, skip it.
- One candidate per thing. Paraphrases of the same statement are one candidate.
- At most 5 candidates per batch; keep the most important.
- Write dates as absolute dates, resolved against the date the turn is marked with.
- When a later turn changes something said earlier, extract only where it ended up.
- Turns marked as earlier context were already processed. Use them to understand the
  new turns; never extract from them.
- Write content in the language the user writes in: the language of the USER lines, or
  the one most of them use when they mix. ASSISTANT and ACTION lines do not decide it.
  When a USER line updates a memory listed below, keep that memory's language unless the
  user now writes in another one. Evidence stays verbatim.

## Already in memory
The prompt may list memories that already exist. They are context, not material.
- Do not propose one again because it came up again, and do not propose what the
  agent repeats from it.
- Propose it when a USER line changes it: new specifics, a correction, a reversal.
  Write the full updated memory, not the delta. When unsure whether a USER line
  changes a known user fact, propose it.
- Some listed memories may be wrong. Never copy one; only the batch is evidence.
"""


def format_capture_prompt(batch: str, known: Optional[list[str]] = None) -> str:
    block = ""
    if known:
        lines = "\n".join(f"- {k}" for k in known)
        block = f"## Already in memory\n{lines}\n\n"
    return f"""Propose candidate memories from this batch.

{block}---
{batch}
---

Return JSON with a "facts" array; an empty array when nothing qualifies."""


# --- gate ---

# Only the batch's own section headers: a reply's markdown headings stay in its message.
_LINE_START = re.compile(
    r"^(USER: |ASSISTANT: |ACTION: |### Turn|## (New turns|Earlier context))", re.M
)
_CITATION = re.compile(r"https?://|[\w.-]+/[\w./-]+|\w+\.(py|ts|tsx|md|json|toml)\b")
_CONTEXT_FREE_CHOICE = re.compile(
    r"\b(option|choice|alternative|approach|plan|proposal)\s*(#?\d+|[a-d])\b"
    r"|\bthe\s+(first|second|third|fourth|last|other|former|latter)\s+(one|option)\b"
    r"|\b(option|choice)\s+(one|two|three)\b",
    re.I,
)
_NUMBER = re.compile(r"\d+(?:[.:/-]\d+)*")
_PROPER_NOUN = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-zA-Z]+\b")
_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")
_GENERIC_CAPITALS = frozenset({"User", "Agent", "I", "The", "A", "An"})


def normalize(text: str) -> str:
    # `*` too: agents bold words in their replies, and a quote copied out drops it.
    return re.sub(r"[\s\"'`*“”‘’「」.,;:!?，。；：！？、]+", "", text).lower()


def _bigrams(text: str) -> list[str]:
    return [text[i : i + 2] for i in range(len(text) - 1)] or ([text] if text else [])


def _overlap(needle: str, haystack: str) -> float:
    """Share of *needle*'s character bigrams that occur in *haystack*."""
    grams = _bigrams(needle)
    if not grams:
        return 0.0
    present = set(_bigrams(haystack))
    return sum(1 for g in grams if g in present) / len(grams)


def similarity(a: str, b: str) -> float:
    ga, gb = set(_bigrams(a)), set(_bigrams(b))
    if not ga or not gb:
        return 0.0
    return 2 * len(ga & gb) / (len(ga) + len(gb))


def _new_section(batch: str) -> str:
    return batch.split("## New turns", 1)[-1]


def messages(batch: str, prefix: str = "USER: ") -> list[str]:
    """The text of each new-turn line starting with *prefix*, which may be a regex.

    A message runs until the next line of any kind. Earlier context never counts.
    """
    new = _new_section(batch)
    out: list[str] = []
    for match in re.finditer(f"^(?:{prefix})", new, re.M):
        rest = new[match.end() :]
        nxt = _LINE_START.search(rest)
        out.append(rest[: nxt.start()] if nxt else rest)
    return out


def user_lines(batch: str) -> list[str]:
    """Each USER line of the new turns, normalised."""
    return [normalize(line) for line in messages(batch)]


def evidence_in_lines(evidence: str, lines: list[str]) -> bool:
    ev = normalize(evidence)
    if not ev:
        return False
    return any(ev in line or _overlap(ev, line) >= EVIDENCE_MATCH for line in lines)


def _turn_headers(batch: str) -> str:
    return " ".join(re.findall(r"^### Turn on (.+)$", batch, re.M))


def ungrounded_details(fact: CapturedFact, batch: str) -> list[str]:
    """Numbers and names in the content that neither the evidence nor a turn date gives.

    A flag, not a drop: a translated name or a resolved date can be correct and still
    miss here, so the dream sees the tag and checks the page instead.
    """
    support = fact.evidence + " " + _turn_headers(batch)
    support_norm = normalize(support)
    missing: list[str] = []
    for number in _NUMBER.findall(fact.content):
        if normalize(number) not in support_norm:
            missing.append(number)
    if not _CJK.search(fact.evidence):
        for name in _PROPER_NOUN.findall(fact.content):
            if name in _GENERIC_CAPITALS:
                continue
            if name.lower() not in support.lower():
                missing.append(name)
    return missing


@dataclass
class GateResult:
    kept: list[CapturedFact] = field(default_factory=list)
    dropped: list[tuple[str, CapturedFact]] = field(default_factory=list)
    # content -> details the content adds that its evidence does not hold
    ungrounded: dict[str, list[str]] = field(default_factory=dict)


def _drop_reason(
    fact: CapturedFact,
    users: list[str],
    rejected: list[str],
    known: list[str],
) -> Optional[str]:
    if fact.source == "agent_said":
        return "agent_said"
    if fact.kind == "experience":
        return "experience_channel"
    if fact.horizon == "ephemeral":
        return "ephemeral"
    if fact.kind == "user" and fact.source not in ("user_said", "user_did"):
        return "user_kind_wrong_source"
    if fact.kind == "user" and not evidence_in_lines(fact.evidence, users):
        return "evidence_not_in_user_line"
    if fact.source == "tool_output" and (
        fact.kind != "world" or not _CITATION.search(f"{fact.evidence} {fact.content}")
    ):
        return "tool_output_without_citation"
    if fact.source == "outcome" and fact.kind != "experience":
        return "outcome_not_experience"
    if _CONTEXT_FREE_CHOICE.search(fact.content):
        return "context_free_choice"
    body = normalize(fact.content)
    for claim in rejected:
        key = normalize(claim)
        if key and (key in body or body in key):
            return "rejected"
    if any(similarity(body, normalize(k)) >= RESTATEMENT_MATCH for k in known):
        return "restatement"
    return None


def gate(
    facts: list[CapturedFact],
    batch: str,
    *,
    rejected: Optional[list[str]] = None,
    known: Optional[list[str]] = None,
    cap: int = MAX_CANDIDATES,
) -> GateResult:
    """Drop what the labels prove is not a memory; keep the top *cap* of the rest."""
    users = user_lines(batch)
    result = GateResult()
    kept: list[CapturedFact] = []
    for fact in facts:
        reason = _drop_reason(fact, users, rejected or [], known or [])
        if reason:
            result.dropped.append((reason, fact))
        else:
            kept.append(fact)
    kept.sort(key=lambda f: -f.importance)
    result.kept = kept[:cap]
    result.dropped += [("over_cap", f) for f in kept[cap:]]
    for fact in result.kept:
        details = ungrounded_details(fact, batch)
        if details:
            result.ungrounded[fact.content] = details
    return result


def fact_tags(fact: CapturedFact, stale_after: Optional[str] = None) -> list[str]:
    """Tags written after the fact in the daily log, for the dream to route by."""
    tags = [f"kind:{fact.kind}", f"source:{fact.source}"]
    if fact.horizon == "dated":
        tags.append("dated")
        if stale_after:
            tags.append(f"stale_after:{stale_after}")
    return tags
