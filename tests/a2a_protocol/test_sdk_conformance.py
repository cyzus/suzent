"""
Conformance: the *official* A2A SDK client must be able to drive our server.

Our own client and server were both written from the spec, so they could in
principle agree on a shared mistake. This test removes that risk by putting the
reference implementation on the other end of the wire. If Suzent ever drifts
from the standard, this is the test that fails.

``a2a-sdk`` is a dev-only dependency (see pyproject ``[project.optional-
dependencies].dev``); it is never imported by ``suzent.a2a`` at runtime.
"""

import json

import httpx
import pytest

from suzent.a2a import tasks as tasks_module
from suzent.config import CONFIG
from suzent.server import app

a2a_sdk = pytest.importorskip("a2a", reason="a2a-sdk (dev dependency) not installed")

from a2a.client import ClientConfig, ClientFactory  # noqa: E402
from a2a.types import GetTaskRequest, Message, Part, Role, SendMessageRequest  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_task_store(monkeypatch):
    monkeypatch.setattr(tasks_module, "_store", tasks_module.TaskStore())


@pytest.fixture(autouse=True)
def _published(monkeypatch):
    monkeypatch.setattr(CONFIG, "a2a_enabled", True, raising=False)


class _FakeProcessor:
    frames: list[str] = []

    def process_turn(self, **_kwargs):
        async def _gen():
            for frame in self.frames:
                yield frame

        return _gen()


@pytest.fixture(autouse=True)
def _stub_agent(monkeypatch):
    import suzent.agent_manager as agent_manager
    import suzent.core.chat_processor as chat_processor
    import suzent.database as database

    _FakeProcessor.frames = [
        f"data: {json.dumps({'type': 'TEXT_MESSAGE_CONTENT', 'delta': 'Delegated '})}\n\n",
        f"data: {json.dumps({'type': 'TEXT_MESSAGE_CONTENT', 'delta': 'and done.'})}\n\n",
    ]
    monkeypatch.setattr(chat_processor, "ChatProcessor", _FakeProcessor)
    monkeypatch.setattr(
        agent_manager, "build_agent_config", lambda *a, **k: {}, raising=False
    )

    class _FakeDB:
        def ensure_channel_chat(self, *a, **k):
            return True

    monkeypatch.setattr(database, "get_database", lambda: _FakeDB(), raising=False)


@pytest.fixture
async def sdk_client():
    """A reference-SDK client wired to our in-process app."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as http:
        factory = ClientFactory(ClientConfig(httpx_client=http, streaming=True))
        yield await factory.create_from_url("http://testserver")


def _user_message(text: str) -> Message:
    return Message(message_id="sdk-1", role=Role.ROLE_USER, parts=[Part(text=text)])


@pytest.mark.asyncio
async def test_sdk_resolves_our_agent_card(sdk_client):
    """Card resolution is the SDK's own parser accepting our document."""
    assert sdk_client is not None


def _task_id_of(response) -> str:
    """Task id from whichever stream member the SDK surfaced."""
    for field in ("status_update", "artifact_update"):
        member = getattr(response, field, None)
        if member is not None and getattr(member, "task_id", ""):
            return member.task_id
    return getattr(getattr(response, "task", None), "id", "")


@pytest.mark.asyncio
async def test_sdk_reads_our_lifecycle_and_streamed_text(sdk_client):
    """The reference client must see working → artifact → completed."""
    states, streamed_text = [], ""
    async for response in sdk_client.send_message(
        SendMessageRequest(message=_user_message("do the thing"))
    ):
        if response.HasField("status_update"):
            states.append(response.status_update.status.state)
        if response.HasField("artifact_update"):
            streamed_text += "".join(
                part.text for part in response.artifact_update.artifact.parts
            )

    from a2a.types import TaskState

    assert states[0] == TaskState.TASK_STATE_WORKING
    assert states[-1] == TaskState.TASK_STATE_COMPLETED
    assert streamed_text == "Delegated and done."


@pytest.mark.asyncio
async def test_sdk_can_fetch_a_task_we_created(sdk_client):
    task_id = ""
    async for response in sdk_client.send_message(
        SendMessageRequest(message=_user_message("go"))
    ):
        task_id = _task_id_of(response) or task_id

    assert task_id, "our stream never carried a task id the SDK could read"

    fetched = await sdk_client.get_task(GetTaskRequest(id=task_id))
    assert fetched.id == task_id
