from types import SimpleNamespace
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.routes import memory_routes


class _FakeMarkdownStore:
    def __init__(self) -> None:
        self.contexts = {"project-1": "# One\n"}

    async def read_project_context(self, project_id: str) -> str | None:
        return self.contexts.get(project_id)

    async def write_project_context(self, project_id: str, content: str) -> None:
        self.contexts[project_id] = content


class _FakeDatabase:
    def __init__(self) -> None:
        self.projects = [
            SimpleNamespace(id="project-1", name="One", slug="one", archived=False),
            SimpleNamespace(id="project-2", name="Two", slug="two", archived=False),
        ]

    def list_projects(self, include_archived: bool = False):
        del include_archived
        return self.projects

    def get_project(self, project_id: str):
        return next((p for p in self.projects if p.id == project_id), None)

    def count_chats_in_project(self, project_id: str) -> int:
        return 2 if project_id == "project-1" else 0


def _client(monkeypatch) -> tuple[TestClient, _FakeMarkdownStore]:
    database = _FakeDatabase()
    markdown_store = _FakeMarkdownStore()

    async def get_manager():
        return SimpleNamespace(markdown_store=markdown_store)

    monkeypatch.setattr(memory_routes, "get_database", lambda: database)
    monkeypatch.setattr(memory_routes, "_get_or_initialize_memory_manager", get_manager)
    app = Starlette(
        routes=[
            Route(
                "/memory/project-contexts",
                memory_routes.list_project_contexts,
                methods=["GET"],
            ),
            Route(
                "/memory/project-contexts/{project_id}",
                memory_routes.update_project_context,
                methods=["PUT"],
            ),
        ]
    )
    return TestClient(app), markdown_store


def test_lists_every_project_context(monkeypatch):
    client, _ = _client(monkeypatch)

    response = client.get("/memory/project-contexts")

    assert response.status_code == 200
    assert response.json() == {
        "projects": [
            {
                "projectId": "project-1",
                "projectName": "One",
                "projectSlug": "one",
                "archived": False,
                "chatCount": 2,
                "content": "# One\n",
                "exists": True,
            },
            {
                "projectId": "project-2",
                "projectName": "Two",
                "projectSlug": "two",
                "archived": False,
                "chatCount": 0,
                "content": "",
                "exists": False,
            },
        ]
    }


def test_updates_context_by_project_id(monkeypatch):
    client, markdown_store = _client(monkeypatch)

    response = client.put(
        "/memory/project-contexts/project-2", json={"content": "# Two\n"}
    )

    assert response.status_code == 200
    assert markdown_store.contexts["project-2"] == "# Two\n"


def test_rejects_unknown_project_context(monkeypatch):
    client, _ = _client(monkeypatch)

    response = client.put("/memory/project-contexts/missing", json={"content": "nope"})

    assert response.status_code == 404


def test_repository_context_returns_project_memory_and_walk_up_instructions(
    monkeypatch, tmp_path: Path
):
    repository = tmp_path / "repository"
    working = repository / "packages" / "api"
    project_dir = tmp_path / "projects" / "one"
    working.mkdir(parents=True)
    project_dir.mkdir(parents=True)
    (repository / ".git").mkdir()
    (repository / "AGENTS.md").write_text("# Root rules\n", encoding="utf-8")
    (working / "CLAUDE.md").write_text("# API rules\n", encoding="utf-8")
    project = SimpleNamespace(id="project-1", name="One", slug="one", archived=False)
    chat = SimpleNamespace(
        id="chat-1",
        project_id=project.id,
        working_directory=str(working),
        config={"sandbox_enabled": False},
    )
    database = SimpleNamespace(
        get_chat=lambda _chat_id: chat,
        get_chat_project_id=lambda _chat_id: project.id,
        get_chat_project_slug=lambda _chat_id: project.slug,
        get_project=lambda _project_id: project,
        get_project_dir=lambda _chat_id: project_dir,
    )
    markdown_store = _FakeMarkdownStore()

    async def get_manager():
        return SimpleNamespace(markdown_store=markdown_store)

    monkeypatch.setattr(memory_routes, "get_database", lambda: database)
    monkeypatch.setattr("suzent.database.get_database", lambda: database)
    monkeypatch.setattr(memory_routes, "_get_or_initialize_memory_manager", get_manager)
    app = Starlette(
        routes=[
            Route(
                "/memory/repository-context",
                memory_routes.get_repository_context,
                methods=["GET"],
            )
        ]
    )

    response = TestClient(app).get(
        "/memory/repository-context", params={"chat_id": "chat-1"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project"] == {
        "projectId": "project-1",
        "projectName": "One",
        "content": "# One\n",
        "exists": True,
        "path": str((project_dir / "context.md").resolve()),
        "virtualPath": "/workspace/context.md",
    }
    assert [item["name"] for item in payload["instructions"]] == [
        "AGENTS.md",
        "CLAUDE.md",
    ]
    assert [item["content"] for item in payload["instructions"]] == [
        "# Root rules\n",
        "# API rules\n",
    ]


@pytest.mark.parametrize("memory_enabled", [False, True])
def test_repository_context_returns_instructions_when_memory_unavailable(
    monkeypatch, tmp_path: Path, memory_enabled: bool
):
    repository = tmp_path / "repository"
    working = repository / "packages" / "api"
    project_dir = tmp_path / "projects" / "one"
    working.mkdir(parents=True)
    project_dir.mkdir(parents=True)
    (repository / ".git").mkdir()
    (repository / "AGENTS.md").write_text("# Root rules\n", encoding="utf-8")
    project = SimpleNamespace(id="project-1", name="One", slug="one", archived=False)
    chat = SimpleNamespace(
        id="chat-1",
        project_id=project.id,
        working_directory=str(working),
        config={"sandbox_enabled": False},
    )
    database = SimpleNamespace(
        get_chat=lambda _chat_id: chat,
        get_chat_project_id=lambda _chat_id: project.id,
        get_chat_project_slug=lambda _chat_id: project.slug,
        get_project=lambda _project_id: project,
        get_project_dir=lambda _chat_id: project_dir,
    )

    async def get_manager():
        raise AssertionError("memory initialization must be skipped when disabled")

    monkeypatch.setattr(memory_routes.CONFIG, "memory_enabled", memory_enabled)
    monkeypatch.setattr(memory_routes, "get_database", lambda: database)
    monkeypatch.setattr("suzent.database.get_database", lambda: database)
    monkeypatch.setattr(memory_routes, "_get_or_initialize_memory_manager", get_manager)
    app = Starlette(
        routes=[
            Route(
                "/memory/repository-context",
                memory_routes.get_repository_context,
                methods=["GET"],
            )
        ]
    )

    response = TestClient(app).get(
        "/memory/repository-context", params={"chat_id": "chat-1"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project"]["content"] == ""
    assert payload["project"]["exists"] is False
    assert [item["name"] for item in payload["instructions"]] == ["AGENTS.md"]
