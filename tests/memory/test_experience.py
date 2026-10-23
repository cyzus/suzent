"""Experience capture keeps a lesson only when the batch shows it failing and then
working, runs on scheduled turns too, and turns a repeat into a confirmation."""

import json

import pytest

from suzent.memory import experience
from suzent.memory.experience import Lesson, LessonResponse
from suzent.memory.extraction_queue import ExtractionQueue
from suzent.memory.markdown_store import MarkdownMemoryStore
from suzent.session.transcript import TranscriptManager

BATCH = """## Earlier context (already processed; do not extract)

### Turn on 2026-10-21
ACTION: run(pytest) -> error: database is locked

## New turns

### Turn on 2026-10-22
USER: regenerate the slides
ACTION: run(python scripts/gen.py) -> UnicodeDecodeError: 'gbk' codec can't decode byte 0xe2
ACTION: run(python -X utf8 scripts/gen.py) -> wrote slides.html
ASSISTANT: Done. The default GBK locale broke the read; running with -X utf8 worked."""


def _lesson(**overrides) -> Lesson:
    values = {
        "situation": "running repo scripts on Windows",
        "attempt": "plain python",
        "outcome": "python -X utf8 worked",
        "lesson": "Run Python scripts with python -X utf8 on this Windows machine",
        "scope": "Windows shell",
        "evidence_fail": "UnicodeDecodeError: 'gbk' codec can't decode byte 0xe2",
        "evidence_fix": "run(python -X utf8 scripts/gen.py) -> wrote slides.html",
        "importance": 0.7,
    }
    values.update(overrides)
    return Lesson(**values)


def _dropped(result: experience.LessonGateResult) -> list[str]:
    return [code for code, _ in result.dropped]


# --- signal ---


@pytest.mark.parametrize(
    "new",
    [
        "ACTION: run(npm test) -> exit code 1",
        "ASSISTANT: 根因是坐标系手性相反",
        "USER: 不对，改回中性灰吧",
        "USER: that's not what I asked for",
    ],
)
def test_a_failure_or_a_correction_is_a_signal(new):
    assert experience.has_signal(f"## New turns\n\n### Turn\n{new}")


def test_a_quiet_batch_and_old_failures_are_not():
    assert not experience.has_signal(
        BATCH.split("## New turns")[0] + "## New turns\n\nUSER: hi\nASSISTANT: hello"
    )
    assert not experience.has_signal(
        "## New turns\n\n### Turn\nUSER: the error page looks fine\nASSISTANT: ok"
    )


# --- gate ---


def test_a_lesson_with_failure_and_fix_is_kept_with_its_scope():
    result = experience.gate([_lesson()], BATCH)

    assert result.kept == [_lesson()]
    assert result.kept[0].scope_tag == "scope:windows-shell"
    assert result.kept[0].content.startswith("Run Python scripts with python -X utf8")


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"evidence_fix": "the second run passed cleanly"}, "no_outcome"),
        ({"evidence_fail": "error: database is locked"}, "no_outcome"),
        (
            {"evidence_fix": "UnicodeDecodeError: 'gbk' codec can't decode byte 0xe2"},
            "no_outcome",
        ),
        ({"scope": "general"}, "no_scope"),
    ],
    ids=["fix-not-shown", "failure-from-context", "same-words-twice", "no-scope"],
)
def test_the_gate_drops_lessons_the_batch_does_not_show(overrides, code):
    assert _dropped(experience.gate([_lesson(**overrides)], BATCH)) == [code]


def test_evidence_may_skip_lines_of_one_message_and_drop_markdown():
    batch = (
        "## New turns\n\n### Turn\n"
        "ACTION: run(check) -> === check with UTF-8 mode ===\nok: 12 files\nexit=0\n"
        "ASSISTANT: Fixed.\n\n## Causes\n1. **GBK locale**: the plain run failed on an em-dash."
    )
    lesson = _lesson(
        evidence_fail="1. GBK locale: the plain run failed on an em-dash.",
        evidence_fix="=== check with UTF-8 mode ===\nexit=0",
    )

    assert experience.gate([lesson], batch).kept == [lesson]


def test_evidence_joined_from_two_messages_is_not_shown():
    lesson = _lesson(
        evidence_fail="UnicodeDecodeError: 'gbk' codec\nDone. The default GBK locale"
    )
    assert _dropped(experience.gate([lesson], BATCH)) == ["no_outcome"]


def test_a_known_lesson_is_a_repeat_not_a_drop():
    known = ["Run Python scripts with python -X utf8 on this Windows machine (GBK)."]

    result = experience.gate([_lesson()], BATCH, known=known)

    assert result.kept == [] and result.dropped == []
    assert result.repeated == [(_lesson(), known[0])]


