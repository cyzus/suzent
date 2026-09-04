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
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from suzent.tools.base import truncate_tool_output
from suzent.tools.overflow import (
    OVERFLOW_MAX_FILES,
    Spill,
    spill_overflow,
)


def _deps(tmp_path: Path, *, chat_id: str = "chat-1", sandbox: bool = False):
    class _Resolver:
        """Maps /shared and anything under it, as PathResolver does.

        The spill verifies the *final* virtual path resolves back to the file it
        wrote, so a resolver that only knows the root is not a stand-in for one.
        """

        def resolve(self, virtual: str) -> str:
            assert virtual.startswith("/shared")
            return str(tmp_path / "shared" / virtual[len("/shared") :].lstrip("/"))

    return SimpleNamespace(
        path_resolver=_Resolver(), sandbox_enabled=sandbox, chat_id=chat_id
    )


@pytest.fixture(autouse=True)
def _canonical_root(tmp_path, monkeypatch):
    """The spill root comes from config, not from whatever /shared maps to.

    A custom volume can retarget /shared, so the writer derives the canonical
    directory itself; the tests have to point that same config at tmp_path.
    """
    from suzent.config import CONFIG

    monkeypatch.setattr(CONFIG, "sandbox_data_path", str(tmp_path), raising=False)


@pytest.fixture
def deps(tmp_path):
    return _deps(tmp_path)


def _chat_dir(
    tmp_path: Path, chat_id: str = "chat-1", *, sandbox: bool = False
) -> Path:
    prefix = "sandbox" if sandbox else "host"
    return tmp_path / "shared" / ".overflow" / f"{prefix}-{chat_id}"


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
    assert "kept up to 25h" in out


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

    assert spill.path.startswith(f"{OVERFLOW_VIRTUAL_DIR}/sandbox-chat-1/")


def test_a_sandbox_spill_is_readable_by_a_different_uid(tmp_path):
    """Bind mounts preserve numeric ownership and the sandbox image runs as a
    fixed uid 1000, which need not match the host service's. A 0600 file would
    be unreadable by the very agent the marker points at.

    Sandbox only: host mode reads the file as the same uid that wrote it, so it
    gains nothing from the looser bits and pays for them on a multi-user host.
    """
    spill_overflow("x" * 100, deps=_deps(tmp_path, sandbox=True), kind="t")

    chat_dir = _chat_dir(tmp_path, sandbox=True)
    written = next(chat_dir.glob("*.txt"))

    assert os.stat(written).st_mode & 0o044, "the sandbox cannot read the spill"
    assert os.stat(chat_dir).st_mode & 0o011, "the sandbox cannot traverse to it"


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
    """Sandbox mode needs /shared to resolve so it can advertise a path; host
    mode writes the canonical directory and never asks."""

    class _Broken:
        def resolve(self, virtual: str) -> str:
            raise ValueError("no matching custom mount is registered")

    deps = SimpleNamespace(path_resolver=_Broken(), sandbox_enabled=True, chat_id="c")

    assert spill_overflow("x" * 100, deps=deps, kind="t") is None


def test_a_remapped_shared_mount_is_not_written_to(tmp_path):
    """A custom volume can target /shared and PathResolver gives it priority.
    Writing there would put .overflow in the user's own directory, force-chmod
    it 0755, and leave the files where the sweep never looks."""
    elsewhere = tmp_path / "someone-elses-folder"
    elsewhere.mkdir()

    class _Remapped:
        def resolve(self, virtual: str) -> str:
            return str(elsewhere)

    deps = SimpleNamespace(path_resolver=_Remapped(), sandbox_enabled=True, chat_id="c")

    assert spill_overflow("x" * 100, deps=deps, kind="t") is None
    assert list(elsewhere.iterdir()) == [], "wrote into the remapped mount"


def test_host_mode_writes_the_canonical_root_regardless(tmp_path):
    """Host mode advertises a host path, so a remapped /shared is irrelevant to
    it — but the file still has to land where the sweep looks."""

    class _Remapped:
        def resolve(self, virtual: str) -> str:
            return str(tmp_path / "somewhere-else")

    deps = SimpleNamespace(
        path_resolver=_Remapped(), sandbox_enabled=False, chat_id="c"
    )

    spill = spill_overflow("x" * 100, deps=deps, kind="t")

    assert spill is not None
    assert str(tmp_path / "shared" / ".overflow") in spill.path


# --- one chat's output is not another chat's to read --------------------------


