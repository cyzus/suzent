"""Indexed rows must carry a category worth filtering on.

`category` used to be set to the source label ("notebook" / "core_file") and `tags`
to `[source label, filename]`. That made the two commonest tags in the whole corpus
carry no information at all — every notebook row was tagged `notebook` — while the
category slot, the one field a reader would filter by, duplicated `source_type`.
"""

from suzent.memory.indexer import CoreMemoryFileIndexer as Indexer


def test_declared_type_wins():
    category, _ = Indexer._page_taxonomy(
        "notebook", "2_Wiki/Attention.md", "---\ntype: concept\n---\nbody"
    )
    assert category == "concept"


def test_zone_is_the_fallback():
    """Most pages have no `type:`; the folder they live in is what is left."""
    category, _ = Indexer._page_taxonomy("notebook", "3_Personal/Journal/x.md", "body")
    assert category == "personal"


def test_windows_separators_resolve_to_the_same_zone():
    category, _ = Indexer._page_taxonomy("notebook", "1_Projects\\suzent.md", "body")
    assert category == "project"


def test_unrecognised_declared_type_falls_back_to_the_zone():
    category, _ = Indexer._page_taxonomy(
        "notebook", "0_Inbox/x.md", "---\ntype: whatever\n---"
    )
    assert category == "inbox"


def test_tags_come_from_frontmatter_only():
    _, tags = Indexer._page_taxonomy(
        "notebook", "2_Wiki/Attention.md", "---\ntags: [ai, #Agents]\n---"
    )
    assert tags == ["ai", "agents"]


def test_no_source_label_or_filename_in_tags():
    _, tags = Indexer._page_taxonomy("notebook", "2_Wiki/Attention.md", "body")
    assert tags == []


def test_core_files_are_profile():
    assert Indexer._page_taxonomy("facts", "MEMORY.md", "x") == ("profile", [])
