"""The dream panel's LAST RESULT must show the agent's FINAL summary, not its opening.

process_turn_text concatenates every assistant text segment across a multi-step turn
(preamble + tool steps + final summary). _run_forked_agent watches the event stream and
keeps only the last contiguous text block — the post-final-tool-call summary.
"""

import pytest

from suzent.core.dream_runner import DREAM_CHAT_ID, DreamRunner
from suzent.core.stream_parser import TextChunk, ToolCall


@pytest.mark.asyncio
async def test_run_forked_agent_returns_last_text_block(monkeypatch):
    runner = DreamRunner()

    # Simulate: preamble text -> tool call -> more text -> tool call -> final summary.
    events = [
        TextChunk("I'll start by orienting myself — reading schema, index."),
        ToolCall("read_file", {}),
        TextChunk("Reading the logs now."),
        ToolCall("write_file", {}),
        TextChunk("Consolidated 14 logs: created 3 pages, flagged 1 conflict."),
    ]

    async def fake_process_turn_text(*args, on_event=None, **kwargs):
        for ev in events:
            await on_event(ev)
        # The real method returns the full concatenation (what we must NOT use).
        return "".join(e.content for e in events if isinstance(e, TextChunk))

    import suzent.core.chat_processor as cp

    class _FakeProcessor:
        process_turn_text = staticmethod(fake_process_turn_text)

    monkeypatch.setattr(cp, "ChatProcessor", _FakeProcessor)

    summary = await runner._run_forked_agent(DREAM_CHAT_ID, "sys", "msg")

    assert summary == "Consolidated 14 logs: created 3 pages, flagged 1 conflict."
    assert "orienting myself" not in summary


@pytest.mark.asyncio
async def test_run_forked_agent_falls_back_to_full_when_no_tools(monkeypatch):
    """If the agent emits one text block and no tool calls, return that text."""
    runner = DreamRunner()

    async def fake_process_turn_text(*args, on_event=None, **kwargs):
        await on_event(TextChunk("Nothing to consolidate."))
        return "Nothing to consolidate."

    import suzent.core.chat_processor as cp

    class _FakeProcessor:
        process_turn_text = staticmethod(fake_process_turn_text)

    monkeypatch.setattr(cp, "ChatProcessor", _FakeProcessor)

    summary = await runner._run_forked_agent(DREAM_CHAT_ID, "sys", "msg")
    assert summary == "Nothing to consolidate."


@pytest.mark.asyncio
async def test_run_forked_agent_caps_length(monkeypatch):
    runner = DreamRunner()
    long_text = "x" * 1000

    async def fake_process_turn_text(*args, on_event=None, **kwargs):
        await on_event(TextChunk(long_text))
        return long_text

    import suzent.core.chat_processor as cp

    class _FakeProcessor:
        process_turn_text = staticmethod(fake_process_turn_text)

    monkeypatch.setattr(cp, "ChatProcessor", _FakeProcessor)

    summary = await runner._run_forked_agent(DREAM_CHAT_ID, "sys", "msg")
    assert len(summary) <= 600
    assert summary.endswith("…")
