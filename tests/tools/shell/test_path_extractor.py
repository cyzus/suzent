from suzent.tools.shell.permissions.command_catalog import (
    COMMAND_PATH_OPERATIONS,
    DESTRUCTIVE_COMMANDS,
)
from suzent.tools.shell.permissions.command_parser import parse_command
from suzent.tools.shell.permissions.path_extractor import extract_path_uses
from suzent.tools.shell.permissions.policy_models import PathUse


def _paths(command: str) -> list[PathUse]:
    return extract_path_uses(parse_command(command))


def test_read_only_catalog_commands_validate_paths() -> None:
    assert _paths("wc README.md") == [PathUse(path="README.md", operation="read")]
    assert _paths("sort data.txt") == [PathUse(path="data.txt", operation="read")]
    assert _paths("uniq values.txt") == [PathUse(path="values.txt", operation="read")]


def test_sed_path_operation_matches_read_only_classification() -> None:
    assert _paths("sed -e 's/a/b/' file.txt") == [
        PathUse(path="file.txt", operation="read")
    ]
    assert _paths("sed -i 's/a/b/' file.txt") == [
        PathUse(path="file.txt", operation="write")
    ]


def test_mv_uses_write_not_delete() -> None:
    assert _paths("mv src.txt dst.txt") == [
        PathUse(path="src.txt", operation="write"),
        PathUse(path="dst.txt", operation="write"),
    ]
    assert _paths("rm old.txt") == [PathUse(path="old.txt", operation="delete")]


def test_every_destructive_command_has_a_path_operation() -> None:
    # Guard against adding a command to DESTRUCTIVE_COMMANDS without giving it a
    # path operation in COMMAND_PATH_OPERATIONS (mv is intentionally a write).
    missing = DESTRUCTIVE_COMMANDS - COMMAND_PATH_OPERATIONS.keys()
    assert not missing
