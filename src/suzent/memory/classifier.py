"""Classify an extracted fact against what memory already holds.

Issue #34 was write-time deduplication silently dropping an *update*, so the write
path has been strictly append-only ever since: every extracted fact goes to the daily
log, and the dream resolves repetition later. That is safe, and it is also why the
same claim can occupy a hundred rows — each retelling is a fresh row that competes
with the original in retrieval.

This module lets the write path recognise the one case where appending adds nothing:
the fact is a re-statement of a claim that is *already durably recorded*, in the same
words, with no new specifics. Those become a line in a confirmations sidecar — the
recurrence is kept as evidence, the redundant row is not created.

Everything else, including anything that merely *looks* similar, keeps the old
behaviour. The asymmetry is deliberate: a redundant row costs a little ranking
quality, a dropped revision costs a fact.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

# Same claim, same words -> a confirmation, provided it adds no new specifics.
CONFIRM_SIMILARITY = 0.97

# Close but not identical -> a revision. Written to the log exactly as before; the
# threshold exists so the dream can be told which claim it revises.
REVISION_SIMILARITY = 0.90

# A statement that says everything the old one said and then some is a revision even
# when the extra words push the symmetric similarity down. "Moved to Berlin in 2024"
# only overlaps "moved to Berlin" by 0.8 Dice, but it is plainly the same claim,
# updated -- which is precisely the case that must never be mistaken for a repeat.
REVISION_COVERAGE = 0.90

# Words that carry no claim content, so their presence or absence should not make two
# statements of the same fact look different.
_STOPWORDS = frozenset(
    """a an the and or but if then than that this these those is are was were be been
    being am do does did doing have has had having of in on at to for with from by as
    it its his her their our my your user users he she they we you i not no also very
    just really quite so such about into over under again more most some any each""".split()
)

# Anything that pins a claim down: numbers, dates, versions, money, times, identifiers,
# paths, URLs, emails, and quoted strings. A token like this appearing in the new
# statement but not the old one means the new statement says something more, however
# similar the surrounding prose is.
_SPECIFIC_RE = re.compile(
    r"""(?:
        [\w.+-]+@[\w-]+\.[\w.]+          # email
      | \w+://\S+                        # url
      | [A-Za-z]:[\\/][^\s,;]+           # windows path
      | /[^\s,;]{2,}                     # posix path
      | \d[\w.:/-]*                      # anything starting with a digit
      | "[^"]+"                          # quoted string
    )""",
    re.VERBOSE,
)

_WORD_RE = re.compile(r"[\w'-]+", re.UNICODE)


@dataclass
class ClaimVerdict:
    """What the write path should do with one extracted fact."""

    kind: str  # "confirmation" | "revision" | "new"
    similarity: float = 0.0
    matched: str = ""
    new_specifics: List[str] = field(default_factory=list)

    @property
    def is_confirmation(self) -> bool:
        return self.kind == "confirmation"

    @property
    def is_revision(self) -> bool:
        return self.kind == "revision"


def normalize_claim(text: str) -> str:
    """Lowercase, collapse whitespace, and drop the daily log's `- [category] ` prefix."""
    t = " ".join((text or "").split())
    t = re.sub(r"^-\s*", "", t)
    t = re.sub(r"^\[[^\]]+\]\s*", "", t)
    return t.lower()


def _content_tokens(text: str) -> List[str]:
    return [w for w in _WORD_RE.findall(normalize_claim(text)) if w not in _STOPWORDS]


def claim_similarity(a: str, b: str) -> float:
    """Dice coefficient over content words, in [0.0, 1.0].

    Deliberately lexical rather than semantic. An embedding comparison would cost a
    call per fact per turn, and the only band that changes behaviour here is
    "practically the same sentence" — which is exactly what a lexical measure is good
    at, and exactly what a semantic one is too generous about. Two different facts on
    the same topic are ~0.9 cosine apart and nowhere near identical in words.
    """
    ta, tb = set(_content_tokens(a)), set(_content_tokens(b))
    if not ta or not tb:
        return 0.0
    return 2 * len(ta & tb) / (len(ta) + len(tb))


def claim_coverage(new: str, old: str) -> float:
    """How much of *old*'s content the *new* statement restates, in [0.0, 1.0]."""
    tn, to = set(_content_tokens(new)), set(_content_tokens(old))
    if not to:
        return 0.0
    return len(tn & to) / len(to)


def new_specifics(new: str, old: str) -> List[str]:
    """Specific tokens the new statement has and the old one does not.

    This is the guard that keeps "moved to Berlin in 2024" from being folded into
    "moved to Berlin" as a mere repeat.
    """
    old_tokens = {t.lower() for t in _SPECIFIC_RE.findall(normalize_claim(old))}
    out = []
    for t in _SPECIFIC_RE.findall(normalize_claim(new)):
        if t.lower() not in old_tokens and t not in out:
            out.append(t)
    return out


def classify_fact(content: str, known: Optional[List[str]]) -> ClaimVerdict:
    """Compare one extracted fact against the nearest known facts.

    *known* is the recall set already assembled for the extraction prompt, so this
    costs no extra retrieval. Only claims the caller knows to be durably recorded
    should be passed — see `MemoryManager._recall_known_facts`.
    """
    best_score, best_text = 0.0, ""
    for candidate in known or []:
        score = claim_similarity(content, candidate)
        if score > best_score:
            best_score, best_text = score, candidate

    specifics = new_specifics(content, best_text) if best_text else []
    superset = (
        bool(specifics) and claim_coverage(content, best_text) >= REVISION_COVERAGE
    )
    if best_score < REVISION_SIMILARITY and not superset:
        return ClaimVerdict(kind="new", similarity=best_score, matched=best_text)

    if best_score >= CONFIRM_SIMILARITY and not specifics:
        return ClaimVerdict(
            kind="confirmation", similarity=best_score, matched=best_text
        )

    # Similar but not identical, or identical prose carrying a new detail. Either way
    # it may be an update, so it is written exactly as before.
    return ClaimVerdict(
        kind="revision",
        similarity=best_score,
        matched=best_text,
        new_specifics=specifics,
    )
