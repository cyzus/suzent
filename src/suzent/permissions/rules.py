from __future__ import annotations

from typing import Any, Iterable

from suzent.permissions.models import CommandDecision, PermissionRule
from suzent.tools.shell.permissions.command_parser import parse_command


def _matches_command_prefix(command: str, prefix: str) -> bool:
    command_context = parse_command(command)
    prefix_context = parse_command(prefix)
    if (
        not command_context.base_command
        or not prefix_context.base_command
        or command_context.has_control_operators
        or prefix_context.has_control_operators
    ):
        return False

    command_tokens = [command_context.base_command, *command_context.args]
    prefix_tokens = [prefix_context.base_command, *prefix_context.args]
    return command_tokens[: len(prefix_tokens)] == prefix_tokens


def match_rule(
    rule: PermissionRule,
    tool_name: str,
    args: dict[str, Any],
) -> bool:
    if rule.tool not in {tool_name, "*"}:
        return False
    matcher = rule.matcher
    if matcher.type == "all":
        return True
    if matcher.type == "exact_input":
        expected = matcher.value if isinstance(matcher.value, dict) else {}
        if "command" in expected:
            actual = args.get("content") or args.get("command")
            return str(actual or "").strip() == str(expected["command"]).strip()
        return all(args.get(key) == value for key, value in expected.items())
    if matcher.type == "command_prefix":
        command = str(args.get("content") or args.get("command") or "").strip()
        prefix = str(matcher.value or "").strip()
        return _matches_command_prefix(command, prefix)
    if matcher.type == "path_prefix":
        path = str(args.get("file_path") or args.get("path") or "").replace("\\", "/")
        prefix = str(matcher.value or "").replace("\\", "/").rstrip("/")
        return bool(prefix) and (path == prefix or path.startswith(prefix + "/"))
    if matcher.type == "destination":
        destination = (
            args.get("recipient")
            or args.get("channel")
            or args.get("destination")
            or args.get("repo")
        )
        return str(destination or "") == str(matcher.value or "")
    return False


def find_rule(
    rules: Iterable[PermissionRule],
    tool_name: str,
    args: dict[str, Any],
    behavior: CommandDecision,
) -> PermissionRule | None:
    matching = [
        rule
        for rule in rules
        if rule.behavior == behavior and match_rule(rule, tool_name, args)
    ]
    if not matching:
        return None
    specificity = {
        "exact_input": 5,
        "destination": 4,
        "path_prefix": 3,
        "command_prefix": 2,
        "all": 1,
    }
    return max(matching, key=lambda rule: specificity[rule.matcher.type])


def parse_rules(raw_rules: Any) -> list[PermissionRule]:
    if not isinstance(raw_rules, list):
        return []
    parsed: list[PermissionRule] = []
    for raw in raw_rules:
        if not isinstance(raw, dict):
            continue
        try:
            parsed.append(PermissionRule.model_validate(raw))
        except Exception:
            continue
    return parsed
