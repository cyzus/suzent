"""SUZENT_TOOL_OUTPUT_CHAR_LIMIT lowers a tool's result cap, never raises it."""

from suzent.tools.base import (
    OUTPUT_CHAR_LIMIT,
    OUTPUT_LIMIT_ENV,
    effective_output_limit,
)


def test_no_override_keeps_the_tools_own_cap(monkeypatch):
    monkeypatch.delenv(OUTPUT_LIMIT_ENV, raising=False)

    assert effective_output_limit(OUTPUT_CHAR_LIMIT) == OUTPUT_CHAR_LIMIT


def test_the_override_lowers_the_cap(monkeypatch):
    monkeypatch.setenv(OUTPUT_LIMIT_ENV, "10000")

    assert effective_output_limit(OUTPUT_CHAR_LIMIT) == 10_000


def test_the_override_never_raises_a_tools_smaller_cap(monkeypatch):
    monkeypatch.setenv(OUTPUT_LIMIT_ENV, "50000")

    assert effective_output_limit(8_000) == 8_000


def test_a_malformed_or_non_positive_override_is_ignored(monkeypatch):
    for value in ("abc", "0", "-5", ""):
        monkeypatch.setenv(OUTPUT_LIMIT_ENV, value)

        assert effective_output_limit(OUTPUT_CHAR_LIMIT) == OUTPUT_CHAR_LIMIT
