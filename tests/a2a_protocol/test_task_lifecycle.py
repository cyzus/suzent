"""The A2A task state machine: legal transitions, interruption, and settling."""

import pytest

from suzent.a2a.tasks import TaskStore, TaskTransitionError
from suzent.a2a.types import (
    Artifact,
    Message,
    Role,
    TaskState,
    TextPart,
)


def _msg(text: str, role: Role = Role.user) -> Message:
    return Message(message_id=f"m-{text[:8]}", role=role, parts=[TextPart(text=text)])


@pytest.mark.asyncio
async def test_task_starts_submitted_with_history():
    store = TaskStore()
    task = await store.create(context_id="a2a:peer:ctx", message=_msg("do the thing"))

    assert task.status.state is TaskState.submitted
    assert task.context_id == "a2a:peer:ctx"
    assert [m.text() for m in task.history] == ["do the thing"]


@pytest.mark.asyncio
async def test_input_required_round_trip():
    """The state the old one-shot peer flow could not express."""
    store = TaskStore()
    task = await store.create(context_id="ctx", message=_msg("review this contract"))
    queue = store.record(task.id).subscribe()

    await store.set_state(task.id, TaskState.working)
    await store.set_state(
        task.id,
        TaskState.input_required,
        message=_msg("which jurisdiction?", Role.agent),
    )
    # Interruption ends the stream: the client must send a fresh request.
    assert store.get(task.id).status.state is TaskState.input_required

    await store.set_state(task.id, TaskState.working)
    await store.set_state(
        task.id, TaskState.completed, message=_msg("done", Role.agent)
    )

    states = []
    while not queue.empty():
        event = queue.get_nowait()
        states.append(None if event is None else (event.status.state, event.final))

    assert states == [
        (TaskState.working, False),
        (TaskState.input_required, True),
        None,
        (TaskState.working, False),
        (TaskState.completed, True),
        None,
    ]


@pytest.mark.asyncio
async def test_settled_task_cannot_be_revived():
    store = TaskStore()
    task = await store.create(context_id="ctx", message=_msg("go"))
    await store.set_state(task.id, TaskState.working)
    await store.set_state(task.id, TaskState.completed)

    with pytest.raises(TaskTransitionError):
        await store.set_state(task.id, TaskState.working)


@pytest.mark.asyncio
async def test_cancel_rejects_already_settled():
    store = TaskStore()
    task = await store.create(context_id="ctx", message=_msg("go"))
    await store.set_state(task.id, TaskState.working)

    canceled = await store.cancel(task.id)
    assert canceled.status.state is TaskState.canceled

    with pytest.raises(TaskTransitionError):
        await store.cancel(task.id)


@pytest.mark.asyncio
async def test_artifacts_stream_and_accumulate():
    store = TaskStore()
    task = await store.create(context_id="ctx", message=_msg("go"))
    queue = store.record(task.id).subscribe()
    await store.set_state(task.id, TaskState.working)

    await store.add_artifact(
        task.id, Artifact(artifact_id="a1", parts=[TextPart(text="Hel")])
    )
    await store.add_artifact(
        task.id,
        Artifact(artifact_id="a1", parts=[TextPart(text="lo")]),
        append=True,
        last_chunk=True,
    )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    updates = [e for e in events if getattr(e, "kind", "") == "artifact-update"]
    assert [u.append for u in updates] == [False, True]
    assert updates[-1].last_chunk is True
    assert len(store.get(task.id).artifacts) == 2


@pytest.mark.asyncio
async def test_eviction_never_drops_a_live_task():
    store = TaskStore(max_tasks=2)
    live = await store.create(context_id="ctx", message=_msg("live"))
    await store.set_state(live.id, TaskState.working)

    for index in range(4):
        done = await store.create(context_id="ctx", message=_msg(f"done{index}"))
        await store.set_state(done.id, TaskState.completed)

    assert store.get(live.id) is not None
    assert store.get(live.id).status.state is TaskState.working
