from pathlib import Path
from types import SimpleNamespace

import pytest

from suzent.routes import sandbox_routes


@pytest.mark.asyncio
async def test_get_sandbox_volumes_includes_discovered_skill_mounts(monkeypatch):
    chat = {"config": {"sandbox_volumes": ["/repo:/mnt/repository"]}}
    monkeypatch.setattr(
        sandbox_routes,
        "get_database",
        lambda: SimpleNamespace(get_chat=lambda _chat_id: chat),
    )
    monkeypatch.setattr(
        sandbox_routes,
        "get_effective_volumes",
        lambda volumes: list(volumes),
    )
    monkeypatch.setattr(
        "suzent.skills.manager.get_skill_manager_for_chat",
        lambda *_args, **_kwargs: SimpleNamespace(
            required_mounts=["/skills:/mnt/skills/discovered/repository:ro"]
        ),
    )
    request = SimpleNamespace(query_params={"chat_id": "chat-1"})

    response = await sandbox_routes.get_sandbox_volumes(request)

    assert response.status_code == 200
    assert response.body == (
        b'{"volumes":["/repo:/mnt/repository",'
        b'"/skills:/mnt/skills/discovered/repository:ro"]}'
    )


def test_request_resolver_includes_discovered_skill_mounts(monkeypatch):
    monkeypatch.setattr(
        sandbox_routes,
        "get_effective_volumes",
        lambda volumes: list(volumes),
    )
    monkeypatch.setattr(
        sandbox_routes,
        "get_database",
        lambda: SimpleNamespace(
            get_chat=lambda _chat_id: {
                "config": {
                    "sandbox_enabled": True,
                    "sandbox_volumes": ["/repo:/mnt/repository"],
                }
            }
        ),
    )
    monkeypatch.setattr(
        "suzent.skills.manager.get_skill_manager_for_chat",
        lambda *_args, **_kwargs: SimpleNamespace(
            required_mounts=["/skills:/mnt/skills/discovered/repository:ro"]
        ),
    )

    resolver = sandbox_routes._get_resolver_for_request("chat-1")

    assert (
        resolver.custom_mounts["/mnt/skills/discovered/repository"]
        == Path("/skills").resolve()
    )


def test_request_resolver_skips_discovered_skill_mounts_in_host_mode(monkeypatch):
    monkeypatch.setattr(
        sandbox_routes,
        "get_effective_volumes",
        lambda volumes: list(volumes),
    )
    monkeypatch.setattr(
        sandbox_routes,
        "get_database",
        lambda: SimpleNamespace(
            get_chat_access_info=lambda _chat_id: {
                "config": {
                    "sandbox_enabled": False,
                    "sandbox_volumes": ["/repo:/mnt/repository"],
                },
                "working_directory": None,
                "project_id": "proj-1",
                "project_slug": "default",
                "project_working_directory": None,
                "project_extra_folders": [],
            },
            resolve_chat_working_directory=lambda _chat: None,
            with_project_folders=lambda _chat, volumes: list(volumes),
        ),
    )

    def _unexpected_call(*_args, **_kwargs):
        raise AssertionError("SkillManager should not be constructed in host mode")

    monkeypatch.setattr(
        "suzent.skills.manager.get_skill_manager_for_chat",
        _unexpected_call,
    )

    resolver = sandbox_routes._get_resolver_for_request("chat-host")

    assert resolver.sandbox_enabled is False
    assert resolver.custom_mounts == {"/mnt/repository": Path("/repo").resolve()}
