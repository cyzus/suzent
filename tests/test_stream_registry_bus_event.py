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
