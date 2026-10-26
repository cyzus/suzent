"""Kind and topics are read off metadata rows already have, typed or not."""

from suzent.memory.lancedb_store import matches_metadata
from suzent.memory.topics import describe, normalize_topics

LESSON = {
    "source_type": "archive_log",
    "category": "technical",
    "tags": ["kind:experience", "source:outcome", "scope:Windows-Shell"],
}


def test_a_typed_log_line_reports_its_kind_source_and_scope():
    assert describe(LESSON) == {
        "kind": "experience",
        "source": "outcome",
        "topics": ["windows-shell"],
    }


def test_an_early_log_line_is_untyped():
    meta = {"source_type": "archive_log", "category": "personal", "tags": ["berlin"]}
    assert describe(meta) == {"kind": "untyped", "topics": []}


def test_a_project_page_is_about_its_project_and_its_tags():
    meta = {
        "source_type": "notebook",
        "source_file": "1_Projects\\Suzent.md",
        "category": "project",
        "tags": ["agents", "suzent"],
    }
    assert describe(meta) == {"kind": "world", "topics": ["suzent", "agents"]}


def test_profile_and_personal_pages_are_about_the_user():
    assert describe({"source_type": "core_file", "category": "profile"})["kind"] == (
        "user"
    )
    assert describe({"source_type": "notebook", "category": "personal"})["kind"] == (
        "user"
    )


def test_topics_are_normalized_and_capped():
    assert normalize_topics(["Suzent repo", "suzent-repo", "a_b"] + list("cdefgh")) == [
        "suzent-repo",
        "a-b",
        "c",
        "d",
        "e",
        "f",
    ]


def test_kind_and_topic_filters_use_the_derived_fields():
    assert matches_metadata(LESSON, kinds=["experience"], topics=["windows-shell"])
    assert not matches_metadata(LESSON, kinds=["user"])
    assert not matches_metadata(LESSON, topics=["suzent"])
    assert matches_metadata({"source_type": "archive_log"}, kinds=["untyped"])


async def test_facets_count_kinds_and_topics_within_the_shelf_being_browsed():
    from suzent.memory.lancedb_store import LanceDBMemoryStore

    page = {"source_type": "notebook", "category": "project", "tags": ["suzent"]}
    rows = [{"metadata": LESSON}, {"metadata": LESSON}, {"metadata": page}]

    async def list_rows(*_args: object) -> list[dict]:
        return rows

    store = object.__new__(LanceDBMemoryStore)
    store._list_rows = list_rows

    facets = await store.get_memory_facets("user", source_types=["notebook"])

    assert facets["source_types"] == {"archive_log": 2, "notebook": 1}
    assert facets["kinds"] == {"world": 1}
    assert facets["topics"] == {"suzent": 1}
