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
@pytest.mark.parametrize("kind", ["agent_message", "remote_agent_message"])
async def test_target_turn_uses_headless_config_and_delivery_marker(monkeypatch, kind):
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
    message["kind"] = kind
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
    assert captured["message_content"] == ""
    reminder = captured["system_reminders"][0]
    assert "[Agent message from Review agent (agent-source)]" in reminder
    assert "<!-- suzent-agent-inbox:msg-1 -->" in reminder
    assert reminder.endswith("Please review")
    if kind == "remote_agent_message":
        assert captured["config_override"]["permission_mode"] == "auto"
    assert captured["incoming_citation_sources"][0]["id"] == "sa_sub_a_src_1"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["subagent_result", "background_task_result"])
async def test_subagent_result_is_delivered_as_system_reminder(monkeypatch, kind):
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
    message["kind"] = kind
    await AgentInboxDispatcher()._run_target_turn(message)

    assert captured["message_content"] == ""
    assert captured["system_reminders"] == [
        "Please review\n<!-- suzent-agent-inbox:msg-1 -->"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["agent_message", "remote_agent_message"])
async def test_acp_inbox_messages_use_local_reminder_wrapper(monkeypatch, kind):
    from suzent.core.system_reminder import (
        PUA_START,
        RUNTIME_NONCE,
        extract_system_reminder_display_trigger,
    )

    captured = {}
    target = SimpleNamespace(title="Target", config={"runtime": "acp"})

    class FakeDatabase:
        def get_chat(self, chat_id):
            return target

    async def run_turn(chat_id, content, config, run_id, **kwargs):
        captured.update(content=content, **kwargs)

    monkeypatch.delenv("SUZENT_XML_SYSTEM_REMINDER", raising=False)
    monkeypatch.setattr("suzent.core.agent_inbox.get_database", lambda: FakeDatabase())
    monkeypatch.setattr(
        "suzent.agent_manager.build_agent_config",
        lambda base_config, require_social_tool=False: base_config,
    )
    monkeypatch.setattr("suzent.acp.runtime.run_acp_turn_text", run_turn)
    monkeypatch.setattr("suzent.core.stream_registry.stream_controls", {})
    await AgentInboxDispatcher()._run_target_turn({**_message(), "kind": kind})

    assert captured["runtime_authored"] is True
    assert PUA_START + RUNTIME_NONCE in captured["content"]
    trigger = extract_system_reminder_display_trigger(captured["content"])
    assert "Please review" in trigger
    assert "<!-- suzent-agent-inbox:msg-1 -->" in trigger


def _subagent_chat(parent_chat_id: str = "agent-source") -> SimpleNamespace:
    return SimpleNamespace(
        id="agent-target",
        title="Sub-agent: research",
        messages=[],
        config={
            "platform": "subagent",
            "parent_chat_id": parent_chat_id,
            "subagent_task_id": "sub_abc",
        },
    )


def _capture_enqueue(monkeypatch) -> list[dict]:
    queued: list[dict] = []

    def enqueue(**kwargs):
        queued.append(kwargs)
        return {"message_id": kwargs["message_id"], "status": "pending"}, True

    monkeypatch.setattr("suzent.core.agent_inbox.enqueue_agent_message", enqueue)
    return queued


