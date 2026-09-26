import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from suzent.core.role_router import RoleRouter
from suzent.routes import config_routes


@pytest.fixture
def router():
    value = RoleRouter()
    value.set_role("primary", ["openai/chat"])
    value.set_role("tts", ["openai/tts-1"])
    return value


async def test_voice_page_reads_and_updates_same_tts_role(router):
    with (
        patch("suzent.core.role_router.get_role_router", return_value=router),
        patch.object(router, "save_to_db") as persist,
        patch.object(
            config_routes, "_load_local_config_file", return_value={"other": True}
        ),
        patch.object(config_routes, "_save_local_config_file") as save,
        patch.object(config_routes.CONFIG, "voice_settings", {}),
    ):
        read = await config_routes.voice_settings(SimpleNamespace(method="GET"))
        assert json.loads(read.body)["tts_models"] == ["openai/tts-1"]
        payload = {
            "engine": "api",
            "voice": "Zephyr",
            "tts_models": ["gemini/gemini-2.5-flash-preview-tts"],
        }
        result = await config_routes.voice_settings(
            SimpleNamespace(method="POST", json=AsyncMock(return_value=payload))
        )
        assert result.status_code == 200
        assert router.get_model_id("tts") == payload["tts_models"][0]
        assert router.get_model_id("primary") == "openai/chat"
        assert config_routes.CONFIG.voice_settings["voice"] == "Zephyr"
        assert "tts_models" not in config_routes.CONFIG.voice_settings
        assert save.call_args.args[0]["other"] is True
        persist.assert_called_once()


async def test_legacy_settings_update_preserves_model_and_invalid_model_does_not_write(
    router,
):
    with (
        patch("suzent.core.role_router.get_role_router", return_value=router),
        patch.object(router, "save_to_db") as persist,
        patch.object(config_routes, "_load_local_config_file", return_value={}),
        patch.object(config_routes, "_save_local_config_file") as save,
        patch.object(config_routes.CONFIG, "voice_settings", {}),
    ):
        request = SimpleNamespace(
            method="POST", json=AsyncMock(return_value={"speed": 1.1})
        )
        assert (await config_routes.voice_settings(request)).status_code == 200
        assert router.get_model_id("tts") == "openai/tts-1"
        persist.assert_not_called()
        save.reset_mock()
        request.json = AsyncMock(return_value={"tts_models": ["invalid"]})
        assert (await config_routes.voice_settings(request)).status_code == 400
        save.assert_not_called()
