from types import SimpleNamespace

import pytest

from suzent.core.agent_inbox import AgentInboxDispatcher


def _message(attempts: int = 1) -> dict:
    return {
        "message_id": "msg-1",
        "sender_chat_id": "agent-source",
        "target_chat_id": "agent-target",
        "content": "Please review",
        "attempts": attempts,
    }


@pytest.mark.asyncio
async def test_dispatcher_acknowledges_successful_delivery(monkeypatch):
    acknowledged = []

    class FakeDatabase:
        def get_chat(self, chat_id):
            return SimpleNamespace(messages=[])

        def acknowledge_agent_message(self, message_id, *, worker_id):
            acknowledged.append((message_id, worker_id))
            return True

    dispatcher = AgentInboxDispatcher()
    delivered = []

    async def deliver(message):
        delivered.append(message["message_id"])

    monkeypatch.setattr("suzent.core.agent_inbox.get_database", lambda: FakeDatabase())
    monkeypatch.setattr(dispatcher, "_run_target_turn", deliver)

    await dispatcher._deliver_claimed(_message())

    assert delivered == ["msg-1"]
    assert acknowledged == [("msg-1", dispatcher.worker_id)]


@pytest.mark.asyncio
async def test_dispatcher_acks_marker_without_redelivering(monkeypatch):
    acknowledged = []

    class FakeDatabase:
        def get_chat(self, chat_id):
            return SimpleNamespace(
                messages=[
                    {"role": "user", "content": "<!-- suzent-agent-inbox:msg-1 -->"}
                ]
            )

        def acknowledge_agent_message(self, message_id, *, worker_id):
            acknowledged.append(message_id)
            return True

    dispatcher = AgentInboxDispatcher()

    async def unexpected_delivery(message):
        pytest.fail("persisted inbox marker should suppress duplicate delivery")

    monkeypatch.setattr("suzent.core.agent_inbox.get_database", lambda: FakeDatabase())
    monkeypatch.setattr(dispatcher, "_run_target_turn", unexpected_delivery)

    await dispatcher._deliver_claimed(_message())

    assert acknowledged == ["msg-1"]


@pytest.mark.asyncio
async def test_dispatcher_releases_failed_delivery_for_retry(monkeypatch):
    retried = []

    class FakeDatabase:
        def get_chat(self, chat_id):
            return SimpleNamespace(messages=[])

        def retry_agent_message(self, message_id, **kwargs):
            retried.append((message_id, kwargs))
            return True

    dispatcher = AgentInboxDispatcher()

    async def fail_delivery(message):
        raise RuntimeError("temporary failure")

    monkeypatch.setattr("suzent.core.agent_inbox.get_database", lambda: FakeDatabase())
    monkeypatch.setattr(dispatcher, "_run_target_turn", fail_delivery)

    await dispatcher._deliver_claimed(_message(attempts=2))

    assert retried[0][0] == "msg-1"
    assert retried[0][1]["worker_id"] == dispatcher.worker_id
    assert retried[0][1]["retry_delay_seconds"] == 4


@pytest.mark.asyncio
async def test_dispatcher_routes_peer_message_through_transport(monkeypatch):
    acknowledged = []
    delivered = []

    class FakeDatabase:
        def acknowledge_agent_message(self, message_id, *, worker_id):
            acknowledged.append((message_id, worker_id))
            return True

    class FakeTransport:
        async def deliver(self, message):
            delivered.append(message)

    message = {
        **_message(),
        "transport": "suzent_peer",
        "destination_peer_id": "peer-1",
    }
    dispatcher = AgentInboxDispatcher()
    monkeypatch.setattr("suzent.core.agent_inbox.get_database", lambda: FakeDatabase())
    monkeypatch.setattr(
        "suzent.nodes.agent_transport.get_peer_agent_transport",
        lambda: FakeTransport(),
    )

    await dispatcher._deliver_claimed(message)

    assert delivered == [message]
    assert acknowledged == [("msg-1", dispatcher.worker_id)]


@pytest.mark.asyncio
async def test_peer_delivery_uses_offline_tolerant_retry_window(monkeypatch):
    retried = []

    class FakeDatabase:
        def retry_agent_message(self, message_id, **kwargs):
            retried.append(kwargs)
            return True

    class FailingTransport:
        async def deliver(self, message):
            raise RuntimeError("peer offline")

    message = {
        **_message(attempts=10),
        "transport": "suzent_peer",
        "destination_peer_id": "peer-1",
    }
    monkeypatch.setattr("suzent.core.agent_inbox.get_database", lambda: FakeDatabase())
    monkeypatch.setattr(
        "suzent.nodes.agent_transport.get_peer_agent_transport",
        lambda: FailingTransport(),
    )

    await AgentInboxDispatcher()._deliver_claimed(message)

    assert retried[0]["retry_delay_seconds"] == 1024


@pytest.mark.asyncio
async def test_target_turn_uses_headless_config_and_delivery_marker(monkeypatch):
    captured = {}
    target = SimpleNamespace(title="Target", config={"platform": "personal"})
    sender = SimpleNamespace(title="Review agent", config={})

    class FakeDatabase:
        def get_chat(self, chat_id):
            return {"agent-target": target, "agent-source": sender}.get(chat_id)

    class FakeProcessor:
        async def process_background_turn(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("suzent.core.agent_inbox.get_database", lambda: FakeDatabase())
    monkeypatch.setattr(
        "suzent.agent_manager.build_agent_config",
        lambda base_config, require_social_tool=False: base_config,
    )
    monkeypatch.setattr(
        "suzent.core.chat_processor.ChatProcessor", lambda: FakeProcessor()
    )
    monkeypatch.setattr("suzent.core.stream_registry.stream_controls", {})

    message = _message()
    message["payload"] = {
        "citation_sources": [
            {
                "id": "sa_sub_a_src_1",
                "type": "webpage",
                "title": "Evidence",
                "url": "https://example.com/evidence",
            }
        ]
    }
    await AgentInboxDispatcher()._run_target_turn(message)

    assert captured["chat_id"] == "agent-target"
    assert captured["config_override"]["interaction_profile"] == "headless"
    assert (
        "[Agent message from Review agent (agent-source)]"
        in captured["message_content"]
    )
    assert "<!-- suzent-agent-inbox:msg-1 -->" in captured["message_content"]
    assert captured["message_content"].endswith("Please review")
    assert captured["incoming_citation_sources"][0]["id"] == "sa_sub_a_src_1"


@pytest.mark.asyncio
async def test_subagent_result_is_delivered_as_system_reminder(monkeypatch):
    captured = {}
    target = SimpleNamespace(title="Target", config={"platform": "personal"})
    sender = SimpleNamespace(title="Research agent", config={})

    class FakeDatabase:
        def get_chat(self, chat_id):
            return {"agent-target": target, "agent-source": sender}.get(chat_id)

    class FakeProcessor:
        async def process_background_turn(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("suzent.core.agent_inbox.get_database", lambda: FakeDatabase())
    monkeypatch.setattr(
        "suzent.agent_manager.build_agent_config",
        lambda base_config, require_social_tool=False: base_config,
    )
    monkeypatch.setattr(
        "suzent.core.chat_processor.ChatProcessor", lambda: FakeProcessor()
    )
    monkeypatch.setattr("suzent.core.stream_registry.stream_controls", {})

    message = _message()
    message["kind"] = "subagent_result"
    await AgentInboxDispatcher()._run_target_turn(message)

    assert captured["message_content"] == ""
    assert captured["system_reminders"] == [
        "Please review\n<!-- suzent-agent-inbox:msg-1 -->"
    ]
