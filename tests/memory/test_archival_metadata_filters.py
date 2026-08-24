"""Metadata filtering for the archival list.

`metadata` is a JSON string column, so source/category/tag filters cannot be pushed
into the SQL clause and have to run in Python over the materialised rows. These
tests pin the semantics the UI depends on: OR within a list, AND across lists, and
a missing `source_type` reported as "unknown" rather than dropped.
"""

from suzent.memory.lancedb_store import matches_metadata


def test_no_filters_matches_everything():
    assert matches_metadata({}, None, None, None)


def test_source_type_is_or_within_the_list():
    meta = {"source_type": "notebook"}
    assert matches_metadata(meta, ["archive_log", "notebook"], None, None)
    assert not matches_metadata(meta, ["archive_log"], None, None)


def test_a_missing_source_type_reads_as_unknown():
    """Pre-June rows have no `source_type`; the facet counts call them "unknown",
    so the filter must agree or the tab shows a count it cannot deliver."""
    assert matches_metadata({}, ["unknown"], None, None)
    assert not matches_metadata({}, ["notebook"], None, None)


def test_filters_are_and_across_kinds():
    meta = {"source_type": "notebook", "category": "concept", "tags": ["ai"]}
    assert matches_metadata(meta, ["notebook"], ["concept"], ["ai"])
    assert not matches_metadata(meta, ["notebook"], ["personal"], ["ai"])


def test_a_tag_filter_needs_only_one_overlap():
    meta = {"tags": ["ai", "agents"]}
    assert matches_metadata(meta, None, None, ["agents", "robotics"])
    assert not matches_metadata(meta, None, None, ["robotics"])


def test_malformed_tags_do_not_crash_the_list():
    assert not matches_metadata({"tags": "ai"}, None, None, ["ai"])
