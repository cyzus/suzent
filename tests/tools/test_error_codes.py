"""Every ``ToolErrorCode`` a tool names must actually exist.

``ToolErrorCode.NOT_FOUND`` was referenced by the goal and task tools without
being defined, so ``update_task`` on a missing id and ``manage_goal`` with no
active goal raised ``AttributeError`` instead of returning the refusal they had
written. Nothing caught it because these are error paths: the attribute is only
looked up once the tool has already decided to fail.

A static scan is the right shape of check here -- reaching all of these paths
for real would mean standing up a database per case.
"""

import ast
import pathlib

from suzent.tools.base import ToolErrorCode

TOOLS_ROOT = pathlib.Path(__file__).resolve().parents[2] / "src" / "suzent"


def _referenced_codes() -> set[tuple[str, str, int]]:
    """``(member, file, line)`` for every ``ToolErrorCode.X`` under src/suzent."""
    found: set[tuple[str, str, int]] = set()
    for path in TOOLS_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "ToolErrorCode"
            ):
                found.add((node.attr, str(path), node.lineno))
    return found


def test_every_referenced_error_code_exists() -> None:
    references = _referenced_codes()
    assert references, "scan found no ToolErrorCode references at all"

    defined = set(ToolErrorCode.__members__)
    bogus = sorted(
        f"{member} at {path}:{line}"
        for member, path, line in references
        if member not in defined
    )
    assert not bogus, "undefined ToolErrorCode members referenced:\n  " + "\n  ".join(
        bogus
    )
