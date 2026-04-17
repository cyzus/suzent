"""Unit tests for memory system models (suzent.memory.models)."""

import pytest

from suzent.memory.models import (
    AgentAction,
    ConversationTurn,
    ExtractedFact,
    MemoryExtractionResult,
    Message,
)


class TestMessage:
    """Tests for Message model."""

    def test_message_creation(self):
        """Test Message model creation."""
        msg = Message(role="user", content="Hello")

        assert msg.role == "user"
        assert msg.content == "Hello"


class TestAgentAction:
    """Tests for AgentAction model."""

    def test_agent_action_creation(self):
        """Test AgentAction model creation."""
        action = AgentAction(tool="bash", args={"command": "ls"}, output="file1 file2")

        assert action.tool == "bash"
        assert action.args["command"] == "ls"
        assert action.output == "file1 file2"

    def test_agent_action_defaults(self):
        """Test AgentAction with default values."""
        action = AgentAction(tool="test_tool")

        assert action.tool == "test_tool"
        assert action.args == {}
        assert action.output is None


class TestExtractedFact:
    """Tests for ExtractedFact model."""

    def test_extracted_fact_creation(self):
        """Test ExtractedFact model creation."""
        fact = ExtractedFact(
            content="User prefers Python",
            category="preference",
            importance=0.8,
            tags=["programming", "python"],
        )

        assert fact.content == "User prefers Python"
        assert fact.category == "preference"
        assert fact.importance == 0.8
        assert len(fact.tags) == 2

    def test_extracted_fact_importance_validation(self):
        """Test ExtractedFact importance validation."""
        with pytest.raises(Exception):  # Pydantic validation error
            ExtractedFact(content="test", importance=1.5)

        with pytest.raises(Exception):  # Pydantic validation error
            ExtractedFact(content="test", importance=-0.1)


class TestMemoryExtractionResult:
    """Tests for MemoryExtractionResult model."""

    def test_memory_extraction_result_empty(self):
        """Test MemoryExtractionResult.empty() factory."""
        result = MemoryExtractionResult.empty()

        assert result.extracted_facts == []
        assert result.memories_created == []
        assert result.memories_updated == []
        assert result.conflicts_detected == []


class TestConversationTurn:
    """Tests for ConversationTurn model."""

    def test_conversation_turn_from_dict(self):
        """Test ConversationTurn.from_dict()."""
        data = {
            "user_message": {"role": "user", "content": "Hello"},
            "assistant_message": {"role": "assistant", "content": "Hi there"},
            "agent_actions": [{"tool": "bash", "args": {"cmd": "ls"}, "output": "ok"}],
            "agent_reasoning": ["First step", "Second step"],
        }

        turn = ConversationTurn.from_dict(data)

        assert turn.user_message.content == "Hello"
        assert turn.assistant_message.content == "Hi there"
        assert len(turn.agent_actions) == 1
        assert turn.agent_actions[0].tool == "bash"
        assert len(turn.agent_reasoning) == 2

    def test_conversation_turn_format_for_extraction(self):
        """Test ConversationTurn.format_for_extraction()."""
        turn = ConversationTurn(
            user_message=Message(role="user", content="What is 2+2?"),
            assistant_message=Message(role="assistant", content="The answer is 4"),
            agent_actions=[
                AgentAction(tool="calculator", args={"expr": "2+2"}, output="4")
            ],
            agent_reasoning=["Need to calculate 2+2"],
        )

        formatted = turn.format_for_extraction()

        assert "What is 2+2?" in formatted
        assert "The answer is 4" in formatted
        assert "calculator" in formatted
        assert "Need to calculate 2+2" in formatted
