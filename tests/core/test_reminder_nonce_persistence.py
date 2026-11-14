"""The reminder token survives restarts so stored history stays byte-stable."""

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from suzent.core.system_reminder import _load_or_create_nonce


def test_creates_token_with_owner_only_permissions(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "reminder_nonce"
    token = _load_or_create_nonce(path)
    assert len(token) == 16
    assert path.read_text() == token
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_reuses_existing_token(tmp_path: Path) -> None:
    path = tmp_path / "reminder_nonce"
    first = _load_or_create_nonce(path)
    assert _load_or_create_nonce(path) == first


@pytest.mark.parametrize("contents", ["not-a-token", "0" * 15, "ABCDEF0123456789"])
def test_replaces_malformed_token(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "reminder_nonce"
    path.write_text(contents)
    token = _load_or_create_nonce(path)
    assert token != contents
    assert path.read_text() == token


def test_replaces_non_ascii_token_file(tmp_path: Path) -> None:
    """A damaged file must not raise at import time and block startup."""
    path = tmp_path / "reminder_nonce"
    path.write_bytes(b"\xff" * 16)
    token = _load_or_create_nonce(path)
    assert path.read_text() == token


def test_falls_back_when_data_dir_is_unwritable(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("")
    token = _load_or_create_nonce(blocker / "runtime" / "reminder_nonce")
    assert len(token) == 16


def test_stored_reminder_survives_a_restart(tmp_path: Path) -> None:
    """A reminder written by one process is still authenticated by the next,
    so the history processor leaves it alone and the prompt prefix is unchanged."""
    env = {**os.environ, "SUZENT_DATA_DIR": str(tmp_path)}
    write = (
        "from suzent.core.system_reminder import wrap_in_system_reminder;"
        "print(wrap_in_system_reminder('ctx'), end='')"
    )
    stored = subprocess.run(
        [sys.executable, "-c", write],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    reread = (
        "import sys;"
        "from suzent.core.system_reminder import sanitize_stored_user_prompt;"
        "t=sys.stdin.read();print(sanitize_stored_user_prompt(t)==t, end='')"
    )
    result = subprocess.run(
        [sys.executable, "-c", reread],
        env=env,
        input="hi" + stored,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert result == "True"


def test_empty_token_file_is_replaced_and_then_reused(tmp_path: Path) -> None:
    """An empty file must not disable persistence for every later start."""
    path = tmp_path / "reminder_nonce"
    path.write_text("")
    token = _load_or_create_nonce(path)
    assert path.read_text() == token
    assert _load_or_create_nonce(path) == token


def test_leaves_no_temp_files(tmp_path: Path) -> None:
    _load_or_create_nonce(tmp_path / "reminder_nonce")
    _load_or_create_nonce(tmp_path / "reminder_nonce")
    assert [p.name for p in tmp_path.iterdir()] == ["reminder_nonce"]
