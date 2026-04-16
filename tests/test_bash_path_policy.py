from types import SimpleNamespace

from suzent.tools.filesystem.file_tool_utils import get_or_create_path_resolver
from suzent.tools.shell.permissions.path_policy import validate_paths
from suzent.tools.shell.permissions.policy_models import CommandDecision, PathUse


def _deps(tmp_path):
    return SimpleNamespace(
        chat_id="chat-1",
        sandbox_enabled=False,
        workspace_root=str(tmp_path),
        custom_volumes=[],
        path_resolver=None,
    )


def test_path_policy_denies_outside_workspace(tmp_path):
    resolver = get_or_create_path_resolver(_deps(tmp_path))

    result = validate_paths(
        [PathUse(path="/etc/passwd", operation="read")],
        resolver,
    )

    assert result is not None
    assert result.decision == CommandDecision.DENY


def test_path_policy_denies_dangerous_delete_target(tmp_path):
    resolver = get_or_create_path_resolver(_deps(tmp_path))

    result = validate_paths(
        [PathUse(path="/", operation="delete")],
        resolver,
    )

    assert result is not None
    assert result.decision == CommandDecision.DENY
