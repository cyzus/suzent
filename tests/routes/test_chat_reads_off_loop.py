"""Chat reads must not run their SQLite work on the event loop streams share."""

import asyncio

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.database import ChatDatabase


def _on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def test_chat_list_and_chat_load_query_off_the_event_loop(
    temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    from suzent.routes import chat_routes

    seen: dict[str, bool] = {}

    def watch(name: str) -> None:
        original = getattr(temp_db, name)

        def wrapper(*args, **kwargs):
            seen[name] = _on_event_loop()
            return original(*args, **kwargs)

        monkeypatch.setattr(temp_db, name, wrapper)

    for name in ("list_chats", "get_chat_count", "get_chat"):
        watch(name)
    monkeypatch.setattr(chat_routes, "get_database", lambda: temp_db)
    client = TestClient(
        Starlette(
            routes=[
                Route("/chats", chat_routes.get_chats),
                Route("/chats/{chat_id}", chat_routes.get_chat),
            ]
        )
    )
    chat_id = temp_db.create_chat("Busy", {})

    listing = client.get("/chats")
    loaded = client.get(f"/chats/{chat_id}")
    missing = client.get("/chats/does-not-exist")

    assert [chat["id"] for chat in listing.json()["chats"]] == [chat_id]
    assert loaded.json()["id"] == chat_id
    assert missing.status_code == 404
    assert seen == {"list_chats": False, "get_chat_count": False, "get_chat": False}
