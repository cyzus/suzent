"""Typed capture labels every candidate, and a deterministic gate checks the labels.

Unlabelled extraction stored the agent's own words, scheduled-task specs and context-free
choices as facts about the user. Capture asks the model where each candidate came from
and the exact words behind it; the gate drops what those labels prove is not a memory.
"""

import json
from types import SimpleNamespace

import pytest

from suzent.database.chat_log import ChatEventLog
from suzent.memory import capture
from suzent.memory.capture import CapturedFact, CaptureResponse
from suzent.memory.extraction_queue import CURSORS_FILE, ExtractionQueue
from suzent.memory.markdown_store import MarkdownMemoryStore

BATCH = """## Earlier context (already processed; do not extract)

### Turn on 2026-10-20
USER: I used to live in Paris

## New turns

### Turn on 2026-10-22
USER: I always drink tea, never coffee. Keep commit messages short, no emoji.
ACTION: read_file(persona.md) -> The user is a night owl
ASSISTANT: You mentioned you are a morning person."""


def _fact(**overrides) -> CapturedFact:
    values = {
        "content": "User prefers tea over coffee",
        "kind": "user",
        "source": "user_said",
        "evidence": "I always drink tea, never coffee",
        "horizon": "durable",
        "category": "preference",
        "importance": 0.6,
    }
    values.update(overrides)
    return CapturedFact(**values)


def _dropped(result: capture.GateResult) -> list[str]:
    return [code for code, _ in result.dropped]


# --- schema ---


def test_loose_labels_are_mapped_onto_the_schema():
    fact = CapturedFact(
        content="User plans a trip",
        kind="Lesson",
        source="user",
        evidence="x",
        horizon="temporary",
        category="project",
    )
    assert (fact.kind, fact.source, fact.horizon, fact.category) == (
        "experience",
        "user_said",
        "dated",
        "context",
    )


# --- gate ---


def test_a_grounded_user_fact_is_kept():
    result = capture.gate([_fact()], BATCH)
    assert [f.content for f in result.kept] == ["User prefers tea over coffee"]
    assert result.dropped == [] and result.ungrounded == {}


def test_evidence_matches_despite_spacing_and_punctuation():
    fact = _fact(evidence="I always drink tea never coffee")
    assert capture.gate([fact], BATCH).kept == [fact]


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"source": "agent_said"}, "agent_said"),
        ({"kind": "experience", "source": "outcome"}, "experience_channel"),
        ({"horizon": "ephemeral"}, "ephemeral"),
        ({"source": "tool_output"}, "user_kind_wrong_source"),
        ({"evidence": "I used to live in Paris"}, "evidence_not_in_user_line"),
        ({"evidence": "The user is a night owl"}, "evidence_not_in_user_line"),
        (
            {
                "kind": "world",
                "source": "tool_output",
                "content": "User is a night owl",
            },
            "tool_output_without_citation",
        ),
        ({"kind": "world", "source": "outcome"}, "outcome_not_experience"),
        ({"content": "User chose option 1"}, "context_free_choice"),
        ({"content": "User picked the second one"}, "context_free_choice"),
    ],
)
def test_the_gate_drops_what_the_labels_rule_out(overrides, code):
    assert _dropped(capture.gate([_fact(**overrides)], BATCH)) == [code]


def test_a_cited_tool_fact_about_the_world_is_kept():
    fact = _fact(
        kind="world",
        source="tool_output",
        content="The persona file at persona.md describes the agent's voice",
        evidence="read_file(persona.md)",
        category="technical",
    )
    assert capture.gate([fact], BATCH).kept == [fact]


def test_rejected_and_known_claims_are_dropped():
    rejected = capture.gate([_fact()], BATCH, rejected=["prefers tea over coffee"])
    known = capture.gate([_fact()], BATCH, known=["User prefers tea over coffee."])

    assert _dropped(rejected) == ["rejected"]
    assert _dropped(known) == ["restatement"]


