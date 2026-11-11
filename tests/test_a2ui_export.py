import re

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.a2ui.export import canvas_file_name, save_surface, surface_to_html
from suzent.a2ui.models import A2UISurface
from suzent.config import CONFIG
from suzent.routes import a2ui_routes


def _surface(component: dict, title: str | None = "Q4 Sales") -> A2UISurface:
    return A2UISurface.model_validate(
        {"id": "sales", "title": title, "component": component}
    )


def test_typed_surface_becomes_a_readable_page_without_controls() -> None:
    surface = _surface(
        {
            "type": "card",
            "title": "Regions",
            "children": [
                {
                    "type": "table",
                    "columns": [{"key": "r", "label": "Region"}],
                    "rows": [{"r": "<EU>"}],
                },
                {"type": "badge", "label": "Up", "color": "success"},
                {"type": "button", "label": "Refresh", "action": "refresh"},
                {
                    "type": "form",
                    "action": "go",
                    "fields": [{"name": "a", "label": "A"}],
                },
            ],
        }
    )

    html = surface_to_html(surface)

    assert html.startswith("<!DOCTYPE html>")
    assert "<title>Q4 Sales</title>" in html
    assert "<td>&lt;EU&gt;</td>" in html
    assert 'class="badge success"' in html
    assert "Refresh" not in html
    assert "<form" not in html


def test_html_surface_is_saved_as_its_own_document() -> None:
    surface = _surface({"type": "html", "html": "<svg></svg>"})

    assert surface_to_html(surface) == "<!DOCTYPE html>\n<svg></svg>"


def test_nested_html_is_sandboxed() -> None:
    surface = _surface(
        {"type": "stack", "children": [{"type": "html", "html": '<b class="x">hi</b>'}]}
    )

    assert (
        '<iframe sandbox="allow-scripts" srcdoc="&lt;b class=&quot;x&quot;&gt;hi&lt;/b&gt;"'
        in surface_to_html(surface)
    )


def test_file_name_is_stable_and_safe() -> None:
    name = canvas_file_name(_surface({"type": "divider"}, "../Q4 / 销售"), "chat-a")
    assert re.fullmatch(r"q4-销售-[0-9a-f]{6}\.html", name)
    assert name == canvas_file_name(
        _surface({"type": "text", "content": "x"}, "../Q4 / 销售"), "chat-a"
    )
    assert canvas_file_name(_surface({"type": "divider"}, None), "chat-a").startswith(
        "sales-"
    )


def test_same_title_from_another_chat_gets_its_own_file() -> None:
    surface = _surface({"type": "divider"})
    assert canvas_file_name(surface, "chat-a") != canvas_file_name(surface, "chat-b")


def test_saving_again_replaces_the_file(tmp_path) -> None:
    first = save_surface(_surface({"type": "text", "content": "v1"}), "c", tmp_path)
    second = save_surface(_surface({"type": "text", "content": "v2"}), "c", tmp_path)

    assert first == second
    assert first.parent == tmp_path / "artifacts" / "canvas"
    assert first.name.startswith("q4-sales-")
    assert "v2" in second.read_text(encoding="utf-8")


def test_save_route_writes_into_the_chats_project(
    temp_db, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(CONFIG, "sandbox_data_path", str(tmp_path))
    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    project_id = temp_db.create_project("Sales", "sales")
    chat_id = temp_db.create_chat("Report", {}, project_id=project_id)
    client = TestClient(
        Starlette(
            routes=[
                Route("/canvas/{chat_id}/save", a2ui_routes.a2ui_save, methods=["POST"])
            ]
        )
    )
    surface = {"id": "sales", "title": "Q4", "component": {"type": "divider"}}

    saved = client.post(f"/canvas/{chat_id}/save", json={"surface": surface})
    invalid = client.post(f"/canvas/{chat_id}/save", json={"surface": {"id": "x"}})
    missing = client.post("/canvas/nope/save", json={"surface": surface})

    assert saved.status_code == 200
    name = canvas_file_name(A2UISurface.model_validate(surface), chat_id)
    assert saved.json() == {
        "path": str(tmp_path / "projects" / "sales" / "artifacts" / "canvas" / name),
        "workspace_path": f"/workspace/artifacts/canvas/{name}",
    }
    assert invalid.status_code == 400
    assert missing.status_code == 404
