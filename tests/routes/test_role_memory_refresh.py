from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from suzent.core.role_router import RoleRouter
from suzent.memory.manager import MemoryManager
from suzent.routes.config_routes import save_role_models


async def test_saving_roles_updates_live_extraction_and_inheritance(
    monkeypatch,
) -> None:
    router = RoleRouter()
    monkeypatch.setattr("suzent.core.role_router.get_role_router", lambda: router)
    monkeypatch.setattr(router, "save_to_db", lambda: None)
    manager = MemoryManager(store=Mock())
    monkeypatch.setattr("suzent.memory.lifecycle.memory_manager", manager)
    used: list[str] = []

    def client(model: str) -> SimpleNamespace:
        async def extract(**kwargs) -> SimpleNamespace:
            used.append(model)
            return SimpleNamespace(facts=[])

        return SimpleNamespace(model=model, extract_with_schema=extract)

    monkeypatch.setattr("suzent.memory.manager.LLMClient", client)
    for roles, expected in [
        ({"memory_extraction": ["specific"], "cheap": ["cheap"]}, "specific"),
        ({"memory_extraction": [], "cheap": ["cheap"]}, "cheap"),
        ({"primary": ["main"]}, "main"),
        ({}, None),
    ]:
        request = SimpleNamespace(json=AsyncMock(return_value={"roles": roles}))
        response = await save_role_models(request)
        assert response.status_code == 200
        assert manager.llm_extraction_model == expected
        if expected:
            await manager._extract_facts_llm("test conversation")
        else:
            assert manager.llm_client is None
    assert used == ["specific", "cheap", "main"]


async def test_save_roles_does_not_initialize_memory(monkeypatch) -> None:
    router = RoleRouter()
    monkeypatch.setattr("suzent.core.role_router.get_role_router", lambda: router)
    monkeypatch.setattr(router, "save_to_db", lambda: None)
    monkeypatch.setattr("suzent.memory.lifecycle.memory_manager", None)
    request = SimpleNamespace(
        json=AsyncMock(return_value={"roles": {"cheap": ["new"]}})
    )
    assert (await save_role_models(request)).status_code == 200


async def test_extraction_keeps_original_client_during_role_change(monkeypatch) -> None:
    manager = MemoryManager(store=Mock())
    original = AsyncMock()

    async def schema(**kwargs) -> None:
        manager.set_extraction_model(None)
        raise ValueError("schema unsupported")

    original.extract_with_schema.side_effect = schema
    original.extract_structured.return_value = {"facts": []}
    manager.llm_extraction_model = "original"
    manager.llm_client = original
    assert await manager._extract_facts_llm("conversation") == []
    original.extract_structured.assert_awaited_once()
    assert manager.llm_client is None
