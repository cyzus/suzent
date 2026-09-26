from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from suzent.tools.creative import video_tool as video
from suzent.tools.creative import voice_tool as voice
from suzent.voice.settings import VoiceSettings


@pytest.fixture
def context(tmp_path):
    return SimpleNamespace(
        deps=SimpleNamespace(
            chat_id=None,
            workspace_root=str(tmp_path),
            interaction_profile="interactive",
            social_context={},
        )
    )


async def test_video_reference_recovery_and_cached_download(context, tmp_path):
    image = tmp_path / "reference.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nreference")
    client = SimpleNamespace(
        avideo_generation=AsyncMock(
            return_value=SimpleNamespace(id="provider-job", status="queued")
        ),
        avideo_status=AsyncMock(
            return_value=SimpleNamespace(status="completed", progress=100)
        ),
        avideo_content=AsyncMock(return_value=b"video"),
    )
    with (
        patch.object(video, "_directory", return_value=tmp_path),
        patch.object(
            video,
            "get_role_router",
            return_value=SimpleNamespace(get_model_id=lambda _: "gemini/veo"),
        ),
        patch.object(
            video,
            "get_or_create_path_resolver",
            return_value=SimpleNamespace(resolve=lambda _: image),
        ),
        patch.object(video, "_litellm", return_value=client),
        patch.object(
            video,
            "_litellm_model_and_kwargs",
            return_value=("gemini/veo", {"api_key": "test"}),
        ),
    ):
        submitted = await video.VideoGenerationTool().forward(
            context, "moving clouds", image_path="reference.png", seconds=8
        )
        assert submitted.success
        args = client.avideo_generation.call_args.kwargs
        assert args["input_reference"].closed
        assert args["seconds"] == "8"
        job_id = submitted.metadata["job_id"]
        result = await video.VideoStatusTool().forward(context, job_id)
        assert result.success and result.metadata["saved_paths"]
        # A fresh tool instance reuses the durable result without another API call.
        assert (await video.VideoStatusTool().forward(context, job_id)).success
        assert client.avideo_content.await_count == 1
        assert client.avideo_status.call_args.kwargs["api_key"] == "test"


async def test_video_download_failure_can_retry_without_generation(context, tmp_path):
    job_id = "a" * 32
    (tmp_path / f"{job_id}.json").write_text(
        video.VideoJob(
            model="openai/sora", provider_id="remote", chat_id=None
        ).model_dump_json()
    )
    client = SimpleNamespace(
        avideo_status=AsyncMock(return_value=SimpleNamespace(status="completed")),
        avideo_content=AsyncMock(side_effect=[RuntimeError("network"), b"video"]),
    )
    with (
        patch.object(video, "_directory", return_value=tmp_path),
        patch.object(video, "_litellm", return_value=client),
        patch.object(
            video, "_litellm_model_and_kwargs", return_value=("openai/sora", {})
        ),
    ):
        assert not (await video.VideoStatusTool().forward(context, job_id)).success
        assert (await video.VideoStatusTool().forward(context, job_id)).success


async def test_video_job_is_scoped_to_chat(context, tmp_path):
    job_id = "a" * 32
    (tmp_path / f"{job_id}.json").write_text(
        video.VideoJob(
            model="openai/sora", provider_id="remote", chat_id="another"
        ).model_dump_json()
    )
    with (
        patch.object(video, "_directory", return_value=tmp_path),
        patch.object(video, "_litellm") as client,
    ):
        assert not (await video.VideoStatusTool().forward(context, job_id)).success
        assert not (await video.VideoStatusTool().forward(context, "../escape")).success
        client.assert_not_called()


async def test_system_speech_needs_no_model_or_audio_device(context):
    with (
        patch.object(voice, "get_voice_settings", return_value=VoiceSettings()),
        patch.object(voice, "_litellm") as client,
    ):
        result = await voice.SpeakTool().forward(
            context, "你好", speed=1.5, pitch=0.8, language="zh-CN"
        )
        assert result.success
        assert result.metadata["speed"] == 1.5
        assert result.metadata["engine"] == "system"
        client.assert_not_called()


