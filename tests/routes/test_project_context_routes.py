from types import SimpleNamespace

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
