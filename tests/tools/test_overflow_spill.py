"""Truncation keeps the tail on disk instead of discarding it.

A cap stops one output swallowing the context window, but the part it removes
is usually the part someone wanted — the failing assertion at the end of a test
run, the last of a build log. Truncating to a bare marker tells the model that
content is missing and gives it no way to read it.

Two properties are load-bearing: the write must not become a way to reach files
the agent could not otherwise touch, and a spill must not be readable by other
chats sharing the same mount.
"""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from suzent.tools.base import truncate_tool_output
from suzent.tools.overflow import (
    OVERFLOW_MAX_FILES,
    Spill,
    spill_overflow,
)


def _deps(tmp_path: Path, *, chat_id: str = "chat-1", sandbox: bool = False):
    class _Resolver:
        def resolve(self, virtual: str) -> str:
            assert virtual == "/shared"
            return str(tmp_path / "shared")

    return SimpleNamespace(
        path_resolver=_Resolver(), sandbox_enabled=sandbox, chat_id=chat_id
    )


@pytest.fixture
def deps(tmp_path):
    return _deps(tmp_path)


def _chat_dir(tmp_path: Path, chat_id: str = "chat-1") -> Path:
    return tmp_path / "shared" / ".overflow" / chat_id


def test_the_whole_output_is_written_not_the_kept_part(deps):
    text = "\n".join(f"line {i}" for i in range(5000))

    spill = spill_overflow(text, deps=deps, kind="run_command")

    assert Path(spill.path).read_text(encoding="utf-8") == text
    assert spill.clipped is False


def test_the_marker_names_the_file(deps):
    text = "x" * 50_000

    spill = spill_overflow(text, deps=deps, kind="run_command")
    out = truncate_tool_output(text, 100, spill=spill)

    assert spill.path in out
    assert "full output" in out
    assert "kept up to 24h" in out


def test_a_marker_without_a_spill_still_reports_the_loss():
    """Spilling is best-effort. Losing the tail beats failing the tool call that
    produced it, but the model still has to know it happened."""
    out = truncate_tool_output("x" * 50_000, 100, spill=None)

    assert "truncated" in out
    assert "full output" not in out


def test_host_mode_gets_a_host_path(tmp_path):
    """A path the agent cannot open is worse than none: it invites a read that
    fails."""
    host = spill_overflow("y" * 100, deps=_deps(tmp_path), kind="t")

    assert host.path.startswith(str(tmp_path))


def test_sandbox_mode_gets_the_virtual_path(tmp_path):
    from suzent.tools.overflow import OVERFLOW_VIRTUAL_DIR

    spill = spill_overflow("y" * 100, deps=_deps(tmp_path, sandbox=True), kind="t")

    assert spill.path.startswith(f"{OVERFLOW_VIRTUAL_DIR}/chat-1/")


def test_the_spill_is_readable_by_a_different_uid(deps, tmp_path):
    """Bind mounts preserve numeric ownership and the sandbox image runs as a
    fixed uid 1000, which need not match the host service's. A 0600 file would
    be unreadable by the very agent the marker points at — a path that exists
    and cannot be opened, which is the failure the spill exists to avoid."""
    spill = spill_overflow("x" * 100, deps=deps, kind="t")

    file_mode = os.stat(spill.path).st_mode & 0o777
    dir_mode = os.stat(_chat_dir(tmp_path)).st_mode & 0o777

    assert file_mode & 0o044, f"others cannot read the spill ({oct(file_mode)})"
    assert dir_mode & 0o011, f"others cannot traverse the directory ({oct(dir_mode)})"


def test_chat_directories_are_organisation_not_access_control(tmp_path):
    """Recorded so the naming is not mistaken for a boundary: on one shared
    mount with one uid, these directories separate pruning scope and nothing
    else. The owner has accepted that their chats can read each other."""
    a = spill_overflow("alpha", deps=_deps(tmp_path, chat_id="a"), kind="t")

    # Any other chat, running as the same uid, can read it.
    assert Path(a.path).read_text(encoding="utf-8") == "alpha"


def test_no_resolver_means_no_spill_rather_than_a_crash():
    assert spill_overflow("x" * 100, deps=SimpleNamespace(), kind="t") is None


def test_an_unreachable_shared_root_degrades_quietly(tmp_path):
    class _Broken:
        def resolve(self, virtual: str) -> str:
            raise ValueError("no matching custom mount is registered")

    deps = SimpleNamespace(path_resolver=_Broken(), sandbox_enabled=False, chat_id="c")

    assert spill_overflow("x" * 100, deps=deps, kind="t") is None


