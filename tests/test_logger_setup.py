"""How the two log sinks are arranged.

The case worth pinning down is the one the desktop app creates: it redirects
the backend's stdout into ``server.log`` *and* passes ``LOG_FILE`` pointing at
the same file. Both sinks then wrote every record, in two different formats,
and the console's log viewer showed each line twice.
"""

from __future__ import annotations

import suzent.logger as logger_module
from suzent.logger import CONSOLE_FORMAT, FILE_FORMAT, setup_logging


class _Recorder:
    """Stands in for loguru's logger, recording the sinks it is handed."""

    def __init__(self) -> None:
        self.sinks: list[dict] = []

    def remove(self) -> None:
        self.sinks.clear()

    def add(self, sink, **kwargs) -> None:
        self.sinks.append({"sink": sink, **kwargs})


def _configure(monkeypatch, *, log_file=None, stdout_is_log_file=False, tty=False):
    recorder = _Recorder()
    monkeypatch.setattr(logger_module, "logger", recorder)
    monkeypatch.setattr(logger_module, "_logging_configured", False)
    monkeypatch.setattr(logger_module, "_stdout_is_a_terminal", lambda: tty)
    monkeypatch.setattr(
        logger_module, "_is_where_stdout_already_goes", lambda _p: stdout_is_log_file
    )
    setup_logging(level="INFO", log_file=log_file)
    return recorder.sinks


def test_a_terminal_gets_the_short_coloured_line(monkeypatch):
    sinks = _configure(monkeypatch, tty=True)

    assert len(sinks) == 1
    assert sinks[0]["colorize"] is True
    assert sinks[0]["format"] == CONSOLE_FORMAT


def test_redirected_stdout_gets_the_parseable_line_without_colour(monkeypatch):
    # Colour codes in a captured stdout are litter in every reader of the
    # file, and the console's viewer has to strip them back out.
    sinks = _configure(monkeypatch, tty=False)

    assert len(sinks) == 1
    assert sinks[0]["colorize"] is False
    assert sinks[0]["format"] == FILE_FORMAT


def test_a_log_file_elsewhere_is_written_alongside_the_console(monkeypatch, tmp_path):
    sinks = _configure(monkeypatch, log_file=str(tmp_path / "server.log"), tty=True)

    assert len(sinks) == 2
    assert sinks[1]["level"] == "DEBUG"
    assert sinks[1]["rotation"] == "10 MB"


def test_a_log_file_that_is_already_stdout_is_written_once(monkeypatch, tmp_path):
    log_file = tmp_path / "server.log"

    sinks = _configure(monkeypatch, log_file=str(log_file), stdout_is_log_file=True)

    # The file sink wins: it keeps DEBUG regardless of the console level, and
    # it rotates. Output that never passes through loguru still arrives by
    # way of the redirect.
    assert len(sinks) == 1
    assert sinks[0]["sink"] == str(log_file)
    assert sinks[0]["level"] == "DEBUG"


def test_the_same_file_is_recognised_through_a_different_path(monkeypatch, tmp_path):
    import os
    import sys

    log_file = tmp_path / "server.log"
    log_file.write_text("", encoding="utf-8")
    with log_file.open("a") as handle:
        monkeypatch.setattr(sys, "stdout", handle)
        # A symlink, a relative path and the real path all name one inode.
        link = tmp_path / "linked.log"
        os.symlink(log_file, link)
        assert logger_module._is_where_stdout_already_goes(link)
        assert not logger_module._is_where_stdout_already_goes(tmp_path / "other.log")
