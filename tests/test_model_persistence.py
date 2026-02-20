"""
Tests for model persistence logic in chat routes and SocialBrain.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from suzent.core.social_brain import SocialBrain
from suzent.routes.chat_routes import chat


@pytest.fixture
def mock_db():
    with patch("suzent.routes.chat_routes.get_database") as mock:
        db = MagicMock()
        mock.return_value = db
        # Setup default user preferences
        prefs = MagicMock()
        prefs.model = "test-provider/test-model"
        prefs.agent = "TestAgent"
        prefs.tools = ["TestTool"]
        db.get_user_preferences.return_value = prefs
        yield db


@patch("suzent.core.chat_processor.ChatProcessor.process_turn")
async def test_chat_route_uses_user_prefs(mock_process_turn, mock_db):
    """Test that /chat endpoint falls back to user preferences when config is empty."""
    from starlette.requests import Request

    # Mock request with empty config
    request = MagicMock(spec=Request)
    request.headers = {"content-type": "application/json"}
    request.json = AsyncMock(return_value={"message": "hello", "config": {}})

    # Mock generator to avoid actual processing
    async def mock_gen(*args, **kwargs):
        yield 'data: {"type": "final_answer", "data": "response"}\n\n'

    mock_process_turn.side_effect = mock_gen

    await chat(request)

    # Verify process_turn was called with config containing user prefs
    call_args = mock_process_turn.call_args[1]  # kwargs
    config = call_args["config_override"]

    assert config["model"] == "test-provider/test-model"
    assert config["agent"] == "TestAgent"
    assert config["tools"] == ["TestTool"]


@patch("suzent.core.social_brain.get_database")
@patch("suzent.core.chat_processor.ChatProcessor.process_turn")
async def test_social_brain_uses_user_prefs(mock_process_turn, mock_get_db):
    """Test that SocialBrain falls back to user preferences if no model configured."""
    # Setup mock DB for SocialBrain
    db = MagicMock()
    mock_get_db.return_value = db
    prefs = MagicMock()
    prefs.model = "social-prefer-model"
    db.get_user_preferences.return_value = prefs

    # Mock channel manager and message
    channel_manager = MagicMock()
    message = MagicMock()
    message.platform = "telegram"
    message.sender_id = "user123"
    message.sender_name = "User"
    message.content = "hello"
    message.attachments = []
    message.get_chat_id.return_value = "telegram:123"

    # Mock generator
    async def mock_gen(*args, **kwargs):
        yield 'data: {"type": "final_answer", "data": "response"}\n\n'

    mock_process_turn.side_effect = mock_gen

    # Initialize SocialBrain with NO model
    brain = SocialBrain(
        channel_manager=channel_manager,
        model=None,  # This should trigger fallback
    )

    # We need to mock _ensure_chat_exists to avoid real DB call
    brain._ensure_chat_exists = MagicMock()

    await brain._handle_message(message)

    # Verify config passed to processor has user pref model
    call_args = mock_process_turn.call_args[1]
    config = call_args["config_override"]

    assert config["model"] == "social-prefer-model"
