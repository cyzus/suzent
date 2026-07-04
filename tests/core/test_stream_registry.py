import asyncio

import suzent.core.stream_registry as stream_registry
from suzent.core.stream_registry import (
    background_queues,
    get_background_turn_lock,
    merge_pending_auto_approvals,
    pending_auto_approvals,
    pop_pending_auto_approvals,
    register_background_stream,
    try_register_background_stream,
    unregister_background_stream,
)


def teardown_function():
    pending_auto_approvals.clear()
    background_queues.clear()
    stream_registry._background_turn_locks.clear()


def test_merge_and_pop_pending_auto_approvals():
    chat_id = "chat-1"

    merge_pending_auto_approvals(chat_id, {"a": True})
    merge_pending_auto_approvals(chat_id, {"b": False})
    merge_pending_auto_approvals(chat_id, {"a": False})

    merged = pop_pending_auto_approvals(chat_id)
    assert merged == {"a": False, "b": False}
    assert pop_pending_auto_approvals(chat_id) == {}


def test_merge_pending_auto_approvals_ignores_empty_inputs():
    merge_pending_auto_approvals("", {"a": True})
    merge_pending_auto_approvals("chat-2", {})
    assert pending_auto_approvals == {}


def test_try_register_background_stream_rejects_active_producer():
    chat_id = "chat-3"

    first = try_register_background_stream(chat_id)
    second = try_register_background_stream(chat_id)

    assert first is not None
    assert second is None
    assert background_queues[chat_id] is first


def test_register_background_stream_can_replace_finished_queue():
    chat_id = "chat-4"
    first = register_background_stream(chat_id)
    asyncio.run(first.put(None))

    second = try_register_background_stream(chat_id)

    assert second is not None
    assert second is not first
    assert background_queues[chat_id] is second


def test_background_stream_queue_does_not_block_without_live_consumer():
    queue = register_background_stream("chat-5")

    async def fill_queue() -> None:
        for index in range(2500):
            await queue.put(f"data: {index}\n\n")

    asyncio.run(fill_queue())

    assert queue.qsize() == 2500


def test_unregister_background_stream_keeps_newer_queue():
    chat_id = "chat-6"
    old_queue = register_background_stream(chat_id)
    old_queue.producer_active = False
    new_queue = register_background_stream(chat_id)

    unregister_background_stream(chat_id, old_queue)

    assert background_queues[chat_id] is new_queue


def test_background_turn_locks_prune_idle(monkeypatch):
    async def scenario():
        monkeypatch.setattr(stream_registry, "_MAX_BACKGROUND_TURN_LOCKS", 3)

        # Hold one lock so it is not idle and must survive pruning.
        held = get_background_turn_lock("held")
        async with held:
            # Fill past the cap with idle (unlocked) locks.
            for i in range(3):
                get_background_turn_lock(f"idle_{i}")
            # This insertion trips the prune: idle locks are dropped, held stays.
            get_background_turn_lock("trigger")

            assert "held" in stream_registry._background_turn_locks
            assert "trigger" in stream_registry._background_turn_locks
            assert not any(
                k.startswith("idle_") for k in stream_registry._background_turn_locks
            )

    asyncio.run(scenario())


def test_background_turn_lock_is_stable_per_chat():
    assert get_background_turn_lock("stable") is get_background_turn_lock("stable")


def test_background_turn_locks_keep_locks_with_waiters(monkeypatch):
    async def scenario():
        monkeypatch.setattr(stream_registry, "_MAX_BACKGROUND_TURN_LOCKS", 3)

        contended = get_background_turn_lock("contended")
        await contended.acquire()  # holder

        # A second turn queues up as a waiter on the same lock.
        async def waiter():
            async with contended:
                pass

        waiter_task = asyncio.create_task(waiter())
        await asyncio.sleep(0)  # let the waiter enqueue

        # Release the holder: during the handoff, locked() briefly reads False,
        # but the lock still has a queued waiter and must not be pruned.
        contended.release()
        assert stream_registry._lock_in_use(contended)

        for i in range(3):
            get_background_turn_lock(f"idle_{i}")
        get_background_turn_lock("trigger")  # trips the prune

        assert "contended" in stream_registry._background_turn_locks

        await waiter_task

    asyncio.run(scenario())