@pytest.mark.asyncio
async def test_subagent_reply_to_its_parent_wakes_the_parent(monkeypatch):
    from suzent.core.agent_inbox import AgentReply

    target = _subagent_chat()
    monkeypatch.setattr(
        "suzent.core.agent_inbox.get_database",
        lambda: SimpleNamespace(get_chat=lambda chat_id: target),
    )
    queued = _capture_enqueue(monkeypatch)
    dispatcher = AgentInboxDispatcher()

    async def run_turn(message):
        return AgentReply(
            text="Found it in core/x.py",
            citation_sources=[{"id": "src_1", "title": "Doc", "url": "https://a.b"}],
        )

    monkeypatch.setattr(dispatcher, "_run_target_turn", run_turn)

    await dispatcher._deliver({**_message(), "kind": "agent_message"})

    assert len(queued) == 1
    reply = queued[0]
    assert reply["message_id"] == "subagent-reply-msg-1"
    assert reply["sender_chat_id"] == "agent-target"
    assert reply["target_chat_id"] == "agent-source"
    assert reply["kind"] == "subagent_result"
    assert "Sub-agent `sub_abc` replied" in reply["content"]
    assert "Your message: Please review" in reply["content"]
    assert "Found it in core/x.py" in reply["content"]
    sources = reply["payload"]["citation_sources"]
    assert sources[0]["id"] == "sa_sub_abc_msg_1_src_1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target", "kind"),
    [
        (_subagent_chat(parent_chat_id="someone-else"), "agent_message"),
        (
            SimpleNamespace(config={"platform": "personal"}, messages=[]),
            "agent_message",
        ),
        (_subagent_chat(), "subagent_result"),
    ],
)
async def test_other_replies_stay_in_the_target_chat(monkeypatch, target, kind):
    from suzent.core.agent_inbox import AgentReply

    monkeypatch.setattr(
        "suzent.core.agent_inbox.get_database",
        lambda: SimpleNamespace(get_chat=lambda chat_id: target),
    )
    queued = _capture_enqueue(monkeypatch)
    dispatcher = AgentInboxDispatcher()

    async def run_turn(message):
        return AgentReply(text="done")

    monkeypatch.setattr(dispatcher, "_run_target_turn", run_turn)

    await dispatcher._deliver({**_message(), "kind": kind})

    assert queued == []


@pytest.mark.asyncio
async def test_message_joining_a_live_turn_sends_no_separate_reply(monkeypatch):
    target = _subagent_chat()
    monkeypatch.setattr(
        "suzent.core.agent_inbox.get_database",
        lambda: SimpleNamespace(get_chat=lambda chat_id: target),
    )
    queued = _capture_enqueue(monkeypatch)
    dispatcher = AgentInboxDispatcher()

    async def run_turn(message):
        return None

    monkeypatch.setattr(dispatcher, "_run_target_turn", run_turn)

    await dispatcher._deliver({**_message(), "kind": "agent_message"})

    assert queued == []


@pytest.mark.asyncio
async def test_target_turn_returns_its_reply_and_sources(monkeypatch):
    target = SimpleNamespace(title="Target", config={"platform": "subagent"})

    class FakeProcessor:
        async def process_background_turn(self, **kwargs):
            kwargs["citation_sources_out"].append({"id": "src_1"})
            return "All tests pass"

    monkeypatch.setattr(
        "suzent.core.agent_inbox.get_database",
        lambda: SimpleNamespace(get_chat=lambda chat_id: target),
    )
    monkeypatch.setattr(
        "suzent.agent_manager.build_agent_config",
        lambda base_config, require_social_tool=False: base_config,
    )
    monkeypatch.setattr(
        "suzent.core.chat_processor.ChatProcessor", lambda: FakeProcessor()
    )
    monkeypatch.setattr("suzent.core.stream_registry.stream_controls", {})

    reply = await AgentInboxDispatcher()._run_target_turn(_message())

    assert reply.text == "All tests pass"
    assert reply.citation_sources == [{"id": "src_1"}]


@pytest.mark.asyncio
async def test_deliver_and_wait_returns_the_reply_without_queueing(monkeypatch):
    from suzent.core import agent_inbox
    from suzent.core.agent_inbox import AgentReply, deliver_and_wait

    delivered = []
    dispatcher = AgentInboxDispatcher()

    async def run_turn(message):
        delivered.append(message)
        return AgentReply(text="Fixed")

    monkeypatch.setattr(dispatcher, "_run_target_turn", run_turn)
    monkeypatch.setattr(agent_inbox, "get_agent_inbox_dispatcher", lambda: dispatcher)
    queued = _capture_enqueue(monkeypatch)

    reply = await deliver_and_wait(
        sender_chat_id="agent-source", target_chat_id="agent-target", content="Fix"
    )

    assert reply.text == "Fixed"
    assert delivered[0]["content"] == "Fix"
    assert delivered[0]["kind"] == "agent_message"
    assert queued == []


