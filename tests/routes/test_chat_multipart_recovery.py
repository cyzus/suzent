"""A multipart /chat may opt into the recoverable protocol too.

Everything the JSON branch reads has to be read from the form as well: the
route's shared tail cannot reach for the JSON body, because on this path there
isn't one, and reaching for it turned a recoverable upload into a 500.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.datastructures import FormData
from starlette.requests import Request

from suzent.core import stream_registry
from suzent.routes.chat_routes import chat


@pytest.fixture(autouse=True)
def clean_registry():
    stream_registry.background_queues.clear()
    yield
    stream_registry.background_queues.clear()


def multipart_request(**fields: str) -> Request:
    request = MagicMock(spec=Request)
    request.headers = {"content-type": "multipart/form-data; boundary=x"}
    request.form = AsyncMock(return_value=FormData(list(fields.items())))
    return request


@patch("suzent.core.chat_processor.ChatProcessor.process_turn")
async def test_a_multipart_turn_streams_and_carries_its_name(mock_process_turn):
    async def mock_gen(*args, **kwargs):
        yield 'data: {"type": "TEXT_MESSAGE_CONTENT", "delta": "hi"}\n\n'

    mock_process_turn.side_effect = mock_gen

    response = await chat(
        multipart_request(
            message="hello",
            chat_id="chat",
            protocol="1",
            client_run_token="token-for-this-turn",
        )
    )

    assert response.status_code == 200
    queue = stream_registry.get_background_queue("chat")
    assert queue is not None
    assert queue.replay.client_token == "token-for-this-turn"
