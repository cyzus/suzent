"""The dream agent is told its two directories the way its own tools take them.

This was the last place a host-mode agent was handed virtual paths. It worked
— PathResolver maps `/mnt/notebook` in host mode too, and the dream tool set
happens to contain no shell tool, so nothing could receive a path it could not
resolve. But the safety was accidental: it held only while that tool list stayed
free of a shell, and it left the runner (which works on host paths) and the
agent describing one directory two different ways.
"""

import pytest

from suzent.memory import memory_context
from suzent.memory.memory_context import (
    DREAM_MEMORY_ROOT,
    DREAM_NOTEBOOK_ROOT,
    DreamRoots,
    resolve_dream_roots,
)


class _Resolver:
    def __init__(self, mapping: dict[str, str]):
        self._mapping = mapping

    def resolve(self, virtual: str) -> str:
        return self._mapping[virtual]


def test_sandbox_keeps_the_sandbox_spelling():
    roots = resolve_dream_roots(sandbox_enabled=True)

    assert roots.memory_root == DREAM_MEMORY_ROOT
    assert roots.notebook_root == DREAM_NOTEBOOK_ROOT


def test_host_gets_host_paths():
    resolver = _Resolver(
        {
            DREAM_MEMORY_ROOT: "/Users/x/.suzent/shared/memory",
            DREAM_NOTEBOOK_ROOT: "/Users/x/vault",
        }
    )

    roots = resolve_dream_roots(sandbox_enabled=False, path_resolver=resolver)

    assert roots.memory_root == "/Users/x/.suzent/shared/memory"
    assert roots.notebook_root == "/Users/x/vault"


def test_an_unresolvable_root_falls_back_rather_than_half_resolving():
    """A virtual path PathResolver can map beats a host path that exists
    nowhere."""

    class _Broken:
        def resolve(self, virtual: str) -> str:
            raise ValueError("no matching custom mount is registered")

    roots = resolve_dream_roots(sandbox_enabled=False, path_resolver=_Broken())

    assert roots.notebook_root == DREAM_NOTEBOOK_ROOT


def test_no_prompt_mentions_the_other_mode():
    """The whole point: neither mode reads text addressed to the other."""
    host = DreamRoots("/Users/x/logs", "/Users/x/vault")
    sandbox = resolve_dream_roots(sandbox_enabled=True)

    def _all(roots: DreamRoots) -> str:
        return "\n".join(
            [
                memory_context.build_dream_system_prompt(roots),
                memory_context.build_dream_instructions(
                    roots,
                    start="2026-01-01",
                    end="2026-01-02",
                    confirmations="   (none)",
                    revisits="   (none)",
                ),
                memory_context.build_lint_system_prompt(roots),
                memory_context.build_lint_instructions(roots),
            ]
        )

    host_text = _all(host)
    assert "/mnt/" not in host_text
    assert "/shared/memory" not in host_text
    assert "/Users/x/vault" in host_text

    sandbox_text = _all(sandbox)
    assert "/Users/x" not in sandbox_text
    assert DREAM_NOTEBOOK_ROOT in sandbox_text


def test_the_superseded_path_follows_the_roots():
    """The agent appends to it and the runner reads it, so the two must land on
    the same file."""
    host = DreamRoots("/m", "/Users/x/vault")

    assert host.superseded_path.startswith("/Users/x/vault/.state/")
    assert resolve_dream_roots(sandbox_enabled=True).superseded_path.startswith(
        DREAM_NOTEBOOK_ROOT
    )


def test_the_agent_and_the_runner_mean_the_same_vault():
    """resolve_notebook_dir() is what points the markdown store at the mapped
    volume. In host mode the agent's notebook_root has to be that same
    directory, or the runner reads a vault the agent never wrote to."""
    from suzent.config import CONFIG
    from suzent.config.model import get_effective_volumes
    from suzent.memory.lifecycle import resolve_notebook_dir
    from suzent.tools.filesystem.path_resolver import PathResolver

    if CONFIG.sandbox_enabled:
        pytest.skip("host-mode invariant")

    resolver = PathResolver(
        chat_id="dream", sandbox_enabled=False, custom_volumes=get_effective_volumes([])
    )
    roots = resolve_dream_roots(sandbox_enabled=False, path_resolver=resolver)

    assert roots.notebook_root.rstrip("/") == resolve_notebook_dir().rstrip("/")


def test_the_dream_agent_holds_no_shell_tool():
    """Not required any more — host paths work with any tool — but the tool list
    is small and a shell in it would mean the dream can run commands during an
    unattended background job. Worth noticing if it ever changes."""
    from suzent.config import CONFIG
    from suzent.tools.registry import SHELL_TOOL_CLASS_NAMES

    assert not (set(CONFIG.memory_dream_tools) & set(SHELL_TOOL_CLASS_NAMES))
