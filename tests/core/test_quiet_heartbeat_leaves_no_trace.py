"""A quiet heartbeat must leave no trace in the history a turn persists.

The stream's history already ended with the heartbeat prompt, so rolling back
to its starting length kept that prompt; the snapshot step then re-attached
the HEARTBEAT_OK reply to it, and the next ordinary turn rebuilt both into the
visible transcript.
"""

from types import SimpleNamespace

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from suzent.core.chat_processor import _history_to_snapshot
from suzent.streaming import roll_back_heartbeat


def _exchange(text: str) -> list:
    return [
        ModelRequest(parts=[UserPromptPart(content=f"ask {text}")]),
        ModelResponse(parts=[TextPart(content=f"answer {text}")]),
    ]


def test_rollback_drops_the_heartbeat_prompt_too() -> None:
    earlier = _exchange("earlier")
    prompt = ModelRequest(parts=[UserPromptPart(content="Background Heartbeat Check")])
    history = [
        *earlier,
        prompt,
        ModelResponse(parts=[TextPart(content="HEARTBEAT_OK")]),
    ]
    deps = SimpleNamespace(turn_start_index=len(earlier), last_messages=None)

    kept = roll_back_heartbeat(history, original_count=len(earlier) + 1, deps=deps)

    assert kept == earlier
    assert deps.last_messages == earlier
    assert deps.heartbeat_rolled_back is True


def test_rollback_without_a_recorded_start_keeps_the_old_behaviour() -> None:
    history = [*_exchange("a"), *_exchange("b")]
    deps = SimpleNamespace(last_messages=None)

    assert roll_back_heartbeat(history, original_count=2, deps=deps) == history[:2]


def test_a_rolled_back_heartbeat_does_not_get_its_reply_back() -> None:
    earlier = _exchange("earlier")
    deps = SimpleNamespace(is_suspended=False, heartbeat_rolled_back=True)

    assert _history_to_snapshot(earlier, "HEARTBEAT_OK", deps) == earlier


def test_an_ordinary_turn_still_keeps_a_missing_final_response() -> None:
    request = ModelRequest(parts=[UserPromptPart(content="hi")])
    deps = SimpleNamespace(is_suspended=False, heartbeat_rolled_back=False)

    saved = _history_to_snapshot([request], "hello", deps)

    assert isinstance(saved[-1], ModelResponse)
    assert saved[-1].parts[0].content == "hello"


class _UnavailableModelAgent:
    """Fails the way a retired model does: the provider answers 404."""

    def run_stream_events(self, _prompt, **_kwargs):
        raise RuntimeError("status_code: 404, model is no longer available")


async def test_a_failed_heartbeat_leaves_its_prompt_out_of_history(monkeypatch) -> None:
    from types import SimpleNamespace as NS
    from unittest.mock import AsyncMock

    from suzent import streaming
    from suzent.core.agent_deps import AgentDeps

    db = NS(get_chat=lambda _chat_id: None, update_chat=lambda *_a, **_k: True)
    monkeypatch.setattr("suzent.database.get_database", lambda: db)
    monkeypatch.setattr(streaming, "get_database", lambda: db)
    monkeypatch.setattr(streaming, "remove_pending_approvals", AsyncMock())
    monkeypatch.setattr(
        streaming._DraftDisplayAccumulator, "maybe_persist", AsyncMock()
    )

    earlier = _exchange("earlier")
    prompt = ModelRequest(parts=[UserPromptPart(content="Background Heartbeat Check")])
    deps = AgentDeps(chat_id="hb-fail", stateless=True)
    deps.turn_start_index = len(earlier)

    chunks = [
        chunk
        async for chunk in streaming.stream_agent_responses(
            _UnavailableModelAgent(),
            "",
            deps,
            message_history=[*earlier, prompt],
            chat_id="hb-fail",
            is_heartbeat=True,
        )
    ]

    assert chunks
    assert deps.last_messages == earlier
    assert deps.heartbeat_rolled_back is True


async def test_a_failed_ordinary_turn_keeps_the_users_message(monkeypatch) -> None:
    from types import SimpleNamespace as NS
    from unittest.mock import AsyncMock

    from suzent import streaming
    from suzent.core.agent_deps import AgentDeps

    db = NS(get_chat=lambda _chat_id: None, update_chat=lambda *_a, **_k: True)
    monkeypatch.setattr("suzent.database.get_database", lambda: db)
    monkeypatch.setattr(streaming, "get_database", lambda: db)
    monkeypatch.setattr(streaming, "remove_pending_approvals", AsyncMock())
    monkeypatch.setattr(
        streaming._DraftDisplayAccumulator, "maybe_persist", AsyncMock()
    )

    earlier = _exchange("earlier")
    question = ModelRequest(parts=[UserPromptPart(content="What changed?")])
    deps = AgentDeps(chat_id="turn-fail", stateless=True)
    deps.turn_start_index = len(earlier)

    async for _chunk in streaming.stream_agent_responses(
        _UnavailableModelAgent(),
        "",
        deps,
        message_history=[*earlier, question],
        chat_id="turn-fail",
    ):
        pass

    assert deps.heartbeat_rolled_back is False