def test_spills_are_scoped_to_their_chat(tmp_path):
    """/shared is mounted into every session, so an unscoped directory is
    readable by every other chat on the deployment. These files hold raw tool
    output and reminder text — conversation content — and a random filename is
    no defence against listing the directory."""
    first = spill_overflow("secret alpha", deps=_deps(tmp_path, chat_id="a"), kind="t")
    second = spill_overflow("secret beta", deps=_deps(tmp_path, chat_id="b"), kind="t")

    assert "-a/" in first.path.replace(str(tmp_path), "")
    assert "-b/" in second.path.replace(str(tmp_path), "")
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
    """Derived, not written out: the two would drift the first time either
    number moved — and the sweep interval is part of the bound because deletion
    happens on a tick, not on an alarm."""
    import suzent.tools.overflow as overflow
    from suzent.tools.overflow import retention_hint

    monkeypatch.setattr(overflow, "OVERFLOW_TTL_SECONDS", 3 * 60 * 60)
    monkeypatch.setattr(overflow, "OVERFLOW_SWEEP_INTERVAL_SECONDS", 60 * 60)

    assert retention_hint() == "kept up to 4h"


def test_the_promise_covers_the_polling_interval(monkeypatch):
    """A spill created just after a sweep is still inside the window at the tick
    following its expiry, and goes on the one after that."""
    import suzent.tools.overflow as overflow
    from suzent.tools.overflow import retention_hint

    monkeypatch.setattr(overflow, "OVERFLOW_TTL_SECONDS", 10 * 60 * 60)
    monkeypatch.setattr(overflow, "OVERFLOW_SWEEP_INTERVAL_SECONDS", 2 * 60 * 60)

    assert retention_hint() == "kept up to 12h"


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
        "_spill_payload",
        lambda payload, clipped, **kw: time.sleep(0.2) or Spill("/tmp/x.txt", False),
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


def test_the_sweep_has_a_path_based_twin(tmp_path, monkeypatch):
    """Only spill_overflow() chose an implementation, so on a platform without
    dir_fd the sweep called descriptor operations that do not exist there and
    retention simply did not run — the third time in this file that hardening
    one path and not its twin left the twin broken."""
    import time

    from suzent.config import CONFIG
    import suzent.tools.overflow as overflow
    from suzent.tools.overflow import OVERFLOW_TTL_SECONDS, sweep_overflow

    chat_dir = _chat_dir(tmp_path)
    chat_dir.mkdir(parents=True)
    stale = chat_dir / "t-old.txt"
    stale.write_text("yesterday", encoding="utf-8")
    old = time.time() - OVERFLOW_TTL_SECONDS - 60
    os.utime(stale, (old, old))

    monkeypatch.setattr(overflow, "_HAVE_DIR_FD", False)
    monkeypatch.setattr(CONFIG, "sandbox_data_path", str(tmp_path), raising=False)
    sweep_overflow()

    assert not stale.exists()


def test_the_path_sweep_also_applies_the_root_quota(tmp_path, monkeypatch):
    from suzent.config import CONFIG
    import suzent.tools.overflow as overflow
    from suzent.tools.overflow import sweep_overflow

    monkeypatch.setattr(overflow, "OVERFLOW_MAX_ROOT_BYTES", 5_000)
    for chat in ("a", "b", "c", "d"):
        spill_overflow("y" * 3_000, deps=_deps(tmp_path, chat_id=chat), kind="t")

    monkeypatch.setattr(overflow, "_HAVE_DIR_FD", False)
    monkeypatch.setattr(CONFIG, "sandbox_data_path", str(tmp_path), raising=False)
    sweep_overflow()

    root = tmp_path / "shared" / ".overflow"
    total = sum(p.stat().st_size for p in root.rglob("*.txt"))

    assert total <= 5_000 + 3_100, total


@pytest.mark.asyncio
async def test_the_sweep_keeps_running_after_startup(monkeypatch):
    """Running it once left the root quota and the retention window unenforced
    for the lifetime of a long-lived process — a write only ever prunes its own
    chat's directory."""
    import asyncio

    import suzent.tools.overflow as overflow

    calls = 0

    def _count():
        nonlocal calls
        calls += 1

    monkeypatch.setattr(overflow, "sweep_overflow", _count)
    monkeypatch.setattr(overflow, "OVERFLOW_SWEEP_INTERVAL_SECONDS", 0.01)

    task = asyncio.create_task(overflow.sweep_overflow_periodically())
    await asyncio.sleep(0.08)
    task.cancel()

    assert calls > 1, f"the sweep ran {calls} time(s); it must keep running"


