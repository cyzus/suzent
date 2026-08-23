"""Indexer state must be keyed portably, not by absolute path.

The vault's `.state` travels between machines and survives a moved base dir. When
state was keyed by absolute path, entries from other machines accumulated in the
file, and any tracked file whose stale recorded mtime happened to match was skipped
forever — which is how daily logs went missing from the search index.
"""

import json

import pytest

from suzent.memory.indexer import CoreMemoryFileIndexer
from suzent.memory.markdown_store import MarkdownMemoryStore


@pytest.fixture
def store(tmp_path):
    return MarkdownMemoryStore(
        base_dir=tmp_path / "memory", notebook_dir=tmp_path / "notebook"
    )


def _state_file(store):
    return store.base_dir / CoreMemoryFileIndexer.INDEX_STATE_FILENAME


def test_keys_are_label_and_filename_not_paths(store):
    (store.archive_dir / "2026-03-12.md").write_text("- [goal] x\n", encoding="utf-8")
    indexer = CoreMemoryFileIndexer()

    indexer._load_state(store)

    assert "archive:2026-03-12.md" in indexer._mtimes
    assert not any("/" in k or "\\" in k for k in indexer._mtimes)


def test_saved_state_is_versioned(store):
    indexer = CoreMemoryFileIndexer()
    indexer._load_state(store)
    indexer._save_state()

    payload = json.loads(_state_file(store).read_text(encoding="utf-8"))

    assert payload["version"] == CoreMemoryFileIndexer.STATE_VERSION
    assert isinstance(payload["mtimes"], dict)


def test_path_keyed_state_is_discarded(store):
    """A pre-v2 file must not be trusted; discarding it forces one full reindex."""
    _state_file(store).write_text(
        json.dumps(
            {
                "/Users/someone/.suzent/sandbox/shared/memory/archive/2026-05-03.md": 1.0,
                "D:\\elsewhere\\memory\\archive\\2026-05-04.md": 2.0,
            }
        ),
        encoding="utf-8",
    )
    indexer = CoreMemoryFileIndexer()

    indexer._load_state(store)

    assert indexer._mtimes == {}


def test_versioned_state_round_trips(store):
    _state_file(store).write_text(
        json.dumps(
            {
                "version": CoreMemoryFileIndexer.STATE_VERSION,
                "mtimes": {"archive:2026-05-03.md": 123.0},
            }
        ),
        encoding="utf-8",
    )
    indexer = CoreMemoryFileIndexer()

    indexer._load_state(store)

    assert indexer._mtimes == {"archive:2026-05-03.md": 123.0}


def test_corrupt_state_degrades_to_empty(store):
    _state_file(store).write_text("{not json", encoding="utf-8")
    indexer = CoreMemoryFileIndexer()

    indexer._load_state(store)

    assert indexer._mtimes == {}
