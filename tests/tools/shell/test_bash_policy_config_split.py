from pathlib import Path

from suzent.permissions.loader import (
    load_permission_overrides,
    persist_global_command_rule,
)


class _DummyLogger:
    def debug(self, *_args, **_kwargs):
        return None


def test_loads_nested_permissions_file(tmp_path: Path):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "permissions.yaml").write_text(
        """
PERMISSIONS:
  tools:
    bash_execute:
      enabled: true
      mode: strict_readonly
      default_action: deny
      command_rules:
        - pattern: "git status"
          match_type: exact
          action: allow
""".strip(),
        encoding="utf-8",
    )

    loaded = load_permission_overrides(tmp_path, _DummyLogger())

    assert "permission_policies" in loaded
    assert loaded["permission_policies"]["bash_execute"]["enabled"] is True
    assert loaded["permission_policies"]["bash_execute"]["mode"] == "strict_readonly"
    assert loaded["permission_policies"]["bash_execute"]["default_action"] == "deny"
    assert len(loaded["permission_policies"]["bash_execute"]["command_rules"]) == 1


def test_user_file_overrides_example(tmp_path: Path):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "permissions.example.yaml").write_text(
        """
tools:
  bash_execute:
    enabled: false
    mode: full_approval
""".strip(),
        encoding="utf-8",
    )
    (cfg_dir / "permissions.yaml").write_text(
        """
tools:
  bash_execute:
    enabled: true
    mode: accept_edits
""".strip(),
        encoding="utf-8",
    )

    loaded = load_permission_overrides(tmp_path, _DummyLogger())

    assert loaded["permission_policies"]["bash_execute"]["enabled"] is True
    assert loaded["permission_policies"]["bash_execute"]["mode"] == "accept_edits"


def test_persist_global_command_rule_creates_permissions_file(tmp_path: Path):
    changed = persist_global_command_rule(
        tmp_path,
        _DummyLogger(),
        tool_name="bash_execute",
        command_pattern="git status",
        action="allow",
    )

    assert changed is True
    user_path = tmp_path / "config" / "permissions.yaml"
    assert user_path.exists()

    loaded = load_permission_overrides(tmp_path, _DummyLogger())
    rules = loaded["permission_policies"]["bash_execute"]["command_rules"]
    assert len(rules) == 1
    assert rules[0]["pattern"] == "git status"
    assert rules[0]["match_type"] == "exact"
    assert rules[0]["action"] == "allow"


def test_persist_global_command_rule_updates_existing_without_duplicates(
    tmp_path: Path,
):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "permissions.yaml").write_text(
        """
PERMISSIONS:
  tools:
    bash_execute:
      enabled: true
      mode: accept_edits
      default_action: ask
      command_rules:
        - pattern: "git status"
          match_type: exact
          action: allow
""".strip(),
        encoding="utf-8",
    )

    changed = persist_global_command_rule(
        tmp_path,
        _DummyLogger(),
        tool_name="bash_execute",
        command_pattern="git status",
        action="deny",
    )

    assert changed is True
    loaded = load_permission_overrides(tmp_path, _DummyLogger())
    rules = loaded["permission_policies"]["bash_execute"]["command_rules"]
    assert len(rules) == 1
    assert rules[0]["action"] == "deny"
