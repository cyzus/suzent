"""Tool-result trimming must leave the previously sent prefix byte-identical.

The trimmed history is what the run returns and what gets persisted, so next
turn it is sent again with new messages after it. Any rewrite inside that
resent part — a boundary that moves one message per turn, or a re-trim of an
already trimmed result — throws away the provider's cached prefix.
"""

import pytest
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from suzent.core.context_compressor import TokenBudget, ToolResultTrimmer

BIG = "x" * 5000
BUDGET = TokenBudget(estimated_tokens=0, limit=1)


def _tool_round(n: int) -> list:
    call_id = f"call-{n}"
    return [
        ModelResponse(
            parts=[ToolCallPart(tool_name="read", args={}, tool_call_id=call_id)]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="read", content=f"{n}:{BIG}", tool_call_id=call_id
                )
            ]
        ),
    ]


def _turn(n: int, rounds: int) -> list:
    messages: list = [ModelRequest(parts=[UserPromptPart(content=f"turn {n}")])]
    for r in range(rounds):
        messages += _tool_round(n * 100 + r)
    return messages


def _wire(messages: list) -> list[bytes]:
    """Each message as the bytes that identify it, minus volatile timestamps."""
    dumped = ModelMessagesTypeAdapter.dump_python(messages, mode="json")
    for message in dumped:
        message.pop("timestamp", None)
        for part in message.get("parts", []):
            part.pop("timestamp", None)
    return [repr(m).encode() for m in dumped]


@pytest.mark.parametrize("trim", ["apply_soft_trim", "apply_hard_clear"])
def test_most_turns_resend_the_previous_request_unchanged(trim):
    apply = getattr(ToolResultTrimmer, trim)
    history: list = []
    previous: list[bytes] | None = None
    unchanged = changed = 0

    for n in range(40):
        history = apply(history + _turn(n, rounds=2), BUDGET)
        sent = _wire(history)
        if previous is not None:
            if sent[: len(previous)] == previous:
                unchanged += 1
            else:
                changed += 1
        # Persisted as trimmed: the run returns the history it was given.
        previous = sent

    # 5 messages per turn against a 16-message step: the boundary moves on
    # roughly one turn in three, where it used to move on every turn.
    assert changed <= 40 * 5 // ToolResultTrimmer.TRIM_STEP + 1
    assert unchanged > 2 * changed


def test_cutoff_moves_only_in_whole_steps():
    cutoffs = {ToolResultTrimmer.trim_cutoff(n) for n in range(200)}

    assert all(c % ToolResultTrimmer.TRIM_STEP == 0 for c in cutoffs)


def test_soft_trim_leaves_trimmed_results_alone():
    """Re-trimming rewrote the marker on the next two turns, twice per result."""
    history = _turn(0, rounds=3) + _turn(1, rounds=3) + _turn(2, rounds=3) * 3

    once = ToolResultTrimmer.apply_soft_trim(history, BUDGET)
    twice = ToolResultTrimmer.apply_soft_trim(once, BUDGET)

    assert _wire(twice) == _wire(once)
    assert any(
        "chars trimmed" in str(part.content)
        for message in once
        for part in getattr(message, "parts", [])
        if isinstance(part, ToolReturnPart)
    )


def test_untouched_messages_are_passed_through_as_is():
    history = _turn(0, rounds=1)

    assert ToolResultTrimmer.apply_soft_trim(history, BUDGET)[0] is history[0]
