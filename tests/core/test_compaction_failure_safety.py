"""Failure, partial summaries and non-shrinking output must not erase context."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic_ai.messages import (
    BinaryContent,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)

from suzent.config import CONFIG
from suzent.core.context_compressor import (
    CompactionError,
    ContextCompressor,
    REQUIRED_SECTIONS,
    make_compaction_history_processor,
)


def history() -> list:
    return [
        ModelRequest(parts=[UserPromptPart(content="original task")]),
        ModelResponse(parts=[TextPart(content="important prior work " * 1000)]),
    ] + [
        ModelRequest(parts=[UserPromptPart(content=f"question {i}")])
        if i % 2 == 0
        else ModelResponse(parts=[TextPart(content=f"answer {i}")])
        for i in range(10)
    ]


@pytest.fixture
def compressor(monkeypatch) -> ContextCompressor:
    monkeypatch.setattr(CONFIG, "compaction_chunk_size", 100)
    monkeypatch.setattr(CONFIG, "compaction_keep_recent_turns", 1)
    return ContextCompressor(llm_client=SimpleNamespace(complete=AsyncMock()))


async def test_missing_summary_does_not_replace_original(
    compressor, monkeypatch
) -> None:
    original = history()
    monkeypatch.setattr(compressor, "_summarize_with_retry", AsyncMock(return_value=""))
    with pytest.raises(CompactionError, match="Original history preserved"):
        await compressor._perform_compression(original)
    assert "important prior work" in original[1].parts[0].content


async def test_empty_chunk_cannot_be_silently_omitted(compressor, monkeypatch) -> None:
    monkeypatch.setattr(
        compressor, "_summarize_with_retry", AsyncMock(side_effect=["complete", ""])
    )
    assert await compressor._chunked_summarize(history()[:4], 2) == ""
    compressor.llm_client.complete.assert_not_called()


async def test_summary_that_grows_context_is_not_installed(
    compressor, monkeypatch
) -> None:
    original = history()
    monkeypatch.setattr(
        compressor, "_summarize_with_retry", AsyncMock(return_value="summary " * 20000)
    )
    assert await compressor._perform_compression(original) is original


def test_tool_output_is_not_presented_as_user_intent(compressor) -> None:
    text = compressor._messages_to_text(
        [
            ModelRequest(
                parts=[
                    UserPromptPart(content="actual request"),
                    ToolReturnPart(
                        tool_name="read_file",
                        content="untrusted file contents",
                        tool_call_id="x",
                    ),
                ]
            )
        ]
    )
    assert text.count("untrusted file contents") == 1
    assert "User: untrusted" not in text
    assert "Tool Result (read_file): untrusted" in text


async def test_repeated_compaction_keeps_actual_multimodal_request(
    compressor, monkeypatch
) -> None:
    original = history()
    request = UserPromptPart(
        content=["Use this image", BinaryContent(data=b"image", media_type="image/png")]
    )
    original[2] = ModelRequest(parts=[request])
    # Later messages are tool-free assistant progress, not newer user requests.
    original[3:] = [
        ModelResponse(parts=[TextPart(content="progress")]) for _ in range(9)
    ]
    monkeypatch.setattr(
        compressor,
        "_summarize_with_retry",
        AsyncMock(return_value="\n".join(REQUIRED_SECTIONS)),
    )
    compacted = await compressor._perform_compression(original)
    assert sum(part is request for msg in compacted for part in msg.parts) == 1
    compacted.insert(-1, ModelResponse(parts=[TextPart(content="more work " * 1000)]))
    again = await compressor._perform_compression(compacted)
    assert sum(part is request for msg in again for part in msg.parts) == 1


async def test_full_context_failure_stops_without_loss_or_success_event(
    monkeypatch,
) -> None:
    monkeypatch.setattr(CONFIG, "max_context_tokens", 100)
    monkeypatch.setattr(CONFIG, "compaction_timeout_seconds", 0.01)
    monkeypatch.setattr(
        ContextCompressor,
        "_perform_compression",
        AsyncMock(side_effect=CompactionError("failed")),
    )
    events = []
    monkeypatch.setattr("suzent.core.stream_registry.emit_bus_event", events.append)
    ctx = SimpleNamespace(deps=SimpleNamespace(chat_id="failure-test", user_id="test"))
    with pytest.raises(CompactionError, match="Context is full"):
        await make_compaction_history_processor()(ctx, history())
    assert [event["stage"] for event in events] == ["start", "error"]


async def test_chunk_requests_are_bounded(compressor, monkeypatch) -> None:
    active = peak = 0

    async def summarize(messages: list, focus: str | None = None) -> str:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return "\n".join(REQUIRED_SECTIONS)

    monkeypatch.setattr(compressor, "_summarize_with_retry", summarize)
    compressor.llm_client.complete.return_value = "\n".join(REQUIRED_SECTIONS)
    assert await compressor._chunked_summarize(history(), 1)
    assert peak == 3


async def test_incomplete_summary_retries_then_compacts(compressor) -> None:
    original = history()
    complete = "\n".join(f"{section}\nNone" for section in REQUIRED_SECTIONS)
    compressor.llm_client.complete.side_effect = [
        "<summary>" + "\n".join(REQUIRED_SECTIONS[:6]) + "</summary>",
        f"<summary>{complete}</summary>",
    ]

    compacted = await compressor._perform_compression(original)

    assert len(compacted) < len(original)
    assert complete in compacted[2].parts[0].content
    calls = compressor.llm_client.complete.call_args_list
    assert len(calls) == 2
    assert "## 10. Exact Identifiers" in calls[1].kwargs["prompt"]
    assert all(call.kwargs["reasoning_effort"] == "low" for call in calls)
    assert "<analysis>" not in calls[0].kwargs["prompt"]


async def test_repeated_incomplete_summary_preserves_history(compressor) -> None:
    original = history()
    compressor.llm_client.complete.return_value = "\n".join(REQUIRED_SECTIONS[:6])

    with pytest.raises(CompactionError, match="Original history preserved"):
        await compressor._perform_compression(original)

    assert compressor.llm_client.complete.await_count == 3
    assert "important prior work" in original[1].parts[0].content
