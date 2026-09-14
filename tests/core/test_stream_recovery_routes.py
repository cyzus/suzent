import asyncio
import json

import pytest
from starlette.requests import Request

from suzent.core import stream_registry
from suzent.routes.chat_routes import _recoverable_response, live_stream


def request(payload: object) -> Request:
    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(payload).encode(),
            "more_body": False,
        }

    return Request(
        {"type": "http", "method": "POST", "path": "/chat/live", "headers": []}, receive
    )


def decode(frame: str) -> dict:
    return json.loads(frame.removeprefix("data: "))


@pytest.fixture(autouse=True)
def clean_registry():
    stream_registry.background_queues.clear()
    yield
    stream_registry.background_queues.clear()


async def test_http_refresh_recovers_already_consumed_tokens():
    queue = stream_registry.register_background_stream("chat")
    await queue.put('data: {"type":"TEXT_MESSAGE_CONTENT","delta":"before"}\n\n')
    legacy = await live_stream(request({"chat_id": "chat"}))
    await anext(legacy.body_iterator)
    await legacy.body_iterator.aclose()
    response = await live_stream(request({"chat_id": "chat", "protocol": 1}))
    frame = decode(await anext(response.body_iterator))
    assert frame["events"][0]["delta"] == "before"
    await queue.put('data: {"type":"TEXT_MESSAGE_CONTENT","delta":"after"}\n\n')
    assert decode(await anext(response.body_iterator))["seq"] == 2
    await queue.put(None)
    assert decode(await anext(response.body_iterator))["type"] == "STREAM_END"
    await response.body_iterator.aclose()


@pytest.mark.parametrize("unregister", [False, True])
async def test_refresh_during_save_receives_snapshot_then_commit_confirmation(
    unregister,
):
    queue = stream_registry.register_background_stream("chat")
    release = asyncio.Event()

    async def save():
        await release.wait()
        return True

    queue.replay.persistence = asyncio.create_task(save())
    await queue.put('data: {"type":"TEXT_MESSAGE_CONTENT","delta":"answer"}\n\n')
    await queue.put(None)
    if unregister:
        stream_registry.unregister_background_stream("chat", queue)
        assert stream_registry.get_background_queue("chat") is queue
    response = await live_stream(request({"chat_id": "chat", "protocol": 1}))
    assert response.status_code == 200
    assert decode(await anext(response.body_iterator))["events"][0]["delta"] == "answer"
    release.set()
    assert decode(await anext(response.body_iterator))["persisted"] is True
    await response.body_iterator.aclose()
    idle = await live_stream(request({"chat_id": "chat", "protocol": 1}))
    assert idle.status_code == 204
    reconnect = await live_stream(
        request(
            {
                "chat_id": "chat",
                "protocol": 1,
                "run_id": queue.replay.run_id,
                "after_seq": 1,
            }
        )
    )
    assert decode(await anext(reconnect.body_iterator))["type"] == "STREAM_END"
    await reconnect.body_iterator.aclose()


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"chat_id": []},
        {"chat_id": "chat", "after_seq": True},
        {"chat_id": "chat", "after_seq": -1},
        {"chat_id": "chat", "protocol": 2},
    ],
)
async def test_invalid_recovery_request_returns_400(payload):
    assert (await live_stream(request(payload))).status_code == 400


@pytest.mark.parametrize("terminal", ["RUN_FINISHED", "AGENT_FINISHED"])
async def test_detached_direct_producer_survives_refresh_for_both_runtimes(terminal):
    release = asyncio.Event()

    async def runtime():
        yield 'data: {"type":"TEXT_MESSAGE_START","messageId":"m"}\n\n'
        yield 'data: {"type":"TEXT_MESSAGE_CONTENT","messageId":"m","delta":"before"}\n\n'
        await release.wait()
        yield 'data: {"type":"TEXT_MESSAGE_CONTENT","messageId":"m","delta":"after"}\n\n'
        yield f'data: {{"type":"{terminal}"}}\n\n'

    original = _recoverable_response("chat", runtime())
    await anext(original.body_iterator)
    await asyncio.sleep(0)
    await original.body_iterator.aclose()
    restored = await live_stream(request({"chat_id": "chat", "protocol": 1}))
    assert decode(await anext(restored.body_iterator))["events"][1]["delta"] == "before"
    release.set()
    frames = [decode(frame) async for frame in restored.body_iterator]
    assert frames[-1]["type"] == "STREAM_END"
    assert any(f.get("event", {}).get("delta") == "after" for f in frames)


def test_completed_replay_retention_is_bounded(monkeypatch):
    monkeypatch.setattr(stream_registry, "_MAX_COMPLETED_STREAMS", 2)
    for index in range(5):
        queue = stream_registry.register_background_stream(str(index))
        queue.put_nowait(None)
    stream_registry.get_background_queue("4")
    assert set(stream_registry.background_queues) == {"3", "4"}


def test_bus_overflow_closes_observer_instead_of_leaving_a_heartbeat_only_socket():
    observer = stream_registry.register_bus_subscriber()
    try:
        for _ in range(observer.maxsize + 1):
            stream_registry.emit_bus_event({"event": "test"})
        assert observer not in stream_registry._bus_subscribers
        frames = [observer.get_nowait() for _ in range(observer.qsize())]
        assert frames[-1] is None
    finally:
        stream_registry.unregister_bus_subscriber(observer)