def test_the_cap_keeps_the_most_important():
    facts = [
        _fact(content=f"User prefers tea variant {i}", importance=i / 10)
        for i in range(7)
    ]
    result = capture.gate(facts, BATCH, cap=5)

    assert [f.importance for f in result.kept] == [0.6, 0.5, 0.4, 0.3, 0.2]
    assert _dropped(result) == ["over_cap", "over_cap"]


def test_details_the_evidence_does_not_hold_are_flagged_not_dropped():
    fact = _fact(content="User has preferred tea in Kyoto since 2019")
    result = capture.gate([fact], BATCH)

    assert result.kept == [fact]
    assert result.ungrounded[fact.content] == ["2019", "Kyoto"]


def test_a_turn_date_grounds_a_resolved_date():
    fact = _fact(content="User stopped drinking coffee on 2026-10-22")
    assert capture.gate([fact], BATCH).ungrounded == {}


def test_tags_record_kind_source_and_expiry():
    assert capture.fact_tags(_fact()) == ["kind:user", "source:user_said"]
    assert capture.fact_tags(_fact(horizon="dated"), "2027-01-20") == [
        "kind:user",
        "source:user_said",
        "dated",
        "stale_after:2027-01-20",
    ]


# --- scheduled turns never reach capture ---


class _Recorder:
    def __init__(self) -> None:
        self.batches: list[str] = []

    async def process_conversation_for_memories(
        self, conversation_text, chat_id, user_id, recall_query=None
    ):
        self.batches.append(conversation_text)

    async def process_experience(self, batch, chat_id, user_id):
        return []


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr("suzent.memory.lifecycle.get_memory_manager", lambda: rec)
    return rec


def _append(log: ChatEventLog, message: dict) -> None:
    path = log.path("c1")
    seq = len(path.read_text().splitlines()) + 1 if path.exists() else 1
    events = [] if seq > 1 else [("chat.created", {"config": {}, "messages": []})]
    events.append(("message.append", message))
    with path.open("a", encoding="utf-8") as f:
        for offset, (kind, data) in enumerate(events):
            event = {"v": 1, "seq": seq + offset, "ts": "2026-10-25T09:00:00+00:00"}
            f.write(json.dumps({**event, "type": kind, "data": data}) + "\n")


def _turn(log: ChatEventLog, user: str, reply: str = "ok") -> None:
    _append(log, {"role": "user", "content": user})
    _append(log, {"role": "assistant", "content": reply})


def _scheduled(log: ChatEventLog, prompt: str, reply: str = "ok") -> None:
    _append(log, {"role": "system_triggered", "content": prompt})
    _append(log, {"role": "assistant", "content": reply})


@pytest.fixture
def log(tmp_path, monkeypatch) -> ChatEventLog:
    monkeypatch.setattr("suzent.config.DATA_DIR", tmp_path / "data")
    return ChatEventLog(tmp_path)


async def test_a_scheduled_only_batch_is_skipped_but_consumed(log, recorder):
    queue = ExtractionQueue(log)
    await queue.catch_up("u1")
    _scheduled(log, "**Scheduled Task: morning news**\nSend the news at 9")

    await queue.flush("c1", "u1")

    assert recorder.batches == []
    cursors = json.loads((log.root / CURSORS_FILE).read_text())
    assert cursors["c1"][0] == 3


async def test_scheduled_turns_are_left_out_of_a_mixed_batch(log, recorder):
    queue = ExtractionQueue(log)
    await queue.catch_up("u1")
    _scheduled(log, "**Scheduled Task: morning news**\nSend the news at 9")
    _turn(log, "I moved to Lisbon")

    await queue.flush("c1", "u1")

    assert len(recorder.batches) == 1
    assert "Lisbon" in recorder.batches[0]
    assert "Scheduled Task" not in recorder.batches[0]


# --- manager ---


@pytest.fixture
def store(tmp_path):
    return MarkdownMemoryStore(
        base_dir=tmp_path, notebook_dir=str(tmp_path / "notebook")
    )