@pytest.mark.asyncio
async def test_a_failing_sweep_does_not_end_the_loop(monkeypatch):
    """One bad sweep must not silently disable retention until the next
    restart."""
    import asyncio

    import suzent.tools.overflow as overflow

    calls = 0

    def _boom():
        nonlocal calls
        calls += 1
        raise OSError("disk went away")

    monkeypatch.setattr(overflow, "sweep_overflow", _boom)
    monkeypatch.setattr(overflow, "OVERFLOW_SWEEP_INTERVAL_SECONDS", 0.01)

    task = asyncio.create_task(overflow.sweep_overflow_periodically())
    await asyncio.sleep(0.08)
    task.cancel()

    assert calls > 1


def test_every_registered_tool_can_reach_its_deps():
    """A tool whose forward() takes no RunContext cannot spill: the wrapper has
    nowhere to read deps from, so its oversized output is truncated with no
    path. BrowsingTool's snapshot regularly clears 30,000 characters."""
    import inspect

    from suzent.tools.registry import _all_tool_classes

    missing = []
    for cls in _all_tool_classes():
        try:
            params = list(inspect.signature(cls.forward).parameters)
        except (TypeError, ValueError):
            continue
        if getattr(cls, "output_char_limit", None) and "ctx" not in params:
            missing.append(cls.name)

    assert missing == [], f"these tools cannot spill their output: {missing}"


@pytest.mark.parametrize("umask_value", [0o077, 0o022, 0o000])
def test_sandbox_spills_stay_reachable_under_any_umask(tmp_path, umask_value):
    """Creation modes are masked by the umask, so a service started with 0077
    turns 0755/0644 into 0700/0600 — the permissions that make the marker point
    at a file the sandbox cannot open.

    Checked all the way up to the mount root: correct descendants under an
    unreachable root are still unreachable, which is how the previous version of
    this test passed while /shared sat at 0700.
    """
    previous = os.umask(umask_value)
    try:
        spill = spill_overflow(
            "x" * 100,
            deps=_deps(tmp_path, chat_id=f"u{umask_value:o}", sandbox=True),
            kind="t",
        )
    finally:
        os.umask(previous)

    host_file = (
        _chat_dir(tmp_path, f"u{umask_value:o}", sandbox=True) / Path(spill.path).name
    )
    assert os.stat(host_file).st_mode & 0o044, "the file is not readable"
    walked = host_file.parent
    while True:
        mode = os.stat(walked).st_mode & 0o777
        assert mode & 0o011, f"umask {umask_value:o} left {walked} at {mode:o}"
        if walked == tmp_path / "shared":
            break
        walked = walked.parent


@pytest.mark.parametrize("umask_value", [0o077, 0o000])
def test_host_spills_are_private(tmp_path, umask_value):
    """In host mode the agent is this process — same uid — so the tightest bits
    work and nothing is gained by letting every local account read raw tool
    output. Forced past the umask in the other direction too: 0000 must not
    leave them world-readable."""
    previous = os.umask(umask_value)
    try:
        spill = spill_overflow(
            "x" * 100, deps=_deps(tmp_path, chat_id=f"h{umask_value:o}"), kind="t"
        )
    finally:
        os.umask(previous)

    file_mode = os.stat(spill.path).st_mode & 0o777
    dir_mode = os.stat(Path(spill.path).parent).st_mode & 0o777

    assert file_mode & 0o077 == 0, (
        f"host spill is group/world accessible ({file_mode:o})"
    )
    assert dir_mode & 0o077 == 0, (
        f"host spill dir is group/world accessible ({dir_mode:o})"
    )
    assert file_mode & 0o600, "the owner cannot read its own spill"


def test_the_path_fallback_also_survives_the_umask(tmp_path, monkeypatch):
    import suzent.tools.overflow as overflow

    monkeypatch.setattr(overflow, "_HAVE_DIR_FD", False)
    previous = os.umask(0o077)
    try:
        spill = overflow.spill_overflow(
            "x" * 100,
            deps=_deps(tmp_path, chat_id="fallback", sandbox=True),
            kind="t",
        )
    finally:
        os.umask(previous)

    host_file = _chat_dir(tmp_path, "fallback", sandbox=True) / Path(spill.path).name
    assert os.stat(host_file).st_mode & 0o044
    assert os.stat(host_file.parent).st_mode & 0o011


