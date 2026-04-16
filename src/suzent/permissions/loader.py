from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import PermissionsConfig, ToolPermissionPolicy


def normalize_keys(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            continue
        normalized = key.strip().lower().replace("-", "_").replace(" ", "_")
        out[normalized] = value
    return out


def _read_config_file(path: Path, logger) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        pass

    try:
        import json

        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.debug("Failed to parse permissions config {}: {}", path, exc)
        return {}


def _extract_permissions_payload(raw: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_keys(raw)
    if "permissions" in normalized and isinstance(normalized["permissions"], dict):
        return normalize_keys(normalized["permissions"])
    return normalized


def load_permission_overrides(project_dir: Path, logger) -> dict[str, Any]:
    """Load generic permissions settings from dedicated config files.

    Load order: permissions.example.yaml -> permissions.yaml
    User file overrides example defaults.
    """
    cfg_dir = project_dir / "config"
    example_path = cfg_dir / "permissions.example.yaml"
    user_path = cfg_dir / "permissions.yaml"

    merged_tools: dict[str, dict[str, Any]] = {}
    for path in (example_path, user_path):
        if not path.exists():
            continue

        raw = _read_config_file(path, logger)
        if not isinstance(raw, dict):
            continue

        payload = _extract_permissions_payload(raw)
        tools_raw = payload.get("tools", {})
        if not isinstance(tools_raw, dict):
            continue

        tools_validated: dict[str, ToolPermissionPolicy] = {}
        for tool_name, tool_cfg in tools_raw.items():
            if not isinstance(tool_cfg, dict):
                continue
            tools_validated[str(tool_name)] = ToolPermissionPolicy.model_validate(
                normalize_keys(tool_cfg)
            )

        cfg = PermissionsConfig(tools=tools_validated)
        merged_tools.update(
            {k: v.model_dump(mode="json") for k, v in cfg.tools.items()}
        )

    return {"permission_policies": merged_tools}


def _load_permissions_user_file(path: Path, logger) -> tuple[dict[str, Any], bool]:
    """Load user permissions file and return (document, has_permissions_wrapper)."""
    if not path.exists():
        return {}, True

    raw = _read_config_file(path, logger)
    if not isinstance(raw, dict):
        return {}, True

    if isinstance(raw.get("PERMISSIONS"), dict):
        return raw, True
    if isinstance(raw.get("permissions"), dict):
        return raw, True
    return raw, False


def persist_project_command_rule(
    project_dir: Path,
    logger,
    *,
    tool_name: str,
    command_pattern: str,
    action: str,
    match_type: str = "exact",
) -> bool:
    """Persist a command policy rule to config/permissions.yaml.

    Returns True if the permissions file was changed.
    """
    cleaned_tool = (tool_name or "").strip()
    cleaned_pattern = (command_pattern or "").strip()
    cleaned_action = (action or "").strip().lower()
    cleaned_match = (match_type or "").strip().lower()

    if not cleaned_tool or not cleaned_pattern:
        return False
    if cleaned_action not in {"allow", "ask", "deny"}:
        raise ValueError(f"Unsupported action: {action}")
    if cleaned_match not in {"exact", "prefix"}:
        raise ValueError(f"Unsupported match_type: {match_type}")

    cfg_dir = project_dir / "config"
    user_path = cfg_dir / "permissions.yaml"

    document, has_wrapper = _load_permissions_user_file(user_path, logger)

    if has_wrapper:
        wrapper_key = "PERMISSIONS" if "PERMISSIONS" in document else "permissions"
        if wrapper_key not in document or not isinstance(
            document.get(wrapper_key), dict
        ):
            document[wrapper_key] = {}
        payload = document[wrapper_key]
    else:
        payload = document

    tools = payload.get("tools")
    if not isinstance(tools, dict):
        tools = {}
        payload["tools"] = tools

    tool_cfg = tools.get(cleaned_tool)
    if not isinstance(tool_cfg, dict):
        tool_cfg = {}
        tools[cleaned_tool] = tool_cfg

    tool_cfg["enabled"] = True
    tool_cfg.setdefault("mode", "accept_edits")
    tool_cfg.setdefault("default_action", "ask")

    rules = tool_cfg.get("command_rules")
    if not isinstance(rules, list):
        rules = []

    updated = False
    replaced = False
    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue
        if (
            str(rule.get("pattern", "")).strip() == cleaned_pattern
            and str(rule.get("match_type", "")).strip().lower() == cleaned_match
        ):
            new_rule = {
                "pattern": cleaned_pattern,
                "match_type": cleaned_match,
                "action": cleaned_action,
            }
            if rule != new_rule:
                rules[idx] = new_rule
                updated = True
            replaced = True
            break

    if not replaced:
        rules.append(
            {
                "pattern": cleaned_pattern,
                "match_type": cleaned_match,
                "action": cleaned_action,
            }
        )
        updated = True

    tool_cfg["command_rules"] = rules

    if not updated and user_path.exists():
        return False

    cfg_dir.mkdir(parents=True, exist_ok=True)
    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "PyYAML is required to persist project permission rules"
        ) from exc

    with user_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(document, fh, sort_keys=False, allow_unicode=False)

    return True
