"""Characterization tests for the image / vision gating in the chat processor.

When the active model lacks vision, attached images must be dropped from the
LLM payload (so the provider never rejects raw bytes) while staying readable on
disk via the analyze_image tool. Two distinct audiences result:

- The USER sees a friendly in-chat ``notice`` (no tool jargon).
- The MODEL gets a hidden ``<system-reminder>`` directive pointing at
  analyze_image with the VIRTUAL paths its tools can resolve.

These tests pin the two derived strings produced from the strip decision. They
guard the behavior added for non-vision models without driving the full
streaming generator.
"""

from suzent.core.chat_processor import (
    _stripped_image_notice,
    _stripped_image_reminder,
)


# ---------------------------------------------------------------------------
# User-facing notice
# ---------------------------------------------------------------------------


def test_notice_includes_model_and_count() -> None:
    notice = _stripped_image_notice("xiaomi_mimo/mimo-v2.5-pro", 2)
    assert "xiaomi_mimo/mimo-v2.5-pro" in notice
    assert "2 image(s)" in notice
    # Mentions the fallback capability so the user knows it isn't a dead end.
    assert "analyze_image" in notice


def test_notice_handles_unknown_model_id() -> None:
    # Unknown models are treated as non-vision (strict); the notice must still
    # render rather than crash on a None model id.
    notice = _stripped_image_notice(None, 1)
    assert "1 image(s)" in notice
    assert "None" in notice


# ---------------------------------------------------------------------------
# Hidden model-facing reminder
# ---------------------------------------------------------------------------


def test_reminder_none_when_nothing_stripped() -> None:
    assert _stripped_image_reminder([]) is None


def test_reminder_lists_every_virtual_path() -> None:
    paths = ["/workspace/uploads/a.png", "/workspace/uploads/b.jpg"]
    reminder = _stripped_image_reminder(paths)
    assert reminder is not None
    for p in paths:
        assert p in reminder
    assert "2 image(s)" in reminder
    assert "analyze_image" in reminder


def test_reminder_uses_virtual_not_host_paths() -> None:
    # The directive must carry the virtual path (PathResolver-resolvable by the
    # agent's tools), never a host path that would escape / fail to resolve.
    reminder = _stripped_image_reminder(["/workspace/uploads/cat.png"])
    assert reminder is not None
    assert "/workspace/uploads/cat.png" in reminder


def test_notice_and_reminder_target_different_audiences() -> None:
    # The user-facing notice stays free of the tool-invocation directive phrasing
    # that belongs only in the hidden reminder, so the two never collapse into
    # one another if edited later.
    notice = _stripped_image_notice("m", 1)
    reminder = _stripped_image_reminder(["/workspace/uploads/x.png"])
    assert reminder is not None
    assert "Use the analyze_image tool" in reminder
    assert "Use the analyze_image tool" not in notice
