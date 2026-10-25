from __future__ import annotations

import pytest

from suzent.config import CONFIG
from suzent.permissions.context import (
    parse_permission_mode,
    seed_default_permission_mode,
)
from suzent.permissions.models import PermissionMode


@pytest.fixture
def default_mode() -> str:
    return str(getattr(CONFIG, "default_permission_mode", "default") or "default")


def test_seed_empty_config_uses_configured_default(default_mode: str) -> None:
    config: dict = {}
    seed_default_permission_mode(config)
    # A voice chat's empty config must resolve to the user's classifier default,
    # not fall back to "default" (ask) later.
    assert config["permission_mode"] == default_mode


def test_seed_upgrades_explicit_default(default_mode: str) -> None:
    config = {"permission_mode": "default"}
    seed_default_permission_mode(config)
    assert config["permission_mode"] == default_mode


def test_seed_leaves_non_default_modes_untouched() -> None:
    for pinned in ("auto", "full_access", "plan", "accept_edits", "strict_readonly"):
        config = {"permission_mode": pinned}
        seed_default_permission_mode(config)
        assert config["permission_mode"] == pinned


@pytest.mark.parametrize(
    "default",
    ["auto", "full_access", "plan", "strict_readonly", "default"],
)
def test_seed_always_parses_to_a_known_mode(monkeypatch, default: str) -> None:
    import suzent.config as config_module

    monkeypatch.setattr(config_module.CONFIG, "default_permission_mode", default)
    config: dict = {}
    seed_default_permission_mode(config)
    assert parse_permission_mode(config["permission_mode"]) in PermissionMode
