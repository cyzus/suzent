from types import SimpleNamespace
from unittest.mock import patch

from pydantic_ai.models.test import TestModel

import suzent.agent_manager as agent_manager


def test_create_agent_uses_v2_constructor_options() -> None:
    with (
        patch.object(
            agent_manager,
            "get_enabled_models_from_db",
            return_value=["test/model"],
        ),
        patch.object(
            agent_manager,
            "create_pydantic_ai_model",
            return_value=TestModel(),
        ),
        patch.object(agent_manager, "_build_mcp_servers", return_value=[]),
        patch.object(
            agent_manager,
            "get_skill_manager",
            return_value=SimpleNamespace(enabled_skills=set()),
        ),
    ):
        agent = agent_manager.create_agent(
            {
                "model": "test/model",
                "tools": ["ReadFileTool"],
                "instructions": "",
                "static_instructions": "",
            }
        )

    assert agent._max_tool_retries == 1
    assert agent._max_output_retries == 3