# --- one chat's output is not another chat's to read --------------------------


def test_spills_are_scoped_to_their_chat(tmp_path):
    """/shared is mounted into every session, so an unscoped directory is
    readable by every other chat on the deployment. These files hold raw tool
    output and reminder text — conversation content — and a random filename is
    no defence against listing the directory."""
    first = spill_overflow("secret alpha", deps=_deps(tmp_path, chat_id="a"), kind="t")
    second = spill_overflow("secret beta", deps=_deps(tmp_path, chat_id="b"), kind="t")

    assert "/a/" in first.path.replace(str(tmp_path), "")
    assert "/b/" in second.path.replace(str(tmp_path), "")
    assert list(_chat_dir(tmp_path, "a").glob("*.txt")) != []
    assert len(list(_chat_dir(tmp_path, "a").glob("*.txt"))) == 1


def test_a_hostile_chat_id_cannot_escape_the_directory(tmp_path):
    spill = spill_overflow(
        "x" * 100, deps=_deps(tmp_path, chat_id="../../etc"), kind="t"
    )

    assert ".." not in spill.path
    assert str(tmp_path / "shared" / ".overflow") in spill.path


# --- the write must not become a capability -----------------------------------


def test_a_symlink_at_the_destination_is_not_followed(deps, tmp_path, monkeypatch):
    """The name was once derived from the output's own hash and the current
    second, both of which the agent can compute."""
    import suzent.tools.overflow as overflow

    target = tmp_path / "precious.txt"
    target.write_text("do not clobber", encoding="utf-8")
    chat_dir = _chat_dir(tmp_path)
    chat_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(overflow.secrets, "token_hex", lambda n: "aimed")
    os.symlink(target, chat_dir / "run_command-aimed.txt")

    assert spill_overflow("payload" * 100, deps=deps, kind="run_command") is None
    assert target.read_text(encoding="utf-8") == "do not clobber"


