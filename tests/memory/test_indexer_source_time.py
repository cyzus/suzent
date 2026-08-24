"""An indexed row must date from its content, not from the indexing run.

`add_memory` stamped `created_at` with the write time, so every reindex re-dated
the whole corpus to today. That is wrong three times over: the list groups by day,
the "new" badge fires on everything, and `calculate_final_score` multiplies in a
recency term — a reindexed vault would out-rank genuinely recent memories in every
search purely for having been re-embedded.
"""

from datetime import datetime, timezone

from suzent.memory.indexer import CoreMemoryFileIndexer as Indexer


def test_a_daily_log_dates_from_its_own_filename():
    """The log's date is not a guess — it is the name of the file."""
    assert Indexer._source_time("archive", "2026-05-03.md", "- [goal] x") == datetime(
        2026, 5, 3, tzinfo=timezone.utc
    )


def test_frontmatter_updated_wins_over_mtime():
    """mtime moves when OneDrive syncs the vault; `updated:` is what the author said."""
    mtime = datetime(2026, 8, 24, tzinfo=timezone.utc).timestamp()
    got = Indexer._source_time(
        "notebook", "2_Wiki/Attention.md", "---\nupdated: 2026-04-12\n---\nbody", mtime
    )
    assert got == datetime(2026, 4, 12, tzinfo=timezone.utc)


def test_created_and_date_are_accepted_too():
    for key in ("created", "date"):
        got = Indexer._source_time(
            "notebook", "x.md", f"---\n{key}: 2026-01-09\n---\nbody"
        )
        assert got == datetime(2026, 1, 9, tzinfo=timezone.utc)


def test_mtime_is_the_fallback():
    """144 of the 309 vault pages carry no date at all; the file still has one."""
    mtime = datetime(2025, 10, 29, 15, 27, tzinfo=timezone.utc).timestamp()
    got = Indexer._source_time("notebook", "x.md", "no frontmatter", mtime)
    assert got == datetime(2025, 10, 29, 15, 27, tzinfo=timezone.utc)


def test_no_signal_returns_none_rather_than_a_wrong_date():
    """None leaves `add_memory` on its write-time default, which is at least honest."""
    assert Indexer._source_time("notebook", "x.md", "body") is None


def test_a_malformed_date_does_not_become_the_timestamp():
    mtime = datetime(2026, 8, 24, tzinfo=timezone.utc).timestamp()
    got = Indexer._source_time(
        "notebook", "x.md", "---\nupdated: last tuesday\n---\nbody", mtime
    )
    assert got == datetime(2026, 8, 24, tzinfo=timezone.utc)


def test_an_undated_log_filename_falls_through_to_mtime():
    mtime = datetime(2026, 2, 2, tzinfo=timezone.utc).timestamp()
    assert Indexer._source_time("archive", "notes.md", "- [goal] x", mtime) == datetime(
        2026, 2, 2, tzinfo=timezone.utc
    )
