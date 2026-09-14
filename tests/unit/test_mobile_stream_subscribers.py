"""Mobile and desktop observers must not consume one another's events."""

from suzent.core.stream_registry import _BusStreamQueue
from unittest.mock import AsyncMock

import pytest


async def test_two_observers_receive_the_same_turn_and_completion() -> None:
    stream = _BusStreamQueue("mobile-test")
    await stream.put("first")
    phone = stream.subscribe()
    desktop = stream.subscribe()
    await stream.put("second")
    await stream.put(None)
    for observer in (phone, desktop):
        assert [await observer.get() for _ in range(3)] == ["first", "second", None]
        stream.unsubscribe(observer)
    assert not stream.producer_active
    assert not stream._subscribers


async def test_backgrounding_phone_does_not_cancel_producer_or_desktop() -> None:
    stream = _BusStreamQueue("mobile-test")
    phone = stream.subscribe()
    desktop = stream.subscribe()
    stream.unsubscribe(phone)
    await stream.put("after background")
    assert stream.producer_active
    assert phone.empty()
    assert await desktop.get() == "after background"
    restored = stream.subscribe()
    assert await restored.get() == "after background"


async def test_slow_observer_ends_without_blocking_other_observers() -> None:
    stream = _BusStreamQueue("mobile-test", maxsize=2)
    slow = stream.subscribe()
    fast = stream.subscribe()
    for chunk in ("one", "two", "three"):
        await stream.put(chunk)
        assert await fast.get() == chunk
    assert "REPLAY_UNAVAILABLE" in await slow.get()
    assert await slow.get() is None
    assert slow not in stream._subscribers
    assert stream.producer_active
    late = stream.subscribe()
    assert "REPLAY_UNAVAILABLE" in await late.get()
    assert await late.get() is None


async def test_late_observer_can_read_completed_turn() -> None:
    stream = _BusStreamQueue("mobile-test")
    await stream.put("reply")
    await stream.put(None)
    observer = stream.subscribe()
    assert [await observer.get(), await observer.get()] == ["reply", None]
    assert not stream._subscribers


async def test_live_route_detaches_only_the_disconnected_observer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from suzent.routes import chat_routes

    stream = _BusStreamQueue("route-test")
    monkeypatch.setattr(chat_routes, "get_background_queue", lambda _: stream)
    request = AsyncMock()
    request.json.return_value = {"chat_id": "route-test", "replay": True}
    first = await chat_routes.live_stream(request)
    second = await chat_routes.live_stream(request)
    await stream.put("data: first\n\n")
    assert await anext(first.body_iterator) == "data: first\n\n"
    assert await anext(second.body_iterator) == "data: first\n\n"
    await first.body_iterator.aclose()
    assert len(stream._subscribers) == 1
    await stream.put("data: second\n\n")
    assert await anext(second.body_iterator) == "data: second\n\n"
    await second.body_iterator.aclose()
    assert not stream._subscribers
    assert stream.producer_active


async def test_mobile_replay_preserves_desktop_unread_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from suzent.routes import chat_routes

    stream = _BusStreamQueue("compatibility")
    monkeypatch.setattr(chat_routes, "get_background_queue", lambda _: stream)
    await stream.put("data: first\n\n")
    desktop_request = AsyncMock()
    desktop_request.json.return_value = {"chat_id": "compatibility"}
    desktop = await chat_routes.live_stream(desktop_request)
    assert await anext(desktop.body_iterator) == "data: first\n\n"
    await desktop.body_iterator.aclose()
    await stream.put("data: second\n\n")
    phone_request = AsyncMock()
    phone_request.json.return_value = {"chat_id": "compatibility", "replay": True}
    phone = await chat_routes.live_stream(phone_request)
    assert await anext(phone.body_iterator) == "data: first\n\n"
    assert await anext(phone.body_iterator) == "data: second\n\n"
    resumed = await chat_routes.live_stream(desktop_request)
    assert await anext(resumed.body_iterator) == "data: second\n\n"
    await phone.body_iterator.aclose()
    await resumed.body_iterator.aclose()
