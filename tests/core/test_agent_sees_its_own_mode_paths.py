"""The agent is told paths in the vocabulary of the filesystem it actually has.

Host mode shows host paths; sandbox mode shows sandbox paths. No translation
layer between the two, and no hardcoded virtual literal that happens to work
because PathResolver quietly maps it.

The uploads path broke this: it was hardcoded to /workspace/uploads in both
modes. It "worked" because PathResolver resolves virtual paths in host mode
too — but the host-mode environment section tells the agent not to use virtual
paths, and a shell tool has no resolver, so the same path fails the moment the
agent reaches for one instead of analyze_image.
"""

from pathlib import Path

import pytest

from suzent.core.chat_processor import ChatProcessor, _stripped_image_reminder


class _Upload:
    filename = "photo.png"
    content_type = "image/png"

    async def read(self) -> bytes:
        return b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("sandbox", [True, False])
async def test_the_upload_path_matches_the_mode(tmp_path: Path, sandbox: bool):
    prefix = "/workspace/uploads" if sandbox else str(tmp_path)

    result = await ChatProcessor()._process_upload_file(_Upload(), tmp_path, prefix)

    assert result["agent_path"].startswith(prefix)
    if not sandbox:
        assert not result["agent_path"].startswith("/workspace"), (
            "host mode was handed a virtual path"
        )


def test_the_vision_reminder_repeats_whatever_it_is_given(tmp_path: Path):
    """It formats, it does not translate — so the decision belongs upstream,
    where the mode is known."""
    host = str(tmp_path / "photo.png")

    text = _stripped_image_reminder([host])

    assert host in text
    assert "/workspace" not in text


def test_host_mode_is_told_not_to_use_virtual_paths():
    """The instruction the old upload path contradicted. Kept as a test so the
    two cannot drift back into disagreeing."""
    from suzent.prompts import build_execution_mode_section

    section = build_execution_mode_section(
        sandbox_enabled=False, workspace_root="/Users/x/proj", shell_type="zsh"
    )

    assert "Do NOT use virtual" in section


def test_sandbox_mode_is_not_told_that():
    from suzent.prompts import build_execution_mode_section

    section = build_execution_mode_section(
        sandbox_enabled=True, workspace_root="/workspace", shell_type="bash"
    )

    assert "Do NOT use virtual" not in section


@pytest.mark.parametrize("sandbox", [True, False])
def test_the_skill_catalogue_already_follows_the_rule(sandbox: bool):
    """Pinned because it is the reference implementation of the principle: the
    listing shows virtual paths only in sandbox mode."""
    from suzent.skills.hooks import skills_reminder_hook
    import inspect

    source = inspect.getsource(skills_reminder_hook)

    assert "if sandbox_enabled:" in source
    assert "skill.path.resolve()" in source
