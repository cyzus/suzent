"""Experience capture: lessons tied to a failure and the fix that followed it.

The user-fact pass reads what the user said, so it never sees the agent get something
wrong and then find what works. That is where lessons come from, and it happens in
scheduled and background turns as much as in chats. A batch reaches the model here only
when a cheap check finds a failure or a correction in it, and a lesson survives the gate
only when the batch shows both the failure and the fix.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, Field

from suzent.memory import capture

MAX_LESSONS = 3
# Share of a lesson's character bigrams that must occur in a known memory for it to
# count as that memory happening again.
REPEAT_MATCH = 0.8

_FAILURE = re.compile(
    r"(error|exception)\b|\b(errno|traceback|failed|failure|denied|refused|root cause)\b"
    r"|\bexit (code|status) [1-9]|报错|失败|出错|错误|被拒|拒绝|根因",
    re.I,
)
_CORRECTION = re.compile(
    r"不对|不是这样|错了|改回|还原|撤销|不行|\b(wrong|revert|undo|change it back"
    r"|that's not|doesn't work|still broken)\b",
    re.I,
)
_ANY_LINE = "USER: |ASSISTANT: |ACTION: "
_GENERIC_SCOPES = frozenset(
    {"", "general", "any", "all", "everywhere", "global", "none", "n/a", "unknown"}
)


def has_signal(batch: str) -> bool:
    """Whether the new turns show a failure, or the user correcting the agent."""
    if any(_FAILURE.search(m) for m in capture.messages(batch, "ASSISTANT: |ACTION: ")):
        return True
    return any(_CORRECTION.search(m) for m in capture.messages(batch))


class Lesson(BaseModel):
    """One candidate lesson, with the words that show it failed and then worked."""

    situation: str = Field(..., description="What was being done, one short phrase")
    attempt: str = Field(..., description="What was tried first and failed")
    outcome: str = Field(..., description="What worked instead, and how that showed")
    lesson: str = Field(..., description="What to do next time, as an instruction")
    scope: str = Field(
        ..., description="Where it applies: a repository, a tool or an environment"
    )
    evidence_fail: str = Field(..., description="Verbatim words showing the failure")
    evidence_fix: str = Field(..., description="Verbatim words showing the fix worked")
    importance: float = Field(0.5, ge=0.0, le=1.0)

    @property
    def content(self) -> str:
        return (
            f"{self.lesson.rstrip('.')} (when {self.situation}: {self.attempt} "
            f"failed; {self.outcome})"
        )

    @property
    def scope_tag(self) -> str:
        return "scope:" + re.sub(r"\s+", "-", self.scope.strip().lower())

    @property
    def evidence(self) -> str:
        return f"{self.evidence_fail} … {self.evidence_fix}"


class LessonResponse(BaseModel):
    lessons: list[Lesson] = Field(default_factory=list)


EXPERIENCE_SYSTEM_PROMPT = """You are the experience step of a personal agent's memory. You read a batch of
conversation turns in which something went wrong at least once, and look for lessons the
agent should carry into future work. Most failures teach nothing that lasts; an empty list
is the normal answer.

The batch has lines of three kinds, and any of them can be evidence here:
- USER: what the user typed, including corrections of the agent.
- ASSISTANT: what the agent wrote, including what it found and what it did about it.
- ACTION: a tool call the agent made and its output: errors, test runs, command results.

## A lesson needs all of these
- evidence_fail: exact words from the batch that show the failure: an error, a rejected
  command, a failing check, or the user saying the result is wrong.
- evidence_fix: exact words from later in the batch that show what worked: a command
  that then succeeded, checks that passed, the user accepting the change. If the batch
  never shows the fix, there is no lesson, however obvious the cause seems.
- lesson: what to do next time, as an instruction someone could follow without reading
  the batch. "Run Python scripts with `python -X utf8` on this Windows machine", not
  "Encoding can cause problems".
- scope: where it applies, in one to four words: a repository ("suzent repo"), a tool
  ("gh CLI"), or an environment ("Windows shell", "background sessions").
- situation, attempt, outcome: one short phrase each.

Each evidence field is one passage copied from a single line of the batch. Never join
words from two lines, and never quote an earlier line's words as if a later one said them.

