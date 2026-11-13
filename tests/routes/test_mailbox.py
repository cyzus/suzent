"""Tests for the unified Mailbox & Dynamic LLM-Crystallized Router."""

import asyncio
import json

import pytest
from starlette.requests import Request

from suzent.core.focal_agent import FOCAL_CHAT_ID
from suzent.core.mailbox import get_or_create_mailbox_token, ingest_mailbox_event
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


def _fake_router(monkeypatch, reply, *, delay: float = 0.0) -> list[str]:
    """Stand in for the decision model; returns the prompts it received."""
    calls: list[str] = []

    async def ask(prompt: str) -> str:
        calls.append(prompt)
        if delay:
            await asyncio.sleep(delay)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr("suzent.core.mailbox._ask_router", ask)
    return calls


_ROUTE_TO_REGENT = json.dumps(
    {"action": "route", "target_chat_id": FOCAL_CHAT_ID, "reason": "Release news."}
)


async def _github_release(tag: str = "v0.16.0"):
    body = {
        "action": "published",
        "repository": {"full_name": "cyzus/suzent"},
        "release": {"tag_name": tag},
    }
    return await ingest_mailbox_event(
        body_bytes=json.dumps(body).encode(),
        headers={"x-github-event": "release"},
    )


@pytest.mark.asyncio
async def test_first_seen_github_release_auto_learns_rule_and_routes_to_regent(
    db, monkeypatch
):
    _fake_router(monkeypatch, _ROUTE_TO_REGENT)
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
        "zen": "Design for failure.",
        "repository": {"full_name": "cyzus/suzent-relay"},
    }
    res = await receive_webhook(
        _request(
            "POST",
            f"/hooks/{token}",
            body=json.dumps(payload).encode(),
            headers={
                "content-type": "application/json",
                "x-github-event": "ping",
            },
            path_params={"token": token},
        )
    )
    assert res.status_code == 202
    data = json.loads(res.body)
    assert data["route_status"] == "unrouted"
    assert data["target_chat_id"] is None

    # Rule should be wildcarded for quiet ping across repos
    rule = db.get_mailbox_rule_by_signature("github:ping:*")
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


@pytest.mark.asyncio
async def test_router_failure_routes_to_regent_without_saving_a_rule(db, monkeypatch):
    calls = _fake_router(monkeypatch, TimeoutError("router timed out"))

    first = await _github_release("v1")
    second = await _github_release("v2")

    assert first.route_status == "routed"
    assert first.target_chat_id == FOCAL_CHAT_ID
    assert first.rule_origin == "default"
    assert db.list_mailbox_rules() == []
    # Not remembered, so the next event of this kind is triaged again.
    assert second.target_chat_id == FOCAL_CHAT_ID
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_burst_of_a_new_event_kind_is_triaged_once(db, monkeypatch):
    calls = _fake_router(monkeypatch, _ROUTE_TO_REGENT, delay=0.05)

    items = await asyncio.gather(*(_github_release(f"v{i}") for i in range(3)))

    assert len(calls) == 1
    assert {item.target_chat_id for item in items} == {FOCAL_CHAT_ID}
    [rule] = db.list_mailbox_rules()
    assert rule.hit_count == 3


@pytest.mark.asyncio
async def test_learned_route_to_a_deleted_session_goes_to_regent(db, monkeypatch):
    calls = _fake_router(monkeypatch, _ROUTE_TO_REGENT)
    db.upsert_mailbox_rule(
        signature="github:release.published:cyzus/suzent",
        name="github · release.published",
        action="route",
        target_chat_id="deleted-session",
        target_label="Old session",
        origin="learned",
    )

    item = await _github_release()

    assert item.route_status == "routed"
    assert item.target_chat_id == FOCAL_CHAT_ID
    assert "no longer exists" in item.reason
    assert db.get_chat("deleted-session") is None
    # The stale learned rule is dropped, so the next event is triaged afresh.
    assert db.list_mailbox_rules() == []
    await _github_release("v2")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_manual_route_to_a_missing_session_is_rejected(db, monkeypatch):
    _fake_router(monkeypatch, _ROUTE_TO_REGENT)
    item = await _github_release()

    res = await mailbox_routes.route_mailbox_item_route(
        _request(
            "POST",
            f"/mailbox/items/{item.id}/route",
            body=json.dumps(
                {"action": "route", "target_chat_id": "missing-session"}
            ).encode(),
            path_params={"item_id": item.id},
        )
    )

    assert res.status_code == 400
    [rule] = db.list_mailbox_rules()
    assert rule.target_chat_id == FOCAL_CHAT_ID