def test_the_voice_verification_script_still_calls_correctly():
    """A standalone script is not covered by the suite, so a signature change
    breaks it silently. Adding ctx to SpeakTool.forward() bound the utterance to
    ctx and left `text` missing."""
    import ast
    from pathlib import Path as _Path

    source = _Path("tests/verify_voice.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "forward"
    ]

    assert calls, "the script no longer calls forward(); update this test"
    for call in calls:
        assert len(call.args) >= 2, "forward() takes ctx first, then the text"


@pytest.mark.asyncio
async def test_the_sweeper_is_cancelled_at_shutdown():
    """An infinite task the lifespan never cancels keeps running after
    shutdown, and each restart adds another — so an embedded server or an
    in-process restart accumulates hourly sweepers."""
    import inspect

    from suzent import server

    source = inspect.getsource(server.shutdown)

    assert "overflow_sweeper" in source, "the sweeper outlives the application"
    assert "cancel()" in source


def test_a_host_spill_does_not_lock_out_the_sandbox(tmp_path):
    """The mount root and .overflow are shared between execution modes, so
    their mode cannot depend on which one is spilling now: a host spill setting
    them 0700 makes every path already advertised to a sandbox container
    unreadable until some later sandbox spill happens to set them back."""
    sandbox_spill = spill_overflow(
        "s", deps=_deps(tmp_path, chat_id="sbx", sandbox=True), kind="t"
    )
    host_path = _chat_dir(tmp_path, "sbx", sandbox=True) / Path(sandbox_spill.path).name

    # A host-mode chat spills afterwards, touching the shared ancestors.
    spill_overflow("h", deps=_deps(tmp_path, chat_id="host"), kind="t")

    for ancestor in (tmp_path / "shared", tmp_path / "shared" / ".overflow"):
        mode = os.stat(ancestor).st_mode & 0o777
        assert mode & 0o011, f"{ancestor} became untraversable ({mode:o})"
    assert os.stat(host_path).st_mode & 0o044, "the sandbox spill became unreadable"


def test_the_host_chat_directory_is_still_private(tmp_path):
    """Traversable ancestors are not readable contents: the leaf keeps the
    private mode."""
    spill = spill_overflow("h", deps=_deps(tmp_path, chat_id="host"), kind="t")

    assert os.stat(Path(spill.path).parent).st_mode & 0o077 == 0
    assert os.stat(spill.path).st_mode & 0o077 == 0


@pytest.mark.asyncio
async def test_a_wedged_volume_does_not_hold_the_caller(deps, monkeypatch):
    """to_thread frees the loop and bounds nothing. The caller is either a
    reminder being built or a tool call that has already done its work — losing
    the pointer beats losing either."""
    import threading
    import time

    import suzent.tools.overflow as overflow

    monkeypatch.setattr(overflow, "SPILL_TIMEOUT_SECONDS", 0.05)
    # The worker calls _spill_payload; patching spill_overflow would leave the
    # thread doing the real thing.
    monkeypatch.setattr(
        overflow,
        "_spill_payload",
        lambda payload, clipped, **kw: time.sleep(1) or Spill("/x", False),
    )
    monkeypatch.setattr(
        overflow, "_spill_slots", threading.Semaphore(overflow._SPILL_THREADS)
    )

    started = time.monotonic()
    result = await overflow.spill_overflow_async("payload", deps=deps, kind="t")
    elapsed = time.monotonic() - started

    assert result is None, "a wedged write must fall back to the plain marker"
    assert elapsed < 1.0, f"the caller waited {elapsed:.2f}s for a wedged volume"


def test_the_sweeper_survives_an_in_process_restart():
    """shutdown() cancels the sweeper but leaves social_brain set, so the next
    startup() returns at the duplicate-social guard. Starting the sweeper after
    that guard left a restarted application with no retention at all."""
    import inspect

    from suzent import server

    source = inspect.getsource(server.startup)
    sweeper_at = source.index("overflow_sweeper")
    guard_at = source.index("Social brain already initialized")

    assert sweeper_at < guard_at, "the sweeper starts after an early return"


def test_the_synchronous_spill_is_bounded_too(deps, monkeypatch):
    """A sync tool runs on a worker rather than the loop, so a wedged volume
    does not stall other chats — but it holds a tool call that has *already
    succeeded*. Bounding only the async path left two halves of one rule
    disagreeing."""
    import threading
    import time

    import suzent.tools.overflow as overflow

    monkeypatch.setattr(overflow, "SPILL_TIMEOUT_SECONDS", 0.05)
    # The worker calls _spill_payload; patching spill_overflow would leave the
    # thread doing the real thing.
    monkeypatch.setattr(
        overflow,
        "_spill_payload",
        lambda payload, clipped, **kw: time.sleep(1) or Spill("/x", False),
    )
    monkeypatch.setattr(
        overflow, "_spill_slots", threading.Semaphore(overflow._SPILL_THREADS)
    )

    started = time.monotonic()
    result = overflow.spill_overflow_bounded("payload", deps=deps, kind="t")
    elapsed = time.monotonic() - started

    assert result is None
    assert elapsed < 1.0, f"the worker waited {elapsed:.2f}s for a wedged volume"


