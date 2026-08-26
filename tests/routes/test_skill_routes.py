from types import SimpleNamespace

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.routes.skill_routes import get_skills, toggle_skill


class _FakeManager:
    def __init__(self, skill_id: str) -> None:
        self.skill = SimpleNamespace(
            id=skill_id,
            metadata=SimpleNamespace(name="skill-installer"),
        )
        self.loader = SimpleNamespace(get_skill=self._get_skill)
        self.enabled: list[str] = []
        self.disabled: list[str] = []

    def _get_skill(self, identifier: str):
        return self.skill if identifier == self.skill.id else None

    def enable_skill(self, identifier: str) -> None:
        self.enabled.append(identifier)

    def disable_skill(self, identifier: str) -> None:
        self.disabled.append(identifier)


def test_toggle_accepts_namespaced_skill_id_in_json(monkeypatch) -> None:
    skill_id = "home:afa779f98f:.codex/.system:skill-installer"
    manager = _FakeManager(skill_id)
    monkeypatch.setattr(
        "suzent.routes.skill_routes.get_skill_manager_for_chat",
        lambda _chat_id: manager,
    )
    app = Starlette(routes=[Route("/skills/toggle", toggle_skill, methods=["POST"])])

    response = TestClient(app).post(
        "/skills/toggle?chat_id=chat-1",
        json={"id": skill_id, "enabled": False},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": skill_id,
        "name": "skill-installer",
        "enabled": False,
    }
    assert manager.disabled == [skill_id]
    assert manager.enabled == []


def test_skill_listing_exposes_host_and_sandbox_paths(tmp_path, monkeypatch) -> None:
    host_path = tmp_path / ".codex" / "skills" / "example" / "SKILL.md"
    skill = SimpleNamespace(
        id="home:test:.codex:example",
        metadata=SimpleNamespace(name="example", description="Example"),
        body="body",
        path=host_path,
        virtual_path="/mnt/skills/home/example/SKILL.md",
        source="home",
        source_id="home:test:.codex",
    )
    manager = SimpleNamespace(
        loader=SimpleNamespace(list_skills=lambda: [skill]),
        is_skill_enabled=lambda _identifier: True,
    )
    monkeypatch.setattr(
        "suzent.routes.skill_routes.get_skill_manager_for_chat",
        lambda _chat_id: manager,
    )
    app = Starlette(routes=[Route("/skills", get_skills, methods=["GET"])])

    response = TestClient(app).get("/skills")

    assert response.status_code == 200
    payload = response.json()[0]
    assert payload["hostPath"] == str(host_path)
    assert payload["path"] == "/mnt/skills/home/example/SKILL.md"
