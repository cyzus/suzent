"""Truncation keeps the tail on disk instead of discarding it.

A cap stops one output swallowing the context window, but the part it removes
is usually the part someone wanted — the failing assertion at the end of a test
run, the last of a build log. Truncating to a bare marker tells the model that
content is missing and gives it no way to read it.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from suzent.tools.base import truncate_tool_output
from suzent.tools.overflow import (
    OVERFLOW_MAX_FILES,
    OVERFLOW_VIRTUAL_DIR,
    spill_overflow,
)


@pytest.fixture
def deps(tmp_path):
    class _Resolver:
        def resolve(self, virtual: str) -> str:
            assert virtual == OVERFLOW_VIRTUAL_DIR
            return str(tmp_path / "overflow")

    return SimpleNamespace(path_resolver=_Resolver(), sandbox_enabled=False)


def test_the_whole_output_is_written_not_the_kept_part(deps):
    text = "\n".join(f"line {i}" for i in range(5000))

    path = spill_overflow(text, deps=deps, kind="run_command")

    assert Path(path).read_text(encoding="utf-8") == text


def test_the_marker_names_the_file(deps):
    text = "x" * 50_000

    path = spill_overflow(text, deps=deps, kind="run_command")
    out = truncate_tool_output(text, 100, full_output_path=path)

    assert path in out
    assert "full output" in out
    assert len(out) < 500


def test_a_marker_without_a_spill_still_reports_the_loss(deps):
    """Spilling is best-effort. Losing the tail beats failing the tool call
    that produced it, but the model still has to know it happened."""
    out = truncate_tool_output("x" * 50_000, 100, full_output_path=None)

    assert "truncated" in out
    assert "full output" not in out


def test_the_path_is_the_one_this_agent_can_open(tmp_path):
    """Host mode gets a host path, sandbox mode the virtual one. A path the
    agent cannot open is worse than none: it invites a read that fails."""

    class _Resolver:
        def resolve(self, virtual: str) -> str:
            return str(tmp_path / "overflow")

    host = SimpleNamespace(path_resolver=_Resolver(), sandbox_enabled=False)
    sandboxed = SimpleNamespace(path_resolver=_Resolver(), sandbox_enabled=True)

    assert spill_overflow("y" * 100, deps=host, kind="t").startswith(str(tmp_path))
    assert spill_overflow("y" * 100, deps=sandboxed, kind="t").startswith(
        OVERFLOW_VIRTUAL_DIR
    )


def test_no_resolver_means_no_spill_rather_than_a_crash():
    assert spill_overflow("x" * 100, deps=SimpleNamespace(), kind="t") is None


def test_an_unwritable_directory_degrades_quietly(tmp_path):
    class _Broken:
        def resolve(self, virtual: str) -> str:
            raise ValueError("no matching custom mount is registered")

    deps = SimpleNamespace(path_resolver=_Broken(), sandbox_enabled=False)

    assert spill_overflow("x" * 100, deps=deps, kind="t") is None


def test_spills_do_not_accumulate_without_limit(deps):
    """A single runaway session can write thousands; the TTL alone would not
    bound that until tomorrow."""
    for i in range(OVERFLOW_MAX_FILES + 25):
        spill_overflow(f"body {i}", deps=deps, kind="t")

    directory = Path(deps.path_resolver.resolve(OVERFLOW_VIRTUAL_DIR))
    assert len(list(directory.glob("*.txt"))) <= OVERFLOW_MAX_FILES


def test_an_expired_spill_is_removed(deps):
    import os
    import time

    from suzent.tools.overflow import OVERFLOW_TTL_SECONDS

    stale = spill_overflow("old", deps=deps, kind="t")
    old_time = time.time() - OVERFLOW_TTL_SECONDS - 60
    os.utime(stale, (old_time, old_time))

    spill_overflow("new", deps=deps, kind="t")

    assert not Path(stale).exists()
