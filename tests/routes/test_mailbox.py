"""Tests for the unified Mailbox & Dynamic LLM-Crystallized Router."""

import asyncio
import json

import pytest
from starlette.requests import Request

from suzent.core.focal_agent import FOCAL_CHAT_ID, get_or_create_focal_chat
from suzent.core.agent_inbox import enqueue_agent_message
from datetime import datetime, timedelta

from suzent.core.mailbox import (
    flush_due_digests,
    get_or_create_mailbox_token,
    route_inbound,
    webhook_envelope,
)
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


def _decision(target=FOCAL_CHAT_ID, delivery="wake", action="route") -> str:
    return json.dumps(
        {"action": action, "target": target, "delivery": delivery, "reason": "Test."}
    )


_ROUTE_TO_REGENT = _decision()


async def _github_release(tag: str = "v0.16.0"):
    body = {
        "action": "published",
        "repository": {"full_name": "cyzus/suzent"},
        "release": {"tag_name": tag},
    }
    return await route_inbound(
        webhook_envelope(json.dumps(body).encode(), {"x-github-event": "release"})
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


async def _list(query: bytes = b"") -> dict:
    res = await mailbox_routes.list_mailbox_items_route(
        _request("GET", "/mailbox/items", query_string=query)
    )
    return json.loads(res.body)


@pytest.mark.asyncio
async def test_agent_messages_are_recorded_once_when_sent(db, monkeypatch):
    _fake_router(monkeypatch, _ROUTE_TO_REGENT)
    get_or_create_focal_chat()
    regent_chat = db.create_chat(title="Project work", config={})
    enqueue_agent_message(
        message_id="m-agent",
        sender_chat_id=regent_chat,
        target_chat_id=FOCAL_CHAT_ID,
        content="Tests are green.\nDetails follow.",
    )
    enqueue_agent_message(
        message_id="m-bg",
        sender_chat_id=None,
        target_chat_id=FOCAL_CHAT_ID,
        content="background output",
        kind="background_task_result",
    )
    # Delivering a routed webhook goes through the agent inbox too, but the
    # webhook already has its item.
    await _github_release()

    data = await _list()
    kinds = sorted(item["source_kind"] for item in data["items"])
    assert kinds == ["agent_inbox", "webhook"]
    [mail] = [i for i in data["items"] if i["source_kind"] == "agent_inbox"]
    assert mail["summary"] == "Tests are green."
    assert mail["source_name"].endswith("Project work")
    assert mail["event_type"] == "mail"
    assert mail["headers"]["from"] == regent_chat
    assert mail["headers"]["status"] == "pending"
    assert mail["inbox_message_id"] == "m-agent"
    assert data["counts"] == {"all": 2, "routed": 2, "unrouted": 0}


@pytest.mark.asyncio
async def test_peer_device_messages_are_recorded_as_peer(db):
    peer_chat = db.create_chat(title="Laptop", config={})
    enqueue_agent_message(
        message_id="m-peer",
        sender_chat_id=None,
        target_chat_id=peer_chat,
        content="Hello from the laptop",
        kind="remote_agent_message",
        payload={"sender_label": "Laptop", "sender_agent_id": "device:abc"},
    )

    [item] = (await _list())["items"]
    assert item["source_kind"] == "peer"
    assert item["signature"] == "peer:abc"
    assert item["source_name"] == "Laptop"


@pytest.mark.asyncio
async def test_listing_pages_and_filters_in_the_database(db):
    get_or_create_focal_chat()
    for i in range(5):
        enqueue_agent_message(
            message_id=f"m{i}",
            sender_chat_id=None,
            target_chat_id=FOCAL_CHAT_ID,
            content=f"note {i}",
        )

    page = await _list(b"limit=2&offset=1")
    assert [i["summary"] for i in page["items"]] == ["note 3", "note 2"]
    assert page["counts"]["all"] == 5
    assert (await _list(b"route_status=unrouted"))["items"] == []


@pytest.mark.asyncio
async def test_failed_delivery_shows_as_error_and_items_can_be_deleted(db):
    get_or_create_focal_chat()
    enqueue_agent_message(
        message_id="m-fail",
        sender_chat_id=None,
        target_chat_id=FOCAL_CHAT_ID,
        content="will fail",
        max_attempts=1,
    )
    claimed = db.claim_next_agent_message(worker_id="w")
    db.retry_agent_message(
        claimed["message_id"], worker_id="w", error="boom", retry_delay_seconds=0
    )

    [item] = (await _list())["items"]
    assert item["route_status"] == "error"
    assert item["headers"]["status"] == "failed"

    res = await mailbox_routes.delete_mailbox_item_route(
        _request(
            "DELETE",
            f"/mailbox/items/{item['id']}",
            path_params={"item_id": item["id"]},
        )
    )
    assert res.status_code == 200
    assert (await _list())["items"] == []


@pytest.mark.asyncio
async def test_notify_only_tells_the_user(db, monkeypatch):
    _fake_router(monkeypatch, _decision(delivery="notify"))

    item = await _github_release()

    assert item.route_status == "notified"
    assert item.inbox_message_id is None
    assert db.list_agent_messages() == []
    [note] = db.drain_background_notifications()
    assert note.source == "mailbox"
    assert "v0.16.0" in note.result


@pytest.mark.asyncio
async def test_project_target_starts_a_new_session_per_event(db, monkeypatch):
    project_id = db.create_project("Suzent", "suzent")
    _fake_router(monkeypatch, _decision(target=f"project:{project_id}"))

    first = await _github_release("v1")
    second = await _github_release("v2")

    assert first.target_chat_id != second.target_chat_id
    for item in (first, second):
        chat = db.get_chat(item.target_chat_id)
        assert chat.project_id == project_id
        [message] = db.list_agent_messages(target_chat_id=item.target_chat_id)
        assert "Mailbox Event" in message["content"]
    [rule] = db.list_mailbox_rules()
    assert rule.target_project_id == project_id
    assert rule.target_chat_id is None


@pytest.mark.asyncio
async def test_digest_batches_events_until_its_interval(db, monkeypatch):
    get_or_create_focal_chat()
    _fake_router(monkeypatch, _decision(delivery="digest"))
    [rule] = [await _github_release("v1")] and db.list_mailbox_rules()
    db.update_mailbox_rule(
        rule.id,
        action="route",
        target_chat_id=FOCAL_CHAT_ID,
        delivery="digest",
        digest_minutes=30,
        prompt="Summarise these releases.",
    )
    await _github_release("v2")

    assert {i["route_status"] for i in (await _list())["items"]} == {"queued"}
    assert flush_due_digests(datetime.now()) == 0
    assert flush_due_digests(datetime.now() + timedelta(minutes=31)) == 1

    [digest] = db.list_agent_messages(target_chat_id=FOCAL_CHAT_ID)
    assert "2 event(s)" in digest["content"]
    assert "Summarise these releases." in digest["content"]
    assert "v1" in digest["content"] and "v2" in digest["content"]
    items = (await _list())["items"]
    assert {i["route_status"] for i in items} == {"routed"}
    assert {i["inbox_message_id"] for i in items} == {digest["message_id"]}


@pytest.mark.asyncio
async def test_queued_events_of_a_deleted_digest_rule_are_kept_unrouted(
    db, monkeypatch
):
    _fake_router(monkeypatch, _decision(delivery="digest"))
    item = await _github_release()
    db.delete_mailbox_rule(item.rule_id)

    flush_due_digests(datetime.now() + timedelta(days=1))

    assert db.get_mailbox_item(item.id).route_status == "unrouted"
    assert db.list_agent_messages() == []


async def _put_rule(rule_id: int, body: dict):
    return await mailbox_routes.update_mailbox_rule_route(
        _request(
            "PUT",
            f"/mailbox/rules/{rule_id}",
            body=json.dumps(body).encode(),
            path_params={"rule_id": rule_id},
        )
    )


@pytest.mark.asyncio
async def test_rule_edits_set_project_target_delivery_and_prompt(db, monkeypatch):
    _fake_router(monkeypatch, _ROUTE_TO_REGENT)
    await _github_release()
    [rule] = db.list_mailbox_rules()
    project_id = db.create_project("Suzent", "suzent")

    res = await _put_rule(
        rule.id,
        {
            "action": "route",
            "target_chat_id": f"project:{project_id}",
            "delivery": "digest",
            "digest_minutes": 15,
            "prompt": "Triage it.",
        },
    )

    assert res.status_code == 200
    saved = json.loads(res.body)["rule"]
    assert saved["target_project_id"] == project_id
    assert saved["target_chat_id"] is None
    assert saved["target_label"] == "New session in Suzent"
    assert (saved["delivery"], saved["digest_minutes"], saved["prompt"]) == (
        "digest",
        15,
        "Triage it.",
    )
    assert saved["origin"] == "pinned"
    bad = await _put_rule(rule.id, {"action": "route", "delivery": "shout"})
    assert bad.status_code == 400