def test_a_symlinked_parent_directory_is_not_followed(deps, tmp_path):
    """O_NOFOLLOW on the final component says nothing about the directories
    above it. Swap .overflow for a symlink after the path is resolved and an
    unpinned write lands in the attacker's tree — and the prune that follows
    unlinks *.txt there."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    bystander = elsewhere / "keepme.txt"
    bystander.write_text("unrelated", encoding="utf-8")

    shared = tmp_path / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    os.symlink(elsewhere, shared / ".overflow")

    result = spill_overflow("payload" * 100, deps=deps, kind="t")

    assert result is None, "the write followed a swapped parent directory"
    assert bystander.read_text(encoding="utf-8") == "unrelated"


def test_the_name_is_not_derivable_from_the_output(deps):
    text = "same output" * 50

    first = spill_overflow(text, deps=deps, kind="t")
    second = spill_overflow(text, deps=deps, kind="t")

    assert first.path != second.path


# --- disk bounds --------------------------------------------------------------


def test_one_spill_cannot_be_arbitrarily_large(deps):
    from suzent.tools.overflow import OVERFLOW_MAX_FILE_BYTES, SPILL_CLIPPED_NOTE

    spill = spill_overflow("x" * (OVERFLOW_MAX_FILE_BYTES * 2), deps=deps, kind="t")
    written = Path(spill.path).read_bytes()

    assert len(written) <= OVERFLOW_MAX_FILE_BYTES
    assert written.endswith(SPILL_CLIPPED_NOTE.encode("utf-8"))
    assert spill.clipped is True


def test_a_clipped_spill_is_still_valid_utf8(deps):
    """Slicing encoded bytes can land inside a multi-byte code point, and then
    the reader meant to rescue the output cannot open the file at all."""
    from suzent.tools.overflow import OVERFLOW_MAX_FILE_BYTES

    spill = spill_overflow("é" * OVERFLOW_MAX_FILE_BYTES, deps=deps, kind="t")

    Path(spill.path).read_text(encoding="utf-8")  # must not raise


def test_a_clipped_spill_is_not_advertised_as_the_full_output(deps):
    """Sending a reader to a file that does not hold what the marker promised is
    worse than admitting the cut twice."""
    from suzent.tools.overflow import OVERFLOW_MAX_FILE_BYTES

    text = "x" * (OVERFLOW_MAX_FILE_BYTES * 2)
    spill = spill_overflow(text, deps=deps, kind="t")
    out = truncate_tool_output(text, 100, spill=spill)

    assert "partial output" in out
    assert "full output" not in out


def test_spills_do_not_accumulate_without_limit(deps, tmp_path):
    for i in range(OVERFLOW_MAX_FILES + 25):
        spill_overflow(f"body {i}", deps=deps, kind="t")

    kept = list(_chat_dir(tmp_path).glob("*.txt"))

    assert len(kept) <= OVERFLOW_MAX_FILES


def test_the_directory_is_bounded_in_bytes_not_only_in_count(
    deps, tmp_path, monkeypatch
):
    import suzent.tools.overflow as overflow

    monkeypatch.setattr(overflow, "OVERFLOW_MAX_TOTAL_BYTES", 20_000)

    for _ in range(30):
        spill_overflow("y" * 2_000, deps=deps, kind="t")

    total = sum(p.stat().st_size for p in _chat_dir(tmp_path).glob("*.txt"))

    assert total <= 20_000 + 2_100, total


def test_an_expired_spill_is_removed(deps, tmp_path):
    import time

    from suzent.tools.overflow import OVERFLOW_TTL_SECONDS

    stale = spill_overflow("old", deps=deps, kind="t")
    old_time = time.time() - OVERFLOW_TTL_SECONDS - 60
    os.utime(stale.path, (old_time, old_time))

    spill_overflow("new", deps=deps, kind="t")

    assert not Path(stale.path).exists()


# --- lifecycle ----------------------------------------------------------------


def test_the_sweep_collects_what_no_later_spill_would(tmp_path, monkeypatch):
    """Pruning otherwise runs only on write, so the bounds hold exactly while
    output keeps overflowing and stop the moment it does not."""
    import time

    from suzent.config import CONFIG
    from suzent.tools.overflow import OVERFLOW_TTL_SECONDS, sweep_overflow

    chat_dir = _chat_dir(tmp_path)
    chat_dir.mkdir(parents=True)
    stale = chat_dir / "t-old.txt"
    stale.write_text("yesterday", encoding="utf-8")
    old = time.time() - OVERFLOW_TTL_SECONDS - 60
    os.utime(stale, (old, old))
    fresh = chat_dir / "t-new.txt"
    fresh.write_text("today", encoding="utf-8")

    monkeypatch.setattr(CONFIG, "sandbox_data_path", str(tmp_path), raising=False)
    sweep_overflow()

    assert not stale.exists()
    assert fresh.exists()


def test_the_sweep_drops_a_chat_directory_once_it_is_empty(tmp_path, monkeypatch):
    """Per-chat bounds mean the directory total scales with the number of
    chats, so the empty shells have to go too."""
    import time

    from suzent.config import CONFIG
    from suzent.tools.overflow import OVERFLOW_TTL_SECONDS, sweep_overflow

    chat_dir = _chat_dir(tmp_path, "gone")
    chat_dir.mkdir(parents=True)
    stale = chat_dir / "t-old.txt"
    stale.write_text("x", encoding="utf-8")
    old = time.time() - OVERFLOW_TTL_SECONDS - 60
    os.utime(stale, (old, old))

    monkeypatch.setattr(CONFIG, "sandbox_data_path", str(tmp_path), raising=False)
    sweep_overflow()

    assert not chat_dir.exists()


def test_the_sweep_is_harmless_with_no_directory(tmp_path, monkeypatch):
    from suzent.config import CONFIG
    from suzent.tools.overflow import sweep_overflow

    monkeypatch.setattr(CONFIG, "sandbox_data_path", str(tmp_path), raising=False)

    sweep_overflow()  # must not raise


def test_the_stated_window_tracks_the_actual_ttl(monkeypatch):
    import suzent.tools.overflow as overflow
    from suzent.tools.overflow import retention_hint

    monkeypatch.setattr(overflow, "OVERFLOW_TTL_SECONDS", 3 * 60 * 60)

    assert retention_hint() == "kept up to 3h"


@pytest.mark.asyncio
async def test_the_async_spill_does_not_hold_the_loop(deps, monkeypatch):
    """Up to 5 MiB of write plus a directory scan; inline, that stalls every
    other chat the loop is serving.

    A real spill is too quick to observe reliably, so the blocking part is
    replaced by a sleep — what is being tested is that the call is offloaded,
    not how fast the disk is.
    """
    import asyncio
    import time

    import suzent.tools.overflow as overflow
    from suzent.tools.overflow import spill_overflow_async

    monkeypatch.setattr(
        overflow,
        "spill_overflow",
        lambda text, **kw: time.sleep(0.2) or Spill("/tmp/x.txt", False),
    )

    ticks = 0

    async def _tick():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    ticker = asyncio.create_task(_tick())
    try:
        spill = await spill_overflow_async("payload", deps=deps, kind="t")
    finally:
        ticker.cancel()

    assert spill.path == "/tmp/x.txt"
    assert ticks > 5, f"the loop was blocked during the write ({ticks} ticks)"


def test_the_sweep_refuses_a_symlinked_chat_directory(tmp_path, monkeypatch):
    """The write path was pinned and the sweep was not; the attacker picks the
    weaker one. _prune_fd unlinks, so a symlink left under .overflow would let
    the next restart delete *.txt files in a directory of its choosing."""
    from suzent.config import CONFIG
    from suzent.tools.overflow import sweep_overflow

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    bystander = elsewhere / "keepme.txt"
    bystander.write_text("unrelated", encoding="utf-8")
    old = 1.0
    os.utime(bystander, (old, old))  # stale enough that a prune would take it

    root = tmp_path / "shared" / ".overflow"
    root.mkdir(parents=True)
    os.symlink(elsewhere, root / "pretend-chat")

    monkeypatch.setattr(CONFIG, "sandbox_data_path", str(tmp_path), raising=False)
    sweep_overflow()

    assert bystander.exists(), "the sweep followed a symlinked chat directory"


def test_the_retention_hint_is_an_upper_bound(deps):
    """The count and byte ceilings evict early — eleven maximum-sized results
    inside an hour drop the first long before the day is out."""
    from suzent.tools.overflow import retention_hint

    assert retention_hint().startswith("kept up to")


def test_the_whole_output_is_never_encoded(monkeypatch):
    """Encoding the full string to discover it is too long allocates a second
    copy while the original result is still live — a command printing hundreds
    of MiB costs that twice over to write five.

    A slice of a str subclass is a plain str, so if the recorder never fires the
    full string was never encoded — which is exactly the property.
    """
    import suzent.tools.overflow as overflow

    encoded_from: list[int] = []

    class _Watched(str):
        def encode(self, *args, **kwargs):
            encoded_from.append(len(self))
            return str.encode(self, *args, **kwargs)

    monkeypatch.setattr(overflow, "OVERFLOW_MAX_FILE_BYTES", 1_000)

    payload, clipped = overflow._clip(_Watched("x" * 500_000))

    assert clipped is True
    assert len(payload) <= 1_000
    assert encoded_from == [], f"the full {500_000}-char string was encoded"


def test_a_short_output_is_not_reported_as_clipped(monkeypatch):
    """The bounded slice must not make an ordinary result look truncated."""
    import suzent.tools.overflow as overflow

    monkeypatch.setattr(overflow, "OVERFLOW_MAX_FILE_BYTES", 1_000)

    payload, clipped = overflow._clip("short")

    assert clipped is False
    assert payload == b"short"


def test_the_root_total_is_bounded_across_chats(tmp_path, monkeypatch):
    """Pruning on write only ever sees one chat's directory, so the per-chat
    allowance multiplies by the number of chats — a hundred of them retain
    5 GiB while every directory is individually within bounds."""
    from suzent.config import CONFIG
    import suzent.tools.overflow as overflow
    from suzent.tools.overflow import sweep_overflow

    monkeypatch.setattr(overflow, "OVERFLOW_MAX_ROOT_BYTES", 5_000)

    for chat in ("a", "b", "c", "d"):
        spill_overflow("y" * 3_000, deps=_deps(tmp_path, chat_id=chat), kind="t")

    monkeypatch.setattr(CONFIG, "sandbox_data_path", str(tmp_path), raising=False)
    sweep_overflow()

    root = tmp_path / "shared" / ".overflow"
    total = sum(p.stat().st_size for p in root.rglob("*.txt"))

    assert total <= 5_000 + 3_100, total


def test_the_path_fallback_writes_without_dir_fd(tmp_path, monkeypatch):
    """Windows has no dir_fd, and keeping the fd-based code while passing
    dir_fd=None was not a fallback: os.open raises NotImplementedError there,
    which no `except OSError` catches, turning an oversized tool result into a
    failed tool call."""
    import suzent.tools.overflow as overflow

    monkeypatch.setattr(overflow, "_HAVE_DIR_FD", False)

    spill = overflow.spill_overflow("x" * 500, deps=_deps(tmp_path), kind="t")

    assert spill is not None
    assert Path(spill.path).read_text(encoding="utf-8") == "x" * 500