def test_both_wrappers_bound_the_spill():
    """The rule is 'a spill never holds its caller', so it has to hold on both
    branches of the wrapper, not the one that happened to be reviewed."""
    import inspect

    from suzent.tools import registry

    source = inspect.getsource(registry)

    assert "spill_overflow_async(" in source
    assert "spill_overflow_bounded(" in source
    # The unbounded call must not survive anywhere in the wrapper.
    assert "= spill_overflow(" not in source


def test_the_root_quota_holds_between_sweeps(tmp_path, monkeypatch):
    """Leaving it to the hourly sweep let a burst of chats sit above the
    deployment ceiling for an hour — long enough to fill a volume that every
    directory was individually respecting."""
    import suzent.tools.overflow as overflow

    monkeypatch.setattr(overflow, "OVERFLOW_MAX_ROOT_BYTES", 5_000)

    for chat in ("a", "b", "c", "d", "e"):
        spill_overflow("y" * 3_000, deps=_deps(tmp_path, chat_id=chat), kind="t")

    root = tmp_path / "shared" / ".overflow"
    total = sum(p.stat().st_size for p in root.rglob("*.txt"))

    assert total <= 5_000 + 3_100, f"{total} bytes retained with no sweep run"


def test_the_path_fallback_also_holds_the_root_quota(tmp_path, monkeypatch):
    import suzent.tools.overflow as overflow

    monkeypatch.setattr(overflow, "OVERFLOW_MAX_ROOT_BYTES", 5_000)
    monkeypatch.setattr(overflow, "_HAVE_DIR_FD", False)

    for chat in ("a", "b", "c", "d", "e"):
        overflow.spill_overflow(
            "y" * 3_000, deps=_deps(tmp_path, chat_id=chat), kind="t"
        )

    root = tmp_path / "shared" / ".overflow"
    total = sum(p.stat().st_size for p in root.rglob("*.txt"))

    assert total <= 5_000 + 3_100, total


def test_abandoned_spill_workers_are_bounded(deps, monkeypatch):
    """A timed-out spill is abandoned, not cancelled. With permanently wedged
    storage every oversized result would otherwise park another thread forever,
    until the process runs out and healthy tool calls start failing."""
    import threading
    import time

    import suzent.tools.overflow as overflow

    # A private semaphore: parked workers never release, so draining the
    # module-level one would silently disable spilling for every later test.
    monkeypatch.setattr(
        overflow, "_spill_slots", threading.Semaphore(overflow._SPILL_THREADS)
    )
    monkeypatch.setattr(overflow, "SPILL_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(
        overflow, "_spill_payload", lambda payload, clipped, **kw: time.sleep(1)
    )

    before = threading.active_count()
    for _ in range(20):
        assert overflow.spill_overflow_bounded("x", deps=deps, kind="t") is None
    parked = threading.active_count() - before

    assert parked <= overflow._SPILL_THREADS, (
        f"{parked} threads parked on wedged storage"
    )


def test_a_slot_is_returned_when_the_spill_completes(deps):
    import suzent.tools.overflow as overflow

    before = overflow._spill_slots._value
    for _ in range(5):
        overflow.spill_overflow_bounded("x" * 100, deps=deps, kind="t")

    assert overflow._spill_slots._value == before


def test_switching_execution_mode_does_not_lock_out_earlier_spills(tmp_path):
    """A chat can move between modes, and the mode decides the directory's
    permissions. Sharing one directory let a host spill chmod it 0700 and made
    every sandbox path already advertised from it unreadable — the most recent
    spill retroactively deciding whether older ones could be opened."""
    sandbox_spill = spill_overflow(
        "s", deps=_deps(tmp_path, chat_id="c9", sandbox=True), kind="t"
    )
    written = _chat_dir(tmp_path, "c9", sandbox=True) / Path(sandbox_spill.path).name

    # The same chat, now in host mode.
    spill_overflow("h", deps=_deps(tmp_path, chat_id="c9"), kind="t")

    assert os.stat(written).st_mode & 0o044, "the earlier sandbox spill is unreadable"
    assert os.stat(written.parent).st_mode & 0o011, "its directory is untraversable"


