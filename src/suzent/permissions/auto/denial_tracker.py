from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DenialState:
    consecutive: int = 0
    total: int = 0


MAX_CONSECUTIVE_DENIALS = 3
MAX_TOTAL_DENIALS = 20
_states: dict[str, DenialState] = {}


def record_allowed(chat_id: str) -> DenialState:
    state = _states.setdefault(chat_id, DenialState())
    state.consecutive = 0
    return state


def record_denied(chat_id: str) -> DenialState:
    state = _states.setdefault(chat_id, DenialState())
    state.consecutive += 1
    state.total += 1
    return state


def limit_exceeded(state: DenialState) -> bool:
    return (
        state.consecutive >= MAX_CONSECUTIVE_DENIALS or state.total >= MAX_TOTAL_DENIALS
    )


def clear_denial_state(chat_id: str) -> None:
    _states.pop(chat_id, None)
