"""Reaching outside the chat's grants asks; it does not veto.

The path check only sees the base commands the catalog extracts paths for, so
as a hard deny above the consent layer it stopped `cat /etc/passwd` while
`python -c "open('/etc/passwd').read()"` went through untouched — filtering
command names rather than access, and leaving the user no way to authorize the
folder they had just asked the agent to work in.
"""

from types import SimpleNamespace

import pytest

from suzent.tools.filesystem.file_tool_utils import get_or_create_path_resolver
from suzent.tools.shell.permissions.evaluator import evaluate_command_policy
from suzent.tools.shell.permissions.policy_models import CommandDecision


@pytest.fixture
def host_resolver(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return get_or_create_path_resolver(
        SimpleNamespace(
            chat_id="chat-1",
            sandbox_enabled=False,
            workspace_root=str(workspace),
            custom_volumes=[],
            path_resolver=None,
        )
    )


def decide(resolver, command, mode="default", rules=None):
    return evaluate_command_policy(
        command,
        resolver=resolver,
        mode_value=mode,
        raw_rules=rules or [],
        default_action="ask",
    ).decision


def test_reaching_outside_the_grants_asks_instead_of_refusing(host_resolver):
    assert decide(host_resolver, "cat /etc/passwd") == CommandDecision.ASK


def test_a_permission_rule_can_authorize_the_folder(host_resolver):
    # Previously unreachable: the path check ran above the rule engine, so no
    # rule could grant access to a directory outside the workspace.
    rules = [{"pattern": "cat /etc/", "match_type": "prefix", "action": "allow"}]
    assert (
        decide(host_resolver, "cat /etc/passwd", rules=rules) == CommandDecision.ALLOW
    )


def test_a_deny_rule_still_wins(host_resolver):
    rules = [{"pattern": "cat /etc/", "match_type": "prefix", "action": "deny"}]
    assert decide(host_resolver, "cat /etc/passwd", rules=rules) == CommandDecision.DENY


def test_full_access_means_what_it_says(host_resolver):
    assert (
        decide(host_resolver, "cat /etc/passwd", mode="full_access")
        == CommandDecision.ALLOW
    )


def test_paths_inside_the_grants_are_not_prompted(host_resolver):
    inside = host_resolver.workspace_root / "notes.txt"
    assert decide(host_resolver, f"cat {inside}") == CommandDecision.ALLOW


def test_catastrophic_targets_stay_unapprovable(host_resolver):
    # The hard deny keeps its position above the rules and the mode.
    rules = [{"pattern": "rm ", "match_type": "prefix", "action": "allow"}]
    assert decide(host_resolver, "rm -rf /", mode="full_access") == CommandDecision.DENY
    assert decide(host_resolver, "rm -rf /etc", rules=rules) == CommandDecision.DENY


def test_the_check_no_longer_splits_cat_from_python(host_resolver):
    # The asymmetry this replaces: one of these was denied outright and the
    # other allowed, which pushed the agent towards the unreviewable route.
    catted = decide(host_resolver, "cat /etc/passwd")
    scripted = decide(host_resolver, "python3 -c \"print(open('/etc/passwd').read())\"")

    assert catted == scripted


def test_sandbox_containment_is_not_negotiable(tmp_path):
    # Unlike the host's advisory check, this one sits above the rules and the
    # mode: neither an allow rule nor Full Access may talk past it.
    resolver = get_or_create_path_resolver(
        SimpleNamespace(
            chat_id="chat-1",
            sandbox_enabled=True,
            workspace_root=str(tmp_path / "workspace"),
            custom_volumes=[],
            path_resolver=None,
        )
    )
    rules = [{"pattern": "cat /mnt/", "match_type": "prefix", "action": "allow"}]
    command = "cat /mnt/not-registered/file"

    assert decide(resolver, command) == CommandDecision.DENY
    assert decide(resolver, command, rules=rules) == CommandDecision.DENY
    assert decide(resolver, command, mode="full_access") == CommandDecision.DENY