def test_the_two_modes_use_separate_leaves(tmp_path):
    spill_overflow("s", deps=_deps(tmp_path, chat_id="c9", sandbox=True), kind="t")
    spill_overflow("h", deps=_deps(tmp_path, chat_id="c9"), kind="t")

    names = sorted(p.name for p in (tmp_path / "shared" / ".overflow").iterdir())

    assert names == ["host-c9", "sandbox-c9"]


def test_a_slot_is_returned_when_the_worker_cannot_start(deps, monkeypatch):
    """The worker's finally is what returns the slot, so a thread that never
    starts never gives it back — four of those and spilling is off for the life
    of the process."""
    import threading

    import suzent.tools.overflow as overflow

    before = overflow._spill_slots._value

    def _no_thread(*args, **kwargs):
        class _Dead:
            def start(self):
                raise RuntimeError("can't start new thread")

        return _Dead()

    monkeypatch.setattr(threading, "Thread", _no_thread)

    assert overflow.spill_overflow_bounded("x", deps=deps, kind="t") is None
    assert overflow._spill_slots._value == before, "slot leaked"


def test_a_platform_without_fchmod_still_writes(tmp_path, monkeypatch):
    """os.fchmod does not exist on Windows before 3.13, and AttributeError is
    not an OSError — uncaught, it escaped before fdopen took ownership, so every
    oversized result leaked a handle and wrote nothing."""
    import suzent.tools.overflow as overflow

    monkeypatch.delattr(os, "fchmod", raising=False)

    spill = overflow.spill_overflow("x" * 100, deps=_deps(tmp_path), kind="t")

    assert spill is not None
    assert Path(spill.path).read_text(encoding="utf-8") == "x" * 100


