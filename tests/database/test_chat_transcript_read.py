from __future__ import annotations

from sqlalchemy import inspect

from suzent.database import ChatDatabase


def test_transcript_read_does_not_fetch_agent_state(temp_db: ChatDatabase) -> None:
    state = b"large agent state" * 65536
    chat_id = temp_db.create_chat(
        "Long conversation",
        {},
        [{"role": "assistant", "content": "Visible"}],
        agent_state=state,
    )
    chat = temp_db.get_chat(chat_id, include_agent_state=False)
    assert chat is not None
    assert "agent_state" in inspect(chat).unloaded
    payload = chat.model_dump(mode="json", by_alias=True, exclude={"agent_state"})
    assert payload["messages"][0]["content"] == "Visible"
    assert "agent_state" not in payload
    assert temp_db.get_chat(chat_id).agent_state == state