@pytest.mark.parametrize(
    "deps", [{"interaction_profile": "headless"}, {"social_context": {"platform": "x"}}]
)
async def test_system_speech_rejected_without_desktop_client(context, deps):
    vars(context.deps).update(deps)
    with patch.object(voice, "get_voice_settings", return_value=VoiceSettings()):
        result = await voice.SpeakTool().forward(context, "hello")
    assert not result.success
    assert "desktop chat" in result.message


@pytest.mark.parametrize(
    "model,expected_format",
    [("openai/gpt-4o-mini-tts", "mp3")],
)
async def test_api_speech_overrides_and_saves(
    context, tmp_path, model, expected_format
):
    client = SimpleNamespace(aspeech=AsyncMock(return_value=b"audio"))
    with (
        patch.object(
            voice, "get_voice_settings", return_value=VoiceSettings(engine="api")
        ),
        patch.object(
            voice,
            "get_role_router",
            return_value=SimpleNamespace(get_model_id=lambda _: model),
        ),
        patch.object(
            voice,
            "_litellm_model_and_kwargs",
            return_value=(model, {"api_key": "test"}),
        ),
        patch.object(voice, "_litellm", return_value=client),
        patch.object(voice.CONFIG, "workspace_root", str(tmp_path)),
    ):
        result = await voice.SpeakTool().forward(
            context, "hello", voice="chosen", prompt="Calm"
        )
        assert result.success
        assert result.metadata["saved_paths"][0].endswith(expected_format)
        args = client.aspeech.call_args.kwargs
        assert args["voice"] == "chosen"
        assert args["api_key"] == "test"
        assert (
            (args.get("instructions") == "Calm")
            if model.startswith("openai/")
            else ("Calm" in args["input"])
        )
        if model.startswith("gemini/"):
            assert not (
                await voice.SpeakTool().forward(context, "hello", speed=2)
            ).success
            assert client.aspeech.await_count == 1


async def test_video_failure_is_terminal(context, tmp_path):
    job_id = "b" * 32
    (tmp_path / f"{job_id}.json").write_text(
        video.VideoJob(
            model="openai/sora", provider_id="remote", chat_id=None
        ).model_dump_json()
    )
    client = SimpleNamespace(
        avideo_status=AsyncMock(
            return_value=SimpleNamespace(status="failed", error="rejected")
        ),
        avideo_content=AsyncMock(),
    )
    with (
        patch.object(video, "_directory", return_value=tmp_path),
        patch.object(video, "_litellm", return_value=client),
        patch.object(
            video, "_litellm_model_and_kwargs", return_value=("openai/sora", {})
        ),
    ):
        assert not (await video.VideoStatusTool().forward(context, job_id)).success
        assert not (await video.VideoStatusTool().forward(context, job_id)).success
        assert client.avideo_status.await_count == 1
        client.avideo_content.assert_not_called()


async def test_voice_settings_reloaded_between_calls(context):
    with patch.object(
        voice,
        "get_voice_settings",
        side_effect=[VoiceSettings(speed=0.8), VoiceSettings(speed=1.8)],
    ):
        tool = voice.SpeakTool()
        assert (await tool.forward(context, "hello")).metadata["speed"] == 0.8
        assert (await tool.forward(context, "hello")).metadata["speed"] == 1.8
        assert not (await tool.forward(context, " ")).success


def test_video_capability_and_role():
    from suzent.core.model_registry import ModelCapabilities, _LITELLM_MODE_MAP
    from suzent.core.role_router import RoleRouter

    assert _LITELLM_MODE_MAP["video_generation"] == "video_generation"
    assert not ModelCapabilities(mode="video_generation").is_stub
    router = RoleRouter()
    router.set_role("primary", ["openai/chat"])
    assert router.get_model_id("video_generation") is None