@pytest.mark.asyncio
async def test_cancelled_wait_lets_the_turn_finish_and_routes_the_reply(monkeypatch):
    import asyncio

    from suzent.core import agent_inbox
    from suzent.core.agent_inbox import AgentReply, deliver_and_wait

    release = asyncio.Event()
    dispatcher = AgentInboxDispatcher()

    async def run_turn(message):
        await release.wait()
        return AgentReply(text="Finished anyway")

    target = _subagent_chat()
    monkeypatch.setattr(dispatcher, "_run_target_turn", run_turn)
    monkeypatch.setattr(agent_inbox, "get_agent_inbox_dispatcher", lambda: dispatcher)
    monkeypatch.setattr(
        "suzent.core.agent_inbox.get_database",
        lambda: SimpleNamespace(get_chat=lambda chat_id: target),
    )
    queued = _capture_enqueue(monkeypatch)

    waiter = asyncio.create_task(
        deliver_and_wait(
            sender_chat_id="agent-source", target_chat_id="agent-target", content="Go"
        )
    )
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    release.set()
    for _ in range(5):
        await asyncio.sleep(0)

    assert len(queued) == 1
    assert "Finished anyway" in queued[0]["content"]
    assert queued[0]["target_chat_id"] == "agent-source"


@pytest.mark.asyncio
async def test_retry_after_a_lost_reply_sends_it_from_the_transcript(monkeypatch):
    target = _subagent_chat()
    target.messages = [
        {"role": "user", "content": "<!-- suzent-agent-inbox:msg-1 -->\nPlease review"},
        {"role": "assistant", "parts": [{"type": "text", "text": "Reviewed: 2 bugs"}]},
    ]
    acknowledged = []

    class FakeDatabase:
        def get_chat(self, chat_id):
            return target

        def acknowledge_agent_message(self, message_id, *, worker_id):
            acknowledged.append(message_id)
            return True

    monkeypatch.setattr("suzent.core.agent_inbox.get_database", lambda: FakeDatabase())
    queued = _capture_enqueue(monkeypatch)
    dispatcher = AgentInboxDispatcher()

    async def unexpected_turn(message):
        pytest.fail("a persisted turn must not run again")

    monkeypatch.setattr(dispatcher, "_run_target_turn", unexpected_turn)

    await dispatcher._deliver_claimed({**_message(), "kind": "agent_message"})

    assert acknowledged == ["msg-1"]
    assert len(queued) == 1
    assert queued[0]["message_id"] == "subagent-reply-msg-1"
    assert "Reviewed: 2 bugs" in queued[0]["content"]


@pytest.mark.asyncio
async def test_a_failed_reply_enqueue_retries_the_delivery(monkeypatch):
    from suzent.core.agent_inbox import AgentReply

    target = _subagent_chat()
    retried = []

    class FakeDatabase:
        def get_chat(self, chat_id):
            return target

        def acknowledge_agent_message(self, message_id, *, worker_id):
            pytest.fail("a delivery whose reply was lost must not be acknowledged")

        def retry_agent_message(self, message_id, **kwargs):
            retried.append(message_id)
            return True

    def failing_enqueue(**kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr("suzent.core.agent_inbox.get_database", lambda: FakeDatabase())
    monkeypatch.setattr(
        "suzent.core.agent_inbox.enqueue_agent_message", failing_enqueue
    )
    dispatcher = AgentInboxDispatcher()

    async def run_turn(message):
        return AgentReply(text="done")

    monkeypatch.setattr(dispatcher, "_run_target_turn", run_turn)

    await dispatcher._deliver_claimed({**_message(), "kind": "agent_message"})

    assert retried == ["msg-1"]
