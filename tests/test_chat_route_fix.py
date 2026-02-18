"""Tests for chat route streaming and non-streaming modes."""

from unittest.mock import patch

from starlette.testclient import TestClient

from suzent.server import app

client = TestClient(app)


@patch("suzent.core.chat_processor.ChatProcessor.process_turn")
def test_chat_non_streaming(mock_process_turn):
    async def mock_generator(*args, **kwargs):
        yield 'data: {"type": "chunk", "data": "Hello"}\n\n'
        yield 'data: {"type": "final_answer", "data": "Hello world"}\n\n'

    mock_process_turn.return_value = mock_generator()

    # Test stream=False via JSON
    response = client.post(
        "/chat",
        json={"message": "hi", "stream": False},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert "response" in data
    assert data["response"] == "Hello world"


@patch("suzent.core.chat_processor.ChatProcessor.process_turn")
def test_chat_streaming_default(mock_process_turn):
    async def mock_generator(*args, **kwargs):
        yield 'data: {"type": "test"}\n\n'

    mock_process_turn.return_value = mock_generator()

    # Test default (stream=True)
    response = client.post(
        "/chat",
        json={"message": "hi"},
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
