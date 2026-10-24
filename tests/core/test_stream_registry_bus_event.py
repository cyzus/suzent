from suzent.core.stream_registry import (
    emit_bus_event,
    register_bus_subscriber,
    unregister_bus_subscriber,
)


def test_emit_bus_event_broadcasts_payload() -> None:
    q = register_bus_subscriber()
    try:
        payload = {
            "event": "auto_compaction",
            "chat_id": "chat-1",
            "tokens_before": 100,
        }
        emit_bus_event(payload)
        assert q.get_nowait() == payload
    finally:
        unregister_bus_subscriber(q)


def test_emit_bus_event_ignores_non_dict_payload() -> None:
    q = register_bus_subscriber()
    try:
        emit_bus_event("not-a-dict")
        assert q.empty()
    finally:
        unregister_bus_subscriber(q)


def test_stream_events_carry_their_run_id() -> None:
    from suzent.core.stream_registry import (
        background_queues,
        register_background_stream,
    )

    chat_id = "chat-run-id"
    q = register_bus_subscriber()
    try:
        first = register_background_stream(chat_id)
        first.put_nowait("data: one\n\n")
        # A steer supersedes the first run while it is still draining.
        second = register_background_stream(chat_id)
        first.put_nowait("data: late\n\n")
        second.put_nowait(None)

        events = []
        while not q.empty():
            events.append(q.get_nowait())
        old, new = first.replay.run_id, second.replay.run_id
        assert old != new
        assert [(e["event"], e.get("run_id")) for e in events] == [
            ("stream_started", old),
            ("chunk", old),
            ("stream_ended", old),
            ("stream_started", new),
            ("chunk", old),
            ("stream_ended", new),
        ]
    finally:
        unregister_bus_subscriber(q)
        background_queues.pop(chat_id, None)
