"""Regression: manual /compact must survive a stale post-process finalize.

Reproduces the race where a prior turn's background post-process job (holding the
chat's state_revision as its expected_revision) finalizes AFTER /compact writes the
compacted agent_state. The fix makes /compact persist via commit_snapshot_state,
which bumps the revision so the stale finalize is rejected instead of clobbering
the compacted state with the full history.
"""

import tempfile
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from suzent.core.agent_serializer import serialize_state, deserialize_state
from suzent.core.commands.base import CommandContext, dispatch


@pytest.fixture
def db():
    from suzent.database import ChatDatabase

    with tempfile.TemporaryDirectory() as tmpdir:
        database = ChatDatabase(str(Path(tmpdir) / "test_compact_race.db"))
        yield database
        try:
            database.engine.dispose()
        except Exception:
            pass


def _full_history():
    return [
        ModelRequest(parts=[UserPromptPart(content=f"q{i}")])
        if i % 2 == 0
        else ModelResponse(parts=[TextPart(content=f"a{i}")])
        for i in range(12)
    ]


def _compacted_history():
    # What _perform_compression would yield: first msg + summary pair + tail.
    from suzent.core.context_compressor import (
        COMPACTION_SUMMARY_REQUEST_MARKER,
        COMPACTION_SUMMARY_RESPONSE_MARKER,
    )

    full = _full_history()
    summary_req = ModelRequest(
        parts=[UserPromptPart(content=f"{COMPACTION_SUMMARY_REQUEST_MARKER}\npreface")]
    )
    summary_resp = ModelResponse(
        parts=[TextPart(content=f"{COMPACTION_SUMMARY_RESPONSE_MARKER}\nthe summary")]
    )
    return full[:1] + [summary_req, summary_resp] + full[-2:]


@pytest.mark.asyncio
async def test_manual_compact_survives_stale_finalize(db, monkeypatch):
    # Prior turn persisted full history via a snapshot -> revision R.
    chat_id = db.create_chat(title="t", config={}, messages=[])
    full = _full_history()
    model_id = "test-model"
    state_R = serialize_state(full, model_id=model_id, tool_names=[])
    expected_revision = db.commit_snapshot_state(chat_id, state_R)
    assert expected_revision is not None

    # Route both the command's get_database and the no-op task wait.
    monkeypatch.setattr("suzent.database.get_database", lambda: db)

    async def _no_wait(prefix, timeout=None):
        return None

    monkeypatch.setattr(
        "suzent.core.task_registry.wait_for_background_task_prefix", _no_wait
    )

    # Stub the expensive LLM-backed compression with a deterministic compacted result.
    compacted = _compacted_history()

    async def _fake_perform_compression(self, messages, focus=None):
        return compacted

    monkeypatch.setattr(
        "suzent.core.context_compressor.ContextCompressor._perform_compression",
        _fake_perform_compression,
    )

    ctx = CommandContext(chat_id=chat_id, user_id="u", surface="manual")
    result = await dispatch(ctx, "/compact")
    assert result and "compacted" in result.lower()

    # State is compacted on disk now.
    chat = db.get_chat(chat_id)
    after_compact = deserialize_state(chat.agent_state)["message_history"]
    assert len(after_compact) == len(compacted)

    # The prior turn's stale post-process now finalizes with the OLD revision.
    # It must be rejected because /compact bumped the revision.
    finalized = db.finalize_state_if_revision_matches(
        chat_id=chat_id,
        expected_revision=expected_revision,
        agent_state=state_R,  # the full, uncompacted history
        messages=None,
    )
    assert finalized is False, "stale finalize should be rejected after compact"

    # Compacted state survived.
    chat = db.get_chat(chat_id)
    survived = deserialize_state(chat.agent_state)["message_history"]
    assert len(survived) == len(compacted)
