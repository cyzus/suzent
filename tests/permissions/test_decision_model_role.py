from unittest.mock import AsyncMock

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