class _Client:
    def __init__(self, captured: list[CapturedFact]) -> None:
        self.captured = captured

    async def extract_with_schema(self, *, prompt, response_model, system, temperature):
        assert response_model is CaptureResponse
        return CaptureResponse(facts=self.captured)


class _Indexer:
    def __init__(self) -> None:
        self.files: list[str] = []

    async def reindex_file_now(self, *, filename, **kwargs):
        self.files.append(filename)


class _Rows:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete_memory(self, memory_id):
        self.deleted.append(memory_id)


def _manager(store, monkeypatch, *, captured=(), rows=()):
    from suzent.memory.manager import MemoryManager

    mgr = MemoryManager.__new__(MemoryManager)
    mgr.markdown_store = store
    mgr.llm_client = _Client(list(captured))
    mgr.llm_extraction_model = "stub"
    mgr.store = _Rows()
    mgr.embedding_gen = None
    mgr._core_indexer = _Indexer()

    async def search_memories(**kwargs):
        return list(rows)

    mgr.search_memories = search_memories
    return mgr


def _log(store) -> str:
    return "".join(
        p.read_text(encoding="utf-8") for p in sorted(store.archive_dir.glob("*.md"))
    )


async def test_gate_drops_are_logged_for_review(store, monkeypatch):
    mgr = _manager(store, monkeypatch, captured=[_fact(), _fact(source="agent_said")])

    result = await mgr.process_conversation_for_memories(BATCH, "chat-1", "u1")

    assert result.extracted_facts == ["User prefers tea over coffee"]
    record = json.loads(store.capture_dropped_path.read_text(encoding="utf-8"))
    assert (record["channel"], record["chat_id"]) == ("facts", "chat-1")
    assert [d["code"] for d in record["dropped"]] == ["agent_said"]


async def test_typed_mode_writes_evidence_and_tags(store, monkeypatch):
    mgr = _manager(store, monkeypatch, captured=[_fact(horizon="dated")])

    result = await mgr.process_conversation_for_memories(BATCH, "chat-1", "u1")

    assert result.extracted_facts == ["User prefers tea over coffee"]
    log = _log(store)
    assert "kind:user source:user_said dated stale_after:" in log
    assert '> "I always drink tea, never coffee"' in log
    assert not store.capture_dropped_path.exists()
    assert mgr._core_indexer.files


async def test_retracting_a_wrong_memory_rejects_and_hides_it(store, monkeypatch):
    rows = [
        {"id": "r1", "content": "User wrote The Perfect Drone", "metadata": {}},
        {
            "id": "r2",
            "content": "User wrote The Perfect Drone in 2024",
            "metadata": {
                "source_type": "archive_log",
                "source_file": "archive/2026-10-01.md",
            },
        },
        {"id": "r3", "content": "User likes tea", "metadata": {}},
    ]
    mgr = _manager(store, monkeypatch, rows=rows)

    result = await mgr.apply_memory_update(
        user_id="u1", chat_id="c1", retract="User wrote The Perfect Drone"
    )

    assert result == {
        "retracted": [
            "User wrote The Perfect Drone",
            "User wrote The Perfect Drone in 2024",
        ],
        "written": None,
    }
    assert store.read_rejected() == ["User wrote The Perfect Drone"]
    assert store.is_tombstoned("User wrote The Perfect Drone in 2024")
    assert mgr.store.deleted == ["r1"]
    assert mgr._core_indexer.files == ["2026-10-01.md"]


async def test_retracting_leaves_page_chunks_to_the_dream(store, monkeypatch):
    chunk = "User wrote The Perfect Drone. User keeps bees. User likes tea."
    rows = [
        {"id": "p1", "content": chunk, "metadata": {"source_type": "notebook"}},
        {"id": "c1", "content": chunk, "metadata": {"source_type": "core_file"}},
    ]
    mgr = _manager(store, monkeypatch, rows=rows)

    result = await mgr.apply_memory_update(
        user_id="u1", chat_id="c1", retract="User wrote The Perfect Drone"
    )

    assert result["retracted"] == []
    assert not store.is_tombstoned(chunk)
    assert mgr.store.deleted == []
    assert store.read_rejected() == ["User wrote The Perfect Drone"]


