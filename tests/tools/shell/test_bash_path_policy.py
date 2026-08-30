from types import SimpleNamespace

from suzent.tools.filesystem.file_tool_utils import get_or_create_path_resolver
from suzent.tools.shell.permissions.path_policy import validate_paths
from suzent.tools.shell.permissions.policy_models import CommandDecision, PathUse


def _deps(tmp_path, sandbox_enabled=False):
    return SimpleNamespace(
        chat_id="chat-1",
        sandbox_enabled=sandbox_enabled,
        workspace_root=str(tmp_path),
        custom_volumes=[],
        path_resolver=None,
    )


def test_path_policy_asks_before_leaving_the_workspace_on_the_host(tmp_path):
    # Advisory, not a boundary: paths are only extracted for catalogued base
    # commands, so a hard deny stopped `cat /etc/passwd` while
    # `python -c "open('/etc/passwd')"` sailed past. Asking lets the user
    # authorize the folder they pointed the agent at.
    resolver = get_or_create_path_resolver(_deps(tmp_path))

    result = validate_paths(
        [PathUse(path="/etc/passwd", operation="read")],
        resolver,
    )

    assert result is not None
    assert result.decision == CommandDecision.ASK


def test_path_policy_still_denies_outside_the_sandbox(tmp_path):
    resolver = get_or_create_path_resolver(_deps(tmp_path, sandbox_enabled=True))

    result = validate_paths(
        [PathUse(path="/mnt/not-registered/file", operation="read")],
        resolver,
    )

    assert result is not None
    assert result.decision == CommandDecision.DENY


def test_path_policy_allows_paths_inside_the_grants(tmp_path):
    resolver = get_or_create_path_resolver(_deps(tmp_path))

    assert (
        validate_paths(
            [PathUse(path=str(tmp_path / "notes.txt"), operation="read")],
            resolver,
        )
        is None
    )


def test_path_policy_denies_dangerous_delete_target(tmp_path):
    resolver = get_or_create_path_resolver(_deps(tmp_path))

    result = validate_paths(
        [PathUse(path="/", operation="delete")],
        resolver,
    )

    assert result is not None
    assert result.decision == CommandDecision.DENY
