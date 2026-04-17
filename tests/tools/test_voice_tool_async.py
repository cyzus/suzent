from unittest.mock import AsyncMock, MagicMock

import pytest

from suzent.tools.voice_tool import SpeakTool


@pytest.mark.asyncio
async def test_forward_awaits_speech():
    tool = SpeakTool()

    mock_sink = MagicMock()
    mock_speech = MagicMock()
    mock_speech.speak = AsyncMock()
    tool._sink = mock_sink
    tool._speech = mock_speech

    result = await tool.forward("hello", prompt="cheerful")

    mock_speech.speak.assert_awaited_once_with("hello", prompt="cheerful")
    assert result.success
    assert result.message == "Spoke: hello"


@pytest.mark.asyncio
async def test_forward_returns_error_for_empty_text():
    tool = SpeakTool()

    result = await tool.forward("")

    assert not result.success
    assert result.message == "No text to speak."
