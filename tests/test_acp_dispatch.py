import pytest
import json
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from suzent.tools.agent_tool import AgentTool
from suzent.core.agent_deps import AgentDeps
from suzent.core.agent_inbox import AgentInboxDispatcher
from suzent.acp.runtime import stream_acp_turn
from pydantic_ai import RunContext


@pytest.mark.asyncio
async def test_agent_tool_acp_dispatch():
    # Test (1) and (2)
    tool = AgentTool()
    ctx = MagicMock(spec=RunContext)
    ctx.deps = MagicMock(spec=AgentDeps)
    ctx.deps.chat_id = "test-chat"

    with patch(
        "suzent.core.subagent_runner.spawn_subagent", new_callable=AsyncMock
    ) as mock_spawn:
        mock_task = MagicMock()
        mock_task.task_id = "task-1"
        mock_task.chat_id = "chat-1"
        mock_task.parent_chat_id = "test-chat"
        mock_task.status = "spawned"
        mock_task.tools_allowed = []
        mock_task.error = None
        mock_task.result_summary = ""
        mock_spawn.return_value = mock_task

        # (1) runtime='acp' with acp_agent_id and no subagent_type/tools
        await tool.forward(
            ctx, description="do acp stuff", runtime="acp", acp_agent_id="claude-code"
        )
        assert mock_spawn.called
        kwargs = mock_spawn.call_args[1]
        assert kwargs["runtime"] == "acp"
        assert kwargs["acp_agent_id"] == "claude-code"
        assert kwargs["tools_allowed"] == []
        assert kwargs["subagent_type"] is None

        # (2) runtime='acp' + model_override returns invalid argument and does not spawn
        mock_spawn.reset_mock()
        res2 = await tool.forward(
            ctx,
            description="do acp stuff",
            runtime="acp",
            acp_agent_id="claude-code",
            model_override="gpt-4",
        )
        assert not mock_spawn.called
        assert res2.success is False
        assert res2.error_code.value == "invalid_argument"
        assert "model_override is not supported when runtime='acp'" in res2.message


@pytest.mark.asyncio
async def test_inbox_dispatcher_acp_vs_native():
    # Test (3) and (4)
    dispatcher = AgentInboxDispatcher()

    chat_acp = MagicMock()
    chat_acp.config = {"runtime": "acp"}

    chat_native = MagicMock()
    chat_native.config = {"runtime": "native"}

    def get_chat_side_effect(chat_id):
        if chat_id == "chat_acp":
            return chat_acp
        if chat_id == "chat_native":
            return chat_native
        return None

    with patch("suzent.core.agent_inbox.get_database") as mock_get_db:
        mock_db = MagicMock()
        mock_db.get_chat.side_effect = get_chat_side_effect
        mock_get_db.return_value = mock_db

        msg_acp = {
            "message_id": "m1",
            "target_chat_id": "chat_acp",
            "content": "hello acp",
        }

        msg_native = {
            "message_id": "m2",
            "target_chat_id": "chat_native",
            "content": "hello native",
        }

        with (
            patch(
                "suzent.acp.runtime.run_acp_turn_text", new_callable=AsyncMock
            ) as mock_acp_turn,
            patch(
                "suzent.core.chat_processor.ChatProcessor.process_background_turn",
                new_callable=AsyncMock,
            ) as mock_native_turn,
        ):
            # (3) target chat config runtime='acp' calls mocked run_acp_turn_text
            await dispatcher._run_target_turn(msg_acp)
            assert mock_acp_turn.called
            assert not mock_native_turn.called

            mock_acp_turn.reset_mock()
            mock_native_turn.reset_mock()

            # (4) native config calls ChatProcessor and not ACP runtime
            await dispatcher._run_target_turn(msg_native)
            assert mock_native_turn.called
            assert not mock_acp_turn.called


@pytest.mark.asyncio
async def test_stream_acp_turn_no_output():
    # Test (5) stream_acp_turn no-output path does not append an empty assistant message
    with (
        patch("suzent.acp.runtime.get_database") as mock_get_db,
        patch("suzent.acp.runtime.get_acp_manager") as mock_get_manager,
    ):
        mock_db = MagicMock()
        chat_mock = MagicMock()
        chat_mock.config = {
            "runtime": "acp",
            "acp_agent_id": "test-agent",
            "acp_session_id": "test-session",
            "acp_cwd": "/tmp",
        }
        chat_mock.messages = []
        mock_db.get_chat.return_value = chat_mock
        mock_get_db.return_value = mock_db

        # Mock ACP Manager
        mock_manager = AsyncMock()
        managed_mock = MagicMock()
        managed_mock.agent_id = "test-agent"
        managed_mock.session_id = "test-session"
        managed_mock.cwd = "/tmp"

        # Mock client.prompt to return empty response
        async def mock_prompt(session_id, message):
            return {"text": ""}

        managed_mock.client.prompt = mock_prompt

        # Mock updates queue to have empty
        managed_mock.updates = asyncio.Queue()

        mock_manager.ensure.return_value = managed_mock
        mock_get_manager.return_value = mock_manager

        stream = stream_acp_turn("test-chat-id", "hello")

        chunks = []
        async for chunk in stream:
            chunks.append(chunk)

        # Ensure append_chat_message was not called with assistant role
        for call in mock_db.append_chat_message.call_args_list:
            assert call[0][1].get("role") != "assistant"

        # Verify RUN_ERROR is yielded due to no output (parse SSE)
        found_error = False
        for chunk in chunks:
            if chunk.startswith("data: "):
                event = json.loads(chunk[6:].strip())
                if event.get("type") == "RUN_ERROR" and "no output text" in event.get(
                    "message", ""
                ):
                    found_error = True
        assert found_error