async def test_a_correction_hides_the_old_claim_and_writes_the_new(store, monkeypatch):
    rows = [{"id": "r1", "content": "User lives in Paris", "metadata": {}}]
    mgr = _manager(store, monkeypatch, rows=rows)

    result = await mgr.apply_memory_update(
        user_id="u1",
        chat_id="c1",
        fact="User lives in Lisbon",
        retract="User lives in Paris",
        retract_as="outdated",
        evidence="I moved to Lisbon last month",
    )

    assert result["written"] == "User lives in Lisbon"
    assert store.read_rejected() == []
    assert store.is_tombstoned("User lives in Paris")
    log = _log(store)
    assert "User lives in Lisbon `kind:user source:user_said explicit revision`" in log
    assert '> "I moved to Lisbon last month"' in log


# --- tool ---


async def test_the_tool_needs_something_to_do():
    from suzent.tools.base import ToolErrorCode
    from suzent.tools.recall.memory_tools import MemoryUpdateTool

    ctx = SimpleNamespace(deps=SimpleNamespace(memory_manager=None), prompt="hi")
    result = await MemoryUpdateTool().forward(ctx, fact=" ", retract=None)

    assert not result.success
    assert result.error_code == ToolErrorCode.INVALID_ARGUMENT


async def test_the_tool_quotes_the_users_message_as_evidence(store, monkeypatch):
    from suzent.tools.recall.memory_tools import EVIDENCE_CHARS, MemoryUpdateTool

    mgr = _manager(store, monkeypatch)
    prompt = "<system-reminder>clock</system-reminder>Remember I like tea " + "x" * 400
    ctx = SimpleNamespace(
        deps=SimpleNamespace(memory_manager=mgr, user_id="u1", chat_id="c1"),
        prompt=prompt,
    )

    result = await MemoryUpdateTool().forward(ctx, fact="User likes tea")

    assert result.success
    quote = _log(store).split('> "', 1)[1]
    assert quote.startswith("Remember I like tea")
    assert len(quote.split('"', 1)[0]) == EVIDENCE_CHARS


@pytest.mark.parametrize(
    ("kind", "missing"), [("experience", "outcome"), ("world", "source")]
)
async def test_agent_learned_facts_need_their_grounding(kind, missing):
    from suzent.tools.base import ToolErrorCode
    from suzent.tools.recall.memory_tools import MemoryUpdateTool

    ctx = SimpleNamespace(deps=SimpleNamespace(memory_manager=None), prompt="hi")
    result = await MemoryUpdateTool().forward(ctx, fact="Something", kind=kind)

    assert not result.success
    assert result.error_code == ToolErrorCode.INVALID_ARGUMENT
    assert missing in result.message


@pytest.mark.parametrize(
    ("kwargs", "tags", "evidence"),
    [
        (
            {"kind": "experience", "outcome": "the user accepted it"},
            "kind:experience source:outcome",
            '> "outcome: the user accepted it"',
        ),
        (
            {"kind": "world", "source": "docs/sync.md"},
            "kind:world source:tool_output",
            '> "source: docs/sync.md"',
        ),
    ],
)
async def test_agent_learned_facts_are_tagged_with_their_grounding(
    store, monkeypatch, kwargs, tags, evidence
):
    from suzent.tools.recall.memory_tools import MemoryUpdateTool

    mgr = _manager(store, monkeypatch)
    ctx = SimpleNamespace(
        deps=SimpleNamespace(memory_manager=mgr, user_id="u1", chat_id="c1"),
        prompt="unrelated",
    )

    result = await MemoryUpdateTool().forward(ctx, fact="A lesson", **kwargs)

    assert result.success
    log = _log(store)
    assert tags in log
    assert "explicit" not in log
    assert evidence in log