The strongest lessons are where the agent names the cause of a failure ("root cause",
"根因", "the problem was") and the batch then shows the fix working, including the user
accepting the result. Check every such passage.

## Not a lesson
- A one-off failure with no cause that will recur: an expired login, a flaky network,
  a service that was down, a typo.
- A failure the batch leaves unresolved.
- A correction that only states the user's taste ("make it grey"). That is a user
  preference, handled elsewhere. Propose a lesson from a correction only when it shows
  something the agent did wrong that will happen again (a wrong coordinate convention,
  editing the wrong file).
- The task itself: what was built, decided or shipped.

## Rules
- One lesson per cause. Two errors with one cause are one lesson.
- At most 3 lessons per batch; keep the ones most likely to recur.
- Turns marked as earlier context were already processed. Use them to understand the
  new turns; never take evidence from them.
- Write every field except the evidence in the language the user writes in: the language
  of the USER lines, or the one most of them use. Errors, logs and ASSISTANT lines do not
  decide it; with no USER line, write in English. Commands, paths and error text stay as
  they are. The evidence stays verbatim, 5 to 40 words.

## Already in memory
The prompt may list memories that already exist. When the batch shows one of their
lessons happening again, propose it anyway, worded as listed: a lesson that keeps
recurring is the one most worth keeping. Never propose a listed memory the batch does
not show again.
"""


def format_experience_prompt(batch: str, known: Optional[list[str]] = None) -> str:
    block = ""
    if known:
        lines = "\n".join(f"- {k}" for k in known)
        block = f"## Already in memory\n{lines}\n\n"
    return f"""Propose lessons from this batch.

{block}---
{batch}
---

Return JSON with a "lessons" array; an empty array when nothing qualifies."""


@dataclass
class LessonGateResult:
    kept: list[Lesson] = field(default_factory=list)
    # a lesson already in memory, shown again, with the memory it matched
    repeated: list[tuple[Lesson, str]] = field(default_factory=list)
    dropped: list[tuple[str, Lesson]] = field(default_factory=list)


def _shown(evidence: str, lines: list[str]) -> bool:
    """Whether one message holds the evidence. Command output runs over several lines,
    so a quote may skip some of them; each quoted line must still be in that message."""
    pieces = [p for p in evidence.splitlines() if capture.normalize(p)]
    return bool(pieces) and any(
        all(capture.evidence_in_lines(p, [line]) for p in pieces) for line in lines
    )


def _drop_reason(
    lesson: Lesson, lines: list[str], rejected: list[str]
) -> Optional[str]:
    fail = capture.normalize(lesson.evidence_fail)
    if (
        not _shown(lesson.evidence_fail, lines)
        or not _shown(lesson.evidence_fix, lines)
        or fail == capture.normalize(lesson.evidence_fix)
    ):
        return "no_outcome"
    if lesson.scope.strip().lower() in _GENERIC_SCOPES:
        return "no_scope"
    body = capture.normalize(lesson.lesson)
    for claim in rejected:
        key = capture.normalize(claim)
        if key and (key in body or body in key):
            return "rejected"
    return None


def gate(
    lessons: list[Lesson],
    batch: str,
    *,
    rejected: Optional[list[str]] = None,
    known: Optional[list[str]] = None,
    cap: int = MAX_LESSONS,
) -> LessonGateResult:
    """Keep the lessons the batch shows failing and then working; mark repeats."""
    lines = [capture.normalize(m) for m in capture.messages(batch, _ANY_LINE)]
    result = LessonGateResult()
    fresh: list[Lesson] = []
    for lesson in lessons:
        reason = _drop_reason(lesson, lines, rejected or [])
        if reason:
            result.dropped.append((reason, lesson))
            continue
        body = capture.normalize(lesson.lesson)
        match = next(
            (
                k
                for k in known or []
                if capture._overlap(body, capture.normalize(k)) >= REPEAT_MATCH
            ),
            None,
        )
        if match:
            result.repeated.append((lesson, match))
        else:
            fresh.append(lesson)
    fresh.sort(key=lambda lesson: -lesson.importance)
    result.kept = fresh[:cap]
    result.dropped += [("over_cap", lesson) for lesson in fresh[cap:]]
    return result
