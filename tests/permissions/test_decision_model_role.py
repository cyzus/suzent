from unittest.mock import AsyncMock

import pytest

from suzent.core.role_router import RoleRouter
from suzent.permissions.auto.classifier import AutoPermissionClassifier
from suzent.permissions.auto.models import AutoClassificationResult


async def test_permission_review_uses_decision_then_explicit_override(
    monkeypatch,
) -> None:
    router = RoleRouter()
    router.set_role("cheap", ["lightweight"])
    router.set_role("decision", ["decision-model"])
    monkeypatch.setattr("suzent.core.role_router.get_role_router", lambda: router)
    used: list[str] = []

    def client(model: str) -> AsyncMock:
        used.append(model)
        mock = AsyncMock()
        mock.extract_with_schema.return_value = AutoClassificationResult(
            should_block=False, reason="Local read", confidence="high"
        )
        return mock

    monkeypatch.setattr("suzent.llm.LLMClient", client)
    classifier = AutoPermissionClassifier()
    result = await classifier.classify(tool_name="read_file", args={}, transcript=[])
    assert result.reviewer_model == "decision-model"
    router.set_role("permission_review", ["review-model"])
    result = await classifier.classify(tool_name="read_file", args={}, transcript=[])
    assert result.reviewer_model == "review-model"
    assert used == ["decision-model", "review-model"]


def test_reason_follows_user_language_and_keeps_args_verbatim() -> None:
    from suzent.permissions.auto.classifier import SYSTEM_PROMPT

    assert "language of the CURRENT USER REQUEST" in SYSTEM_PROMPT
    assert "exactly as they appear" in SYSTEM_PROMPT
    schema = AutoClassificationResult.model_json_schema()
    assert "language" in schema["properties"]["reason"]["description"]


async def test_unreachable_reviewer_falls_back_to_the_chat_model(monkeypatch) -> None:
    """A reviewer role pinned to a provider the user cannot reach used to turn
    every auto-mode action into a manual prompt, even while the chat itself
    ran fine on another provider."""
    router = RoleRouter()
    router.set_role("permission_review", ["deepseek/deepseek-chat"])
    monkeypatch.setattr("suzent.core.role_router.get_role_router", lambda: router)
    used: list[str] = []

    def client(model: str) -> AsyncMock:
        used.append(model)
        mock = AsyncMock()
        if model.startswith("deepseek/"):
            mock.extract_with_schema.side_effect = ValueError("Cannot connect")
        else:
            mock.extract_with_schema.return_value = AutoClassificationResult(
                should_block=False, reason="Local write", confidence="high"
            )
        return mock

    monkeypatch.setattr("suzent.llm.LLMClient", client)
    classifier = AutoPermissionClassifier()

    result = await classifier.classify(
        tool_name="bash_execute",
        args={},
        transcript=[],
        chat_model="dashscope/qwen-flash",
    )

    assert result.reviewer_model == "dashscope/qwen-flash"
    assert used == ["deepseek/deepseek-chat", "dashscope/qwen-flash"]

    with pytest.raises(ValueError, match="Cannot connect"):
        await classifier.classify(
            tool_name="bash_execute",
            args={},
            transcript=[],
            chat_model="deepseek/deepseek-chat",
        )
