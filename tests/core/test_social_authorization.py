"""Authorization is per-platform and matches sender IDs only.

Sender IDs are namespaced per platform, and display names are user-settable and
unverified everywhere, so neither may leak an approval across platforms.
"""

import json

import pytest

from suzent.channels.base import UnifiedMessage
from suzent.core.social_brain import SocialBrain


def _message(platform: str, sender_id: str, sender_name: str = "alice"):
    return UnifiedMessage(
        id="m1",
        content="hi",
        sender_id=sender_id,
        sender_name=sender_name,
        platform=platform,
    )


@pytest.fixture
def brain():
    return SocialBrain(None, platform_allowlists={"telegram": ["111"]})


def test_allows_listed_sender_on_its_own_platform(brain):
    assert brain._is_authorized(_message("telegram", "111")) is True


def test_denies_same_id_on_another_platform(brain):
    """A Telegram ID must not authorize the identical string on Discord."""
    assert brain._is_authorized(_message("discord", "111")) is False


def test_denies_sender_impersonating_an_allowed_id_by_display_name(brain):
    """Display names are not identity — renaming yourself must not grant access."""
    assert brain._is_authorized(_message("telegram", "999", sender_name="111")) is False


def test_denies_platform_with_no_allowlist(brain):
    assert brain._is_authorized(_message("slack", "111")) is False


@pytest.mark.asyncio
async def test_pairing_approval_is_scoped_to_the_requesting_platform(
    tmp_path, monkeypatch
):
    """An approval on one platform must not authorize the sender elsewhere."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "social.json"
    config_path.write_text(
        json.dumps({"telegram": {"enabled": True}, "discord": {"enabled": True}})
    )
    monkeypatch.setattr("suzent.config.PROJECT_DIR", tmp_path)

    brain = SocialBrain(None, platform_allowlists={})
    await brain._persist_approved_user("555", "telegram")

    saved = json.loads(config_path.read_text())
    assert saved["telegram"]["allowed_users"] == ["555"]
    assert "allowed_users" not in saved["discord"]
    assert "allowed_users" not in saved
