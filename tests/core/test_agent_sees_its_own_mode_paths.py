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


def test_host_mode_never_mentions_the_virtual_scheme():
    """Not "told not to use /mnt" — never shown it. Naming a path scheme is how
    a model learns the scheme exists, and the prohibition used to arrive in the
    same prompt as a Directory Mappings block offering /mnt paths for use."""
    from suzent.prompts import build_execution_mode_section

    section = build_execution_mode_section(
        sandbox_enabled=False, workspace_root="/Users/x/proj", shell_type="zsh"
    )

    assert "/mnt" not in section
    assert "Do NOT use virtual" not in section


def test_sandbox_mode_does_describe_its_own_mounts():
    """The mirror: /mnt is real there, so it is named."""
    from suzent.prompts import build_execution_mode_section

    section = build_execution_mode_section(
        sandbox_enabled=True, workspace_root="/workspace", shell_type="bash"
    )

    assert "/mnt/..." in section


@pytest.mark.parametrize(
    "sandbox,expected,forbidden",
    [
        (False, "/Users/suzy/Obsidian", "/mnt/notebook"),
        (True, "/mnt/notebook", "/Users/suzy/Obsidian"),
    ],
)
def test_directory_mappings_list_one_usable_path(sandbox, expected, forbidden):
    """The host:mount pair went to both modes, so each read half a line meant
    for the other."""
    from types import SimpleNamespace

    from suzent.prompts import build_custom_volumes_section

    deps = SimpleNamespace(
        custom_volumes=["/Users/suzy/Obsidian:/mnt/notebook"],
        custom_volume_metadata={},
        sandbox_enabled=sandbox,
    )

    section = build_custom_volumes_section(deps)

    assert expected in section
    assert forbidden not in section


@pytest.mark.parametrize("sandbox", [True, False])
def test_the_skill_catalogue_already_follows_the_rule(sandbox: bool):
    """Pinned because it is the reference implementation of the principle: the
    listing shows virtual paths only in sandbox mode."""
    from suzent.skills.hooks import skills_reminder_hook
    import inspect

    source = inspect.getsource(skills_reminder_hook)

    assert "if sandbox_enabled:" in source
    assert "skill.path.resolve()" in source
