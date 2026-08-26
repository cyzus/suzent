"""Guards on what the CLI and config layers are allowed to import at startup.

Importing the tool registry pulls in pydantic-ai, MCP and the database stack --
roughly half a second that every `suzent` invocation used to pay before it
printed a single line. These tests fail loudly if that creeps back in.
"""

import subprocess
import sys

import pytest

_HEAVY_MODULES = ("pydantic_ai", "sqlmodel", "sqlalchemy", "fastmcp")


def _modules_loaded_after_importing(target: str) -> set[str]:
    """Import ``target`` in a clean interpreter and report the heavy modules it pulled."""
    code = (
        "import sys\n"
        f"import {target}\n"
        f"loaded = [m for m in {_HEAVY_MODULES!r} if m in sys.modules]\n"
        "print('LOADED:' + ','.join(loaded))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    marker = next(
        line for line in result.stdout.splitlines() if line.startswith("LOADED:")
    )
    return {name for name in marker[len("LOADED:") :].split(",") if name}


@pytest.mark.parametrize("target", ["suzent.config", "suzent.cli"])
def test_startup_import_stays_clear_of_the_agent_runtime(target):
    assert _modules_loaded_after_importing(target) == set()


def test_tool_name_helpers_do_not_need_the_registry():
    assert _modules_loaded_after_importing("suzent.tools.names") == set()


def test_tools_package_reexports_still_resolve():
    from suzent.tools import GrepTool, PathResolver, ReadFileTool, Tool, ToolResult

    assert {
        Tool.__name__,
        ToolResult.__name__,
        PathResolver.__name__,
        ReadFileTool.__name__,
        GrepTool.__name__,
    } == {"Tool", "ToolResult", "PathResolver", "ReadFileTool", "GrepTool"}


def test_filesystem_package_reexports_still_resolve():
    from suzent.tools.filesystem import (
        EditFileTool,
        GlobTool,
        get_or_create_path_resolver,
    )

    assert EditFileTool.__name__ == "EditFileTool"
    assert GlobTool.__name__ == "GlobTool"
    assert callable(get_or_create_path_resolver)


def test_tools_package_rejects_unknown_attributes():
    import suzent.tools

    with pytest.raises(AttributeError):
        suzent.tools.NoSuchTool
