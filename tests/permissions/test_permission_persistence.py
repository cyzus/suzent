from __future__ import annotations

import json
from pathlib import Path

import yaml

from suzent.permissions.audit import record_permission_audit, sanitize_args
from suzent.permissions.loader import (
    delete_global_permission_rule,
    load_permission_overrides,
    persist_global_permission_rule,
)
from suzent.permissions.models import PermissionRule


class Logger:
    def debug(self, *_args) -> None:
        pass


def test_global_permission_rule_round_trip(tmp_path: Path) -> None:
    config_dir = tmp_path / "user"
    rule = PermissionRule.model_validate(
        {
            "id": "rule-1",
            "tool": "bash_execute",
            "behavior": "allow",
            "matcher": {
                "type": "exact_input",
                "value": {"command": "npm test"},
            },
            "source": "global",
        }
    )

    assert persist_global_permission_rule(
        tmp_path,
        Logger(),
        rule,
        user_config_dir=config_dir,
    )
    loaded = load_permission_overrides(
        tmp_path,
        Logger(),
        user_config_dir=config_dir,
    )
    assert loaded["permission_rules"][0]["id"] == "rule-1"
    assert loaded["permission_rules"][0]["source"] == "global"

    assert delete_global_permission_rule(
        tmp_path,
        Logger(),
        "rule-1",
        user_config_dir=config_dir,
    )
    document = yaml.safe_load((config_dir / "permissions.yaml").read_text())
    assert document["permissions"]["rules"] == []


async def test_permission_audit_redacts_sensitive_values(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import suzent.config

    monkeypatch.setattr(suzent.config, "USER_CONFIG_DIR", tmp_path)
    await record_permission_audit(
        chat_id="chat-1",
        tool_call_id="call-1",
        tool_name="deploy",
        args={
            "api_key": "secret-value",
            "authorization": "Bearer secret",
            "message": "safe",
            "headers": {"Authorization": "Bearer nested-secret"},
            "content": "token=inline-secret npm test",
        },
        decision="deny",
        reason="test",
        reason_code="test",
        mode="default",
        feedback="Use staging",
    )

    event = json.loads((tmp_path / "permission-audit.jsonl").read_text())
    assert event["args"]["api_key"] == "[redacted]"
    assert event["args"]["authorization"] == "[redacted]"
    assert event["args"]["message"] == "safe"
    assert event["args"]["headers"]["Authorization"] == "[redacted]"
    assert event["args"]["content"] == "token=[redacted] npm test"
    assert event["feedback"] == "Use staging"


def test_sanitize_args_truncates_large_values() -> None:
    sanitized = sanitize_args({"content": "x" * 400})
    assert len(sanitized["content"]) == 301
    assert sanitized["content"].endswith("…")