def test_an_abandoned_worker_does_not_hold_the_whole_output(deps, monkeypatch):
    """The semaphore bounds threads, not bytes. Handing the worker the original
    string means an abandoned one holds the whole of a hundreds-of-megabyte
    result for as long as the storage stays wedged — four of those being four
    copies of the largest output the process has seen."""
    import time

    import suzent.tools.overflow as overflow

    captured: list[int] = []

    def _wedged(payload, clipped, **kw):
        captured.append(len(payload))
        time.sleep(1)

    import threading

    monkeypatch.setattr(
        overflow, "_spill_slots", threading.Semaphore(overflow._SPILL_THREADS)
    )
    monkeypatch.setattr(overflow, "SPILL_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(overflow, "OVERFLOW_MAX_FILE_BYTES", 1_000)
    monkeypatch.setattr(overflow, "_spill_payload", _wedged)

    assert overflow.spill_overflow_bounded("x" * 5_000_000, deps=deps, kind="t") is None

    assert captured, "the worker never ran"
    assert captured[0] <= 1_000, (
        f"the worker captured {captured[0]} bytes of a 5,000,000-char result"
    )


@pytest.mark.asyncio
async def test_the_async_path_does_not_use_the_shared_executor():
    """to_thread was wrong twice over: cancelling its future does not remove the
    work item from the executor queue, so a timed-out submission keeps holding
    what it captured until some worker dequeues it — and those threads are
    shared with everything else that offloads."""
    import inspect

    import suzent.tools.overflow as overflow

    source = inspect.getsource(overflow.spill_overflow_async)

    assert "asyncio.to_thread(" not in source, (
        "the spill is back on the shared executor"
    )
    assert "daemon=True" in source


@pytest.mark.asyncio
async def test_a_wedged_async_spill_still_returns(deps, monkeypatch):
    import threading
    import time

    import suzent.tools.overflow as overflow

    monkeypatch.setattr(
        overflow, "_spill_slots", threading.Semaphore(overflow._SPILL_THREADS)
    )
    monkeypatch.setattr(overflow, "SPILL_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(
        overflow, "_spill_payload", lambda payload, clipped, **kw: time.sleep(1)
    )

    started = time.monotonic()
    result = await overflow.spill_overflow_async("payload", deps=deps, kind="t")

    assert result is None
    assert time.monotonic() - started < 1.0


def test_the_sweep_runs_on_a_thread_the_process_can_leave():
    """Cancelling the coroutine does not stop the function, and default-executor
    threads are joined at interpreter exit — so a sweep on a wedged filesystem
    would hold up the shutdown the cancellation exists to allow."""
    import inspect

    import suzent.tools.overflow as overflow
    from suzent import server

    background = inspect.getsource(overflow.sweep_overflow_in_background)

    assert "asyncio.to_thread(" not in background
    assert "daemon=True" in background
    assert "asyncio.to_thread(sweep_overflow" not in inspect.getsource(server.startup)


def test_a_failing_sweep_thread_is_not_an_unhandled_exception(monkeypatch, recwarn):
    """Moving the sweep onto a thread moved its failures out of reach of the
    loop's handler — they surfaced as unhandled thread errors instead."""
    import threading

    import suzent.tools.overflow as overflow

    def _boom():
        raise OSError("disk went away")

    monkeypatch.setattr(overflow, "sweep_overflow", _boom)

    before = threading.active_count()
    overflow.sweep_overflow_in_background()
    for _ in range(100):
        if threading.active_count() <= before:
            break
        time.sleep(0.01)

    assert threading.active_count() <= before, "the sweep thread never finished"


def test_only_one_sweep_runs_at_a_time(monkeypatch):
    """On storage wedged for longer than the interval, every tick would
    otherwise start another uncancellable thread — and when storage recovers,
    an hour of queued sweeps all start at once."""
    import threading

    import suzent.tools.overflow as overflow

    release = threading.Event()
    started = threading.Semaphore(0)

    def _blocked():
        started.release()
        release.wait(timeout=5)

    monkeypatch.setattr(overflow, "sweep_overflow", _blocked)

    before = threading.active_count()
    overflow.sweep_overflow_in_background()
    assert started.acquire(timeout=2), "the first sweep never started"
    for _ in range(10):
        overflow.sweep_overflow_in_background()

    running = threading.active_count() - before
    release.set()

    assert running == 1, f"{running} sweeps running at once"


def test_the_sweep_lock_is_released_for_the_next_tick(monkeypatch):
    import suzent.tools.overflow as overflow

    monkeypatch.setattr(overflow, "sweep_overflow", lambda: None)

    for _ in range(3):
        overflow.sweep_overflow_in_background()
        for _ in range(100):
            if not overflow._sweep_lock.locked():
                break
            time.sleep(0.01)
        assert not overflow._sweep_lock.locked(), "the lock outlived its sweep"


def test_a_masked_mount_writes_nothing_at_all(tmp_path):
    """Validating after the write meant the file was created and both quota
    passes had run before the answer was thrown away — so a chat with a masked
    mount produced unreachable orphans on every oversized result, and its
    pruning could evict spills other chats still pointed at."""

    class _Masked:
        """Resolves /shared canonically but sends anything below .overflow
        somewhere else, as a nested custom volume does."""

        def resolve(self, virtual: str) -> str:
            if virtual.startswith("/shared/.overflow"):
                return str(tmp_path / "masked" / virtual.split("/")[-1])
            return str(tmp_path / "shared" / virtual[len("/shared") :].lstrip("/"))

    deps = SimpleNamespace(
        path_resolver=_Masked(), sandbox_enabled=True, chat_id="masked-chat"
    )

    assert spill_overflow("x" * 100, deps=deps, kind="t") is None
    assert not (tmp_path / "shared" / ".overflow").exists(), "an orphan was written"


def test_a_masked_mount_cannot_evict_another_chats_spill(tmp_path, monkeypatch):
    """The eviction half: the rejected chat's pruning ran against the shared
    root before the rejection."""
    import suzent.tools.overflow as overflow

    monkeypatch.setattr(overflow, "OVERFLOW_MAX_ROOT_BYTES", 4_000)
    good = spill_overflow(
        "y" * 3_000, deps=_deps(tmp_path, chat_id="good", sandbox=True), kind="t"
    )
    written = _chat_dir(tmp_path, "good", sandbox=True) / Path(good.path).name

    class _Masked:
        def resolve(self, virtual: str) -> str:
            if virtual.startswith("/shared/.overflow"):
                return str(tmp_path / "masked" / virtual.split("/")[-1])
            return str(tmp_path / "shared" / virtual[len("/shared") :].lstrip("/"))

    bad = SimpleNamespace(
        path_resolver=_Masked(), sandbox_enabled=True, chat_id="masked-chat"
    )
    for _ in range(5):
        assert spill_overflow("z" * 3_000, deps=bad, kind="t") is None

    assert written.exists(), "a rejected spill evicted a valid one"


@pytest.mark.asyncio
async def test_the_async_caller_slices_but_does_not_encode(deps, monkeypatch):
    """The slice bounds what an abandoned worker retains; the encode allocates
    up to four bytes per character and belongs off the loop."""
    import threading

    import suzent.tools.overflow as overflow

    encoded_on: list[str] = []
    real = overflow._encode_bounded

    def _watch(head, dropped):
        encoded_on.append(threading.current_thread().name)
        return real(head, dropped)

    monkeypatch.setattr(overflow, "_encode_bounded", _watch)

    await overflow.spill_overflow_async("é" * 10_000, deps=deps, kind="t")

    assert encoded_on, "the encode never ran"
    assert all(n.startswith("overflow-spill") for n in encoded_on), (
        f"encoding ran on {encoded_on}"
    )


def test_the_bounded_prefix_is_a_slice_not_an_encode():
    """_bound_chars must stay cheap: it is what the event loop runs."""
    import suzent.tools.overflow as overflow

    head, dropped = overflow._bound_chars("é" * (overflow.OVERFLOW_MAX_FILE_BYTES + 10))

    assert isinstance(head, str)
    assert len(head) == overflow.OVERFLOW_MAX_FILE_BYTES
    assert dropped is True


def test_a_failed_fallback_write_leaves_no_file(tmp_path, monkeypatch):
    """A half-written file that was never advertised is pure litter, and this
    branch skips pruning, so it sits there until the sweep."""
    import suzent.tools.overflow as overflow

    monkeypatch.setattr(overflow, "_HAVE_DIR_FD", False)

    real_fdopen = os.fdopen

    def _explode(fd, *args, **kwargs):
        handle = real_fdopen(fd, *args, **kwargs)

        class _Broken:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                handle.close()
                return False

            def write(self, data):
                raise OSError("volume disconnected")

        return _Broken()

    monkeypatch.setattr(os, "fdopen", _explode)

    assert overflow.spill_overflow("x" * 100, deps=_deps(tmp_path), kind="t") is None

    chat_dir = _chat_dir(tmp_path)
    assert not chat_dir.exists() or list(chat_dir.glob("*.txt")) == []


def test_a_spill_that_lands_after_the_deadline_is_removed(deps, tmp_path, monkeypatch):
    """Storage that is slow but recovers writes a file nobody was told about —
    it consumes the per-chat and root quotas and can evict spills whose paths
    *were* handed out."""
    import threading

    import suzent.tools.overflow as overflow

    monkeypatch.setattr(
        overflow, "_spill_slots", threading.Semaphore(overflow._SPILL_THREADS)
    )
    monkeypatch.setattr(overflow, "SPILL_TIMEOUT_SECONDS", 0.05)

    real = overflow._spill_payload

    def _slow(payload, clipped, **kw):
        time.sleep(0.3)
        return real(payload, clipped, **kw)

    monkeypatch.setattr(overflow, "_spill_payload", _slow)

    assert overflow.spill_overflow_bounded("x" * 100, deps=deps, kind="t") is None

    for _ in range(100):
        if list(_chat_dir(tmp_path).glob("*.txt")):
            time.sleep(0.01)
        else:
            break
    time.sleep(0.3)

    assert list(_chat_dir(tmp_path).glob("*.txt")) == [], (
        "a late spill was left behind, unadvertised"
    )


def test_the_worker_does_not_retain_the_whole_request(deps, monkeypatch):
    """AgentDeps carries the request's message history, repository context and
    caches. Four abandoned workers holding those is far more than the bounded
    payload the slot limit was reasoning about."""
    import suzent.tools.overflow as overflow

    seen: list[Any] = []

    def _capture(payload, clipped, *, deps, kind):
        seen.append(deps)
        return None

    monkeypatch.setattr(overflow, "_spill_payload", _capture)

    bulky = SimpleNamespace(
        path_resolver=deps.path_resolver,
        sandbox_enabled=False,
        chat_id="chat-1",
        last_messages=["a very long history"] * 1000,
        repository_context="...",
    )
    overflow.spill_overflow_bounded("x" * 100, deps=bulky, kind="t")

    assert seen, "the worker never ran"
    assert not hasattr(seen[0], "last_messages"), "the worker kept the whole deps"
    assert seen[0].chat_id == "chat-1"


def test_the_snapshot_carries_what_a_spill_needs():
    import suzent.tools.overflow as overflow

    snap = overflow._deps_snapshot(
        SimpleNamespace(
            path_resolver="R", sandbox_enabled=True, chat_id="c", extra="dropped"
        )
    )

    assert (snap.path_resolver, snap.sandbox_enabled, snap.chat_id) == ("R", True, "c")
    assert not hasattr(snap, "extra")