async def test_voice_settings_validation_and_persistence():
    from suzent.routes import config_routes

    request = SimpleNamespace(method="POST", json=AsyncMock(return_value={"speed": 10}))
    with patch.object(config_routes, "_save_local_config_file") as save:
        assert (await config_routes.voice_settings(request)).status_code == 400
        save.assert_not_called()
    request.json = AsyncMock(return_value={"engine": "system", "speed": 1.2})
    with (
        patch.object(
            config_routes, "_load_local_config_file", return_value={"preserved": True}
        ),
        patch.object(config_routes, "_save_local_config_file") as save,
        patch.object(config_routes.CONFIG, "voice_settings", {}),
    ):
        assert (await config_routes.voice_settings(request)).status_code == 200
        assert save.call_args.args[0]["preserved"] is True
        assert config_routes.CONFIG.voice_settings["speed"] == 1.2


async def test_speech_autoplay_setting_and_stable_result_id(context):
    with patch.object(
        voice, "get_voice_settings", return_value=VoiceSettings(autoplay=False)
    ):
        first = await voice.SpeakTool().forward(context, "hello")
        second = await voice.SpeakTool().forward(context, "hello")
        assert first.metadata["autoplay"] is False
        assert first.metadata["speech_id"] != second.metadata["speech_id"]
    assert VoiceSettings().autoplay is True


@pytest.mark.parametrize("provider", ["gemini", "vertex_ai"])
@pytest.mark.parametrize("audio_format", ["auto", "wav"])
async def test_gemini_direct_audio_preserves_credentials_and_wav(
    context, tmp_path, provider, audio_format
):
    import base64
    import io
    import wave
    from pathlib import Path

    import litellm

    model = f"{provider}/gemini-2.5-flash-preview-tts"
    pcm = b"\x00\x00" * 240

    async def completion(**request):
        assert request["model"] == model
        assert request["api_key"] == "configured-test-key"
        assert request["api_base"] == "https://example.invalid/gemini"
        assert "response_format" not in request
        assert request["audio"]["voice"] == "Kore"
        assert request["modalities"] == ["audio"]
        assert "Calm" in request["messages"][0]["content"]
        return litellm.ModelResponse(
            model=model,
            choices=[
                {
                    "message": {
                        "role": "assistant",
                        "audio": {
                            "id": "audio",
                            "data": base64.b64encode(pcm).decode(),
                            "expires_at": 0,
                            "transcript": "hello",
                        },
                    }
                }
            ],
        )

    with (
        patch.object(
            voice,
            "get_voice_settings",
            return_value=VoiceSettings(engine="api", response_format=audio_format),
        ),
        patch.object(
            voice,
            "get_role_router",
            return_value=SimpleNamespace(get_model_id=lambda _: model),
        ),
        patch.object(
            voice,
            "_litellm_model_and_kwargs",
            return_value=(
                model,
                {
                    "api_key": "configured-test-key",
                    "api_base": "https://example.invalid/gemini",
                },
            ),
        ),
        patch.object(
            voice, "_litellm", return_value=SimpleNamespace(acompletion=completion)
        ),
        patch.object(voice.CONFIG, "workspace_root", str(tmp_path)),
    ):
        result = await voice.SpeakTool().forward(context, "hello", prompt="Calm")
        assert result.success, result.message
        assert result.metadata["response_format"] == "wav"
        path = Path(result.metadata["saved_paths"][0])
        assert path.suffix == ".wav"
        with wave.open(io.BytesIO(path.read_bytes()), "rb") as audio:
            assert audio.getframerate() == 24000
            assert audio.readframes(audio.getnframes()) == pcm


async def test_gemini_rejects_unsupported_speed_before_provider_call(context):
    with (
        patch.object(
            voice, "get_voice_settings", return_value=VoiceSettings(engine="api")
        ),
        patch.object(
            voice,
            "get_role_router",
            return_value=SimpleNamespace(
                get_model_id=lambda _: "gemini/gemini-2.5-flash-preview-tts"
            ),
        ),
        patch.object(
            voice,
            "_litellm_model_and_kwargs",
            return_value=("gemini/gemini-2.5-flash-preview-tts", {}),
        ),
        patch.object(voice, "_litellm") as client,
    ):
        assert not (await voice.SpeakTool().forward(context, "hello", speed=2)).success
        client.assert_not_called()
