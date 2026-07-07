from __future__ import annotations

from types import SimpleNamespace

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)

import suzent.routes.chat_routes as chat_routes
import suzent.routes.config_routes as config_routes
import suzent.routes.permission_routes as permission_routes
from suzent.core.agent_serializer import serialize_state


class FakeDatabase:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(id="chat-1", config={}, agent_state=None)

    def get_chat(self, chat_id: str):
        return self.chat if chat_id == "chat-1" else None

    def merge_chat_config(self, chat_id: str, updates: dict) -> bool:
        if chat_id != "chat-1":
            return False
        self.chat.config = {**self.chat.config, **updates}
        return True


def test_plan_mode_restores_previous_mode(monkeypatch) -> None:
    db = FakeDatabase()
    monkeypatch.setattr(chat_routes, "get_database", lambda: db)
    app = Starlette(
        routes=[
            Route(
                "/chats/{chat_id}/permission-mode",
                chat_routes.set_permission_mode,
                methods=["PUT"],
            ),
            Route(
                "/chats/{chat_id}/permission-mode",
                chat_routes.get_permission_mode,
                methods=["GET"],
            ),
        ]
    )
    client = TestClient(app)

    db.chat.config = {"permission_mode": "accept_edits"}
    entered = client.put(
        "/chats/chat-1/permission-mode",
        json={"mode": "plan"},
    )
    assert entered.status_code == 200
    assert entered.json()["prePlanMode"] == "accept_edits"

    restored = client.put(
        "/chats/chat-1/permission-mode",
        json={"restorePrevious": True},
    )
    assert restored.status_code == 200
    assert restored.json()["mode"] == "accept_edits"
    assert restored.json()["prePlanMode"] is None


def test_default_permission_mode_api_persists(monkeypatch, tmp_path) -> None:
    import suzent.config as config_module

    config_dir = tmp_path / "config"
    monkeypatch.setattr(config_module, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(config_module, "USER_CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module.CONFIG, "default_permission_mode", "default")

    app = Starlette(
        routes=[
            Route(
                "/config/default-permission-mode",
                config_routes.save_default_permission_mode,
                methods=["PUT"],
            ),
        ]
    )
    client = TestClient(app)

    response = client.put(
        "/config/default-permission-mode",
        json={"mode": "accept_edits"},
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "accept_edits"
    assert config_module.CONFIG.default_permission_mode == "accept_edits"
    assert (
        "default_permission_mode: accept_edits"
        in (config_dir / "permissions.yaml").read_text()
    )


def test_session_rule_api_round_trip(monkeypatch) -> None:
    db = FakeDatabase()
    monkeypatch.setattr(permission_routes, "get_database", lambda: db)
    app = Starlette(
        routes=[
            Route(
                "/permissions",
                permission_routes.get_permissions,
                methods=["GET"],
            ),
            Route(
                "/permissions/rules",
                permission_routes.create_permission_rule,
                methods=["POST"],
            ),
            Route(
                "/permissions/rules/{rule_id}",
                permission_routes.delete_permission_rule,
                methods=["DELETE"],
            ),
        ]
    )
    client = TestClient(app)

    created = client.post(
        "/permissions/rules",
        json={
            "destination": "session",
            "chat_id": "chat-1",
            "rule": {
                "id": "session-rule",
                "tool": "write_file",
                "behavior": "ask",
                "matcher": {"type": "path_prefix", "value": "docs/"},
            },
        },
    )
    assert created.status_code == 201
    assert created.json()["rule"]["source"] == "session"

    listed = client.get("/permissions?chat_id=chat-1")
    assert listed.status_code == 200
    assert listed.json()["sessionRules"][0]["id"] == "session-rule"

    deleted = client.delete(
        "/permissions/rules/session-rule?destination=session&chat_id=chat-1"
    )
    assert deleted.status_code == 200
    assert db.chat.config["permission_rules"] == []


def test_permission_state_restores_legacy_approval_safely(monkeypatch) -> None:
    db = FakeDatabase()
    db.chat.config = {
        "permission_mode": "default",
        "_pending_approvals": [
            {
                "approvalId": "call-1",
                "toolCallId": "call-1",
                "toolName": "bash_execute",
                "args": {"content": "npm test"},
            }
        ],
    }
    monkeypatch.setattr(permission_routes, "get_database", lambda: db)
    app = Starlette(
        routes=[
            Route(
                "/chats/{chat_id}/permission-state",
                permission_routes.get_chat_permission_state,
                methods=["GET"],
            )
        ]
    )

    response = TestClient(app).get("/chats/chat-1/permission-state")

    assert response.status_code == 200
    actions = response.json()["pendingApprovals"][0]["decision"]["actions"]
    assert [action["id"] for action in actions] == ["allow_once", "reject"]


def test_permission_state_discards_approvals_resolved_in_agent_history(
    monkeypatch,
) -> None:
    db = FakeDatabase()
    db.chat.config = {
        "_pending_approvals": [
            {
                "approvalId": "call-complete",
                "toolCallId": "call-complete",
                "toolName": "bash_execute",
                "args": {"content": "python --version"},
            },
            {
                "approvalId": "call-stale",
                "toolCallId": "call-stale",
                "toolName": "bash_execute",
                "args": {"content": "python --version"},
            },
        ]
    }
    db.chat.agent_state = serialize_state(
        [
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="bash_execute",
                        tool_call_id="call-complete",
                        args={"content": "python --version"},
                    )
                ]
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="bash_execute",
                        tool_call_id="call-complete",
                        content="Python 3.12.9",
                    )
                ]
            ),
        ]
    )
    monkeypatch.setattr(permission_routes, "get_database", lambda: db)
    app = Starlette(
        routes=[
            Route(
                "/chats/{chat_id}/permission-state",
                permission_routes.get_chat_permission_state,
                methods=["GET"],
            )
        ]
    )

    response = TestClient(app).get("/chats/chat-1/permission-state")

    assert response.status_code == 200
    assert response.json()["pendingApprovals"] == []
    assert db.chat.config["_pending_approvals"] == []


def test_permission_state_keeps_only_unanswered_tool_call_ids(monkeypatch) -> None:
    db = FakeDatabase()
    db.chat.config = {
        "_pending_approvals": [
            {
                "approvalId": "call-pending",
                "toolCallId": "call-pending",
                "toolName": "bash_execute",
                "args": {"content": "python --version"},
            },
            {
                "approvalId": "call-stale",
                "toolCallId": "call-stale",
                "toolName": "bash_execute",
                "args": {"content": "python --version"},
            },
        ]
    }
    db.chat.agent_state = serialize_state(
        [
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="bash_execute",
                        tool_call_id="call-pending",
                        args={"content": "python --version"},
                    )
                ]
            )
        ]
    )
    monkeypatch.setattr(permission_routes, "get_database", lambda: db)
    app = Starlette(
        routes=[
            Route(
                "/chats/{chat_id}/permission-state",
                permission_routes.get_chat_permission_state,
                methods=["GET"],
            )
        ]
    )

    response = TestClient(app).get("/chats/chat-1/permission-state")

    assert response.status_code == 200
    approvals = response.json()["pendingApprovals"]
    assert [item["toolCallId"] for item in approvals] == ["call-pending"]
    assert [item["toolCallId"] for item in db.chat.config["_pending_approvals"]] == [
        "call-pending"
    ]
