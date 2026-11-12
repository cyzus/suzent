"""Tests for the unified Mailbox & Dynamic LLM-Crystallized Router."""

import json
import pytest
from starlette.requests import Request

from suzent.core.focal_agent import FOCAL_CHAT_ID
from suzent.core.mailbox import get_or_create_mailbox_token
from suzent.routes import mailbox_routes
from suzent.routes.webhook_routes import receive_webhook


def _request(
    method: str,
    path: str,
    *,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
    path_params: dict | None = None,
    query_string: bytes = b"",
) -> Request:
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string,
        "headers": [
            (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
        ],
        "path_params": path_params or {},
    }
    return Request(scope, receive)


@pytest.fixture
def db(temp_db, monkeypatch):
    monkeypatch.setattr("suzent.core.mailbox.get_database", lambda: temp_db)
    monkeypatch.setattr("suzent.routes.mailbox_routes.get_database", lambda: temp_db)
    monkeypatch.setattr("suzent.routes.webhook_routes.get_database", lambda: temp_db)
    monkeypatch.setattr("suzent.core.focal_agent.get_database", lambda: temp_db)
    monkeypatch.setattr("suzent.core.agent_inbox.get_database", lambda: temp_db)
    return temp_db


@pytest.mark.asyncio
async def test_first_seen_github_release_auto_learns_rule_and_routes_to_regent(db):
    token = get_or_create_mailbox_token()
    payload = {
        "action": "published",
        "repository": {"full_name": "cyzus/suzent"},
        "release": {"tag_name": "v0.16.0", "name": "v0.16.0"},
    }
    res = await receive_webhook(
        _request(
            "POST",
            f"/hooks/{token}",
            body=json.dumps(payload).encode(),
            headers={
                "content-type": "application/json",
                "x-github-event": "release",
                "x-suzent-relay-queued-at": "1793811024000",
            },
            path_params={"token": token},
        )
    )
    assert res.status_code == 202
    data = json.loads(res.body)
    assert data["accepted"] is True
    assert data["route_status"] == "routed"
    assert data["target_chat_id"] == FOCAL_CHAT_ID

    # Verify a reusable learned rule was crystallized
    rules = db.list_mailbox_rules()
    assert len(rules) == 1
    assert rules[0].signature == "github:release.published:cyzus/suzent"
    assert rules[0].action == "route"
    assert rules[0].target_chat_id == FOCAL_CHAT_ID
    assert rules[0].origin == "learned"
    assert rules[0].hit_count == 1

    # Verify the item is listed in /mailbox/items with spooled_at preserved
    list_res = await mailbox_routes.list_mailbox_items_route(
        _request("GET", "/mailbox/items")
    )
    list_data = json.loads(list_res.body)
    assert list_data["counts"]["all"] == 1
    assert list_data["counts"]["routed"] == 1
    assert list_data["items"][0]["spooled_at"] == "1793811024000"
    assert "v0.16.0" in list_data["items"][0]["summary"]


@pytest.mark.asyncio
async def test_routine_ci_success_and_ping_auto_learn_unrouted_rule(db):
    token = get_or_create_mailbox_token()
    payload = {
        "action": "completed",
        "repository": {"full_name": "cyzus/suzent-relay"},
        "workflow_run": {"name": "test (cloudflare)", "conclusion": "success"},
    }
    res = await receive_webhook(
        _request(
            "POST",
            f"/hooks/{token}",
            body=json.dumps(payload).encode(),
            headers={
                "content-type": "application/json",
                "x-github-event": "workflow_run",
            },
            path_params={"token": token},
        )
    )
    assert res.status_code == 202
    data = json.loads(res.body)
    assert data["route_status"] == "unrouted"
    assert data["target_chat_id"] is None

    # Rule should be wildcarded for quiet CI success across repos
    rule = db.get_mailbox_rule_by_signature("github:workflow_run.success:*")
    assert rule is not None
    assert rule.action == "none"
    assert rule.origin == "learned"


@pytest.mark.asyncio
async def test_user_override_pins_rule_for_future_events(db):
    db.create_chat(title="Suzent Dev", config={}, chat_id="proj-suzent-chat")
    token = get_or_create_mailbox_token()
    payload = {
        "action": "completed",
        "repository": {"full_name": "cyzus/suzent"},
        "workflow_run": {"name": "pytest", "conclusion": "failure"},
    }

    # First arrival defaults to Regent (learned)
    res1 = await receive_webhook(
        _request(
            "POST",
            f"/hooks/{token}",
            body=json.dumps(payload).encode(),
            headers={"x-github-event": "workflow_run"},
            path_params={"token": token},
        )
    )
    item1_id = json.loads(res1.body)["item_id"]

    # User overrides item #1 to route to "proj-suzent-chat" and pins the rule
    override_res = await mailbox_routes.route_mailbox_item_route(
        _request(
            "POST",
            f"/mailbox/items/{item1_id}/route",
            body=json.dumps(
                {
                    "action": "route",
                    "target_chat_id": "proj-suzent-chat",
                    "pin_rule": True,
                }
            ).encode(),
            path_params={"item_id": str(item1_id)},
        )
    )
    assert override_res.status_code == 200
    updated_item = json.loads(override_res.body)["item"]
    assert updated_item["target_chat_id"] == "proj-suzent-chat"
    assert updated_item["rule_origin"] == "pinned"

    # Second arrival with the same signature hits the pinned rule directly!
    res2 = await receive_webhook(
        _request(
            "POST",
            f"/hooks/{token}",
            body=json.dumps(payload).encode(),
            headers={"x-github-event": "workflow_run"},
            path_params={"token": token},
        )
    )
    data2 = json.loads(res2.body)
    assert data2["target_chat_id"] == "proj-suzent-chat"

    rule = db.get_mailbox_rule_by_signature("github:workflow_run.failure:cyzus/suzent")
    assert rule.origin == "pinned"
    assert rule.target_chat_id == "proj-suzent-chat"
