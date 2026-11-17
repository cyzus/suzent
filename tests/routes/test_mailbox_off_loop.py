"""Mailbox and chat writes must not run SQLite work on the event loop streams share.

A process-wide write lock can be held for seconds by a streaming chat; any
route that waits on it from the loop freezes the whole server.
"""

import asyncio
import threading

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.core.agent_inbox import AgentInboxDispatcher
from suzent.database import ChatDatabase


def _on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _watch(
    db: ChatDatabase, monkeypatch: pytest.MonkeyPatch, names: list[str]
) -> dict[str, bool]:
    seen: dict[str, bool] = {}
    for name in names:
        original = getattr(db, name)

        def wrapper(*args, _name=name, _original=original, **kwargs):
            seen[_name] = seen.get(_name, False) or _on_event_loop()
            return _original(*args, **kwargs)

        monkeypatch.setattr(db, name, wrapper)
    return seen


def test_mailbox_routes_query_off_the_event_loop(
    temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    from suzent.routes import mailbox_routes

    monkeypatch.setattr(mailbox_routes, "get_database", lambda: temp_db)
    monkeypatch.setattr("suzent.core.mailbox.get_database", lambda: temp_db)
    monkeypatch.setattr(
        mailbox_routes, "get_mailbox_webhook_path", lambda: "/webhooks/test"
    )
    seen = _watch(
        temp_db,
        monkeypatch,
        [
            "count_unread_mailbox_notifications",
            "mark_mailbox_notifications_read",
            "get_mailbox_item",
            "delete_mailbox_item",
            "list_mailbox_rules",
            "delete_mailbox_rule",
        ],
    )
    client = TestClient(
        Starlette(
            routes=[
                Route("/mailbox/unread", mailbox_routes.mailbox_unread_route),
                Route(
                    "/mailbox/read",
                    mailbox_routes.mark_mailbox_read_route,
                    methods=["POST"],
                ),
                Route("/mailbox/rules", mailbox_routes.list_mailbox_rules_route),
                Route(
                    "/mailbox/rules/{rule_id:int}",
                    mailbox_routes.delete_mailbox_rule_route,
                    methods=["DELETE"],
                ),
                Route("/mailbox/endpoint", mailbox_routes.get_mailbox_endpoint_route),
                Route(
                    "/mailbox/{item_id:int}",
                    mailbox_routes.get_mailbox_item_route,
                ),
                Route(
                    "/mailbox/{item_id:int}/delete",
                    mailbox_routes.delete_mailbox_item_route,
                    methods=["DELETE"],
                ),
            ]
        )
    )

    assert client.get("/mailbox/unread").json() == {"unread": 0}
    assert client.post("/mailbox/read", json={}).json() == {"marked": 0, "unread": 0}
    assert client.get("/mailbox/rules").json()["rules"] == []
    assert client.delete("/mailbox/rules/1").status_code == 404
    assert client.get("/mailbox/endpoint").json() == {"webhook_path": "/webhooks/test"}
    assert client.get("/mailbox/1").status_code == 404
    assert client.delete("/mailbox/1/delete").status_code == 404
    assert seen and not any(seen.values()), seen


def test_chat_update_and_mark_read_write_off_the_event_loop(
    temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    from suzent.routes import chat_routes

    monkeypatch.setattr(chat_routes, "get_database", lambda: temp_db)
    seen = _watch(temp_db, monkeypatch, ["update_chat", "get_chat", "mark_chat_read"])
    client = TestClient(
        Starlette(
            routes=[
                Route("/chats/{chat_id}", chat_routes.update_chat, methods=["PUT"]),
                Route(
                    "/chats/{chat_id}/mark-read",
                    chat_routes.mark_chat_read,
                    methods=["POST"],
                ),
            ]
        )
    )
    chat_id = temp_db.create_chat("Before", {})

    updated = client.put(f"/chats/{chat_id}", json={"title": "After"})
    missing = client.put("/chats/does-not-exist", json={"title": "x"})
    read = client.post(f"/chats/{chat_id}/mark-read")

    assert updated.json()["title"] == "After"
    assert missing.status_code == 404
    assert read.json() == {"ok": True}
    assert seen == {"update_chat": False, "get_chat": False, "mark_chat_read": False}


async def test_inbox_dispatcher_wakes_when_notified_from_a_worker_thread() -> None:
    dispatcher = AgentInboxDispatcher()
    dispatcher._loop = asyncio.get_running_loop()

    thread = threading.Thread(target=dispatcher.notify)
    thread.start()
    thread.join()

    await asyncio.wait_for(dispatcher._wake_event.wait(), timeout=1)
