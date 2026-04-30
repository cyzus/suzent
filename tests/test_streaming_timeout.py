import asyncio

import pytest

from suzent import streaming


class _HangingStreamAgent:
    async def run_stream_events(self, _prompt, **_kwargs):
        await asyncio.Event().wait()
        yield None


async def test_stream_events_timeout_when_first_event_never_arrives(monkeypatch):
    monkeypatch.setattr(streaming, "_FIRST_STREAM_EVENT_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(TimeoutError, match="Timed out waiting for LLM stream"):
        async for _event in streaming._iter_stream_events_with_timeout(
            _HangingStreamAgent(), "hi", {}
        ):
            pass