def test_a_rejected_lesson_is_dropped():
    result = experience.gate([_lesson()], BATCH, rejected=["python -X utf8"])
    assert _dropped(result) == ["rejected"]


# --- queue ---


class _Recorder:
    def __init__(self) -> None:
        self.facts: list[str] = []
        self.lessons: list[str] = []

    async def process_conversation_for_memories(
        self, conversation_text, chat_id, user_id, recall_query=None
    ):
        self.facts.append(conversation_text)

    async def process_experience(self, batch, chat_id, user_id):
        self.lessons.append(batch)
        return []


async def test_scheduled_turns_reach_experience_capture_only(tmp_path, monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr("suzent.memory.lifecycle.get_memory_manager", lambda: recorder)
    queue = ExtractionQueue(tmp_path)
    await queue.catch_up("u1")
    transcript = TranscriptManager(str(tmp_path))
    await transcript.append_turn("c1", "user", "**Scheduled Task: release**\nShip it")
    await transcript.append_turn("c1", "assistant", "Push failed: denied")

    await queue.flush("c1", "u1")

    assert recorder.facts == []
    assert len(recorder.lessons) == 1 and "Push failed" in recorder.lessons[0]


# --- manager ---


class _Client:
    def __init__(self, lessons: list[Lesson]) -> None:
        self.lessons = lessons
        self.calls = 0

    async def extract_with_schema(self, *, prompt, response_model, system, temperature):
        self.calls += 1
        assert response_model is LessonResponse
        return LessonResponse(lessons=self.lessons)


class _Indexer:
    async def reindex_file_now(self, **kwargs):
        pass


def _manager(tmp_path, monkeypatch, *, lessons=(), rows=()):
    from suzent.memory.manager import MemoryManager

    mgr = MemoryManager.__new__(MemoryManager)
    mgr.markdown_store = MarkdownMemoryStore(
        base_dir=tmp_path, notebook_dir=str(tmp_path / "notebook")
    )
    mgr.llm_client = _Client(list(lessons))
    mgr._core_indexer = _Indexer()
    mgr.store = None
    mgr.embedding_gen = None

    async def search_memories(**kwargs):
        return list(rows)

    mgr.search_memories = search_memories
    return mgr


def _log(mgr) -> str:
    return "".join(
        p.read_text(encoding="utf-8")
        for p in sorted(mgr.markdown_store.archive_dir.glob("*.md"))
    )


async def test_a_kept_lesson_is_written_with_its_tags(tmp_path, monkeypatch):
    mgr = _manager(tmp_path, monkeypatch, lessons=[_lesson()])

    written = await mgr.process_experience(BATCH, "c1", "u1")

    assert written == [_lesson().content]
    log = _log(mgr)
    assert "kind:experience source:outcome scope:windows-shell" in log
    assert "UnicodeDecodeError" in log and "wrote slides.html" in log


async def test_a_repeat_is_recorded_as_a_confirmation(tmp_path, monkeypatch):
    rows = [
        {
            "content": "Run Python scripts with python -X utf8 on this Windows machine",
            "metadata": {"source_type": "notebook_page"},
        }
    ]
    mgr = _manager(tmp_path, monkeypatch, lessons=[_lesson()], rows=rows)
    monkeypatch.setattr(
        "suzent.memory.manager.DURABLE_SOURCE_TYPES", frozenset({"notebook_page"})
    )

    assert await mgr.process_experience(BATCH, "c1", "u1") == []
    assert _log(mgr) == ""
    [confirmation] = mgr.markdown_store.read_confirmations()
    assert confirmation["matched"] == rows[0]["content"]


async def test_a_dropped_lesson_is_logged_not_written(tmp_path, monkeypatch):
    mgr = _manager(tmp_path, monkeypatch, lessons=[_lesson(scope="general")])

    assert await mgr.process_experience(BATCH, "c1", "u1") == []
    assert _log(mgr) == ""
    record = json.loads(
        mgr.markdown_store.capture_dropped_path.read_text(encoding="utf-8")
    )
    assert record["channel"] == "experience"
    assert [d["code"] for d in record["dropped"]] == ["no_scope"]


async def test_a_batch_without_a_signal_costs_no_model_call(tmp_path, monkeypatch):
    mgr = _manager(tmp_path, monkeypatch, lessons=[_lesson()])

    await mgr.process_experience(
        "## New turns\n\nUSER: hi\nASSISTANT: hello", "c1", "u1"
    )

    assert mgr.llm_client.calls == 0


async def test_a_model_failure_never_raises(tmp_path, monkeypatch):
    mgr = _manager(tmp_path, monkeypatch)

    async def boom(**kwargs):
        raise RuntimeError("model down")

    mgr.llm_client.extract_with_schema = boom

    assert await mgr.process_experience(BATCH, "c1", "u1") == []
