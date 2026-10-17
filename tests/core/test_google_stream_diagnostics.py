from collections.abc import AsyncIterator

import pytest
from google.genai.types import Candidate, Content, GenerateContentResponse, Part
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.providers.google import GoogleProvider

from suzent.core.providers import google_stream


async def test_chunk_diagnostics_include_empty_chunks_without_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records: list[str] = []
    monkeypatch.setattr(
        google_stream.logger,
        "debug",
        lambda message, *args: records.append(message.format(*args)),
    )
    closed = False

    async def source() -> AsyncIterator[GenerateContentResponse]:
        nonlocal closed
        try:
            yield GenerateContentResponse(response_id="response-1")
            yield GenerateContentResponse(
                candidates=[
                    Candidate(
                        content=Content(
                            parts=[
                                Part(text="private thought", thought=True),
                            ]
                        )
                    )
                ]
            )
            yield GenerateContentResponse(
                candidates=[
                    Candidate(
                        content=Content(parts=[Part(text="private answer")]),
                        finish_reason="STOP",
                    )
                ]
            )
        finally:
            closed = True

    model = google_stream.ObservedGoogleModel(
        "gemini-4-argon",
        provider=GoogleProvider(api_key="test-key"),
    )
    stream = await model._process_streamed_response(source(), ModelRequestParameters())
    events = [event async for event in stream]
    assert events
    assert closed
    assert any("chunk=1" in record and "response-1" in record for record in records)
    assert any("thought_parts=1" in record for record in records)
    assert any("STOP" in record for record in records)
    assert any("closed chunks=3" in record for record in records)
    assert all(
        "private" not in record and "test-key" not in record for record in records
    )


@pytest.mark.parametrize("effort", ["low", "medium", "high"])
def test_argon_unified_thinking_reaches_google_config(effort: str) -> None:
    model = google_stream.ObservedGoogleModel(
        "gemini-4-argon",
        provider=GoogleProvider(api_key="test-key"),
    )
    settings, parameters = model.prepare_request(
        {"thinking": effort},
        ModelRequestParameters(),
    )
    config = model._translate_thinking(settings or {}, parameters)
    assert config["thinking_level"] == effort.upper()
    assert config["include_thoughts"] is True
