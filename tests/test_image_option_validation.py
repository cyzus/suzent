import pytest

from suzent.llm import ImageGenerator


def test_image_options_use_provider_capabilities() -> None:
    generator = ImageGenerator("openai/gpt-image-1")
    generator._validate_options(
        "openai/gpt-image-1",
        {"size": "1536x1024", "quality": "high", "n": 1, "mask": object()},
        editing=True,
    )
    with pytest.raises(ValueError, match="Unsupported image parameters"):
        generator._validate_options(
            "openai/gpt-image-1", {"nonexistent_option": True}, editing=True
        )
    generator._validate_options(
        "openai/gpt-image-1",
        {"size": "1536x1024", "quality": "high", "n": 1},
        editing=False,
    )


async def test_gemini_edit_omits_default_count(tmp_path) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    path = tmp_path / "source.png"
    path.write_bytes(b"input")
    call = AsyncMock(
        return_value=SimpleNamespace(
            data=[SimpleNamespace(url="https://example.com/image.png")]
        )
    )
    with (
        patch("suzent.llm._litellm", return_value=SimpleNamespace(aimage_edit=call)),
        patch(
            "suzent.llm._litellm_model_and_kwargs",
            return_value=("gemini/gemini-2.5-flash-image", {}),
        ),
    ):
        generator = ImageGenerator("gemini/gemini-2.5-flash-image")
        await generator.edit("edit", [str(path)])
        assert "n" not in call.call_args.kwargs
        assert call.call_args.kwargs["image"].closed
        with pytest.raises(ValueError, match="Unsupported image parameters"):
            await generator.edit("edit", [str(path)], count=2)
        assert call.await_count == 1


async def test_xai_generation_uses_compatible_fallback() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    call = AsyncMock(
        return_value=SimpleNamespace(
            data=[SimpleNamespace(url="https://example.com/image.png")]
        )
    )
    with (
        patch(
            "suzent.llm._litellm", return_value=SimpleNamespace(aimage_generation=call)
        ),
        patch(
            "suzent.llm._litellm_model_and_kwargs",
            return_value=("xai/grok-imagine-image", {}),
        ),
    ):
        generator = ImageGenerator("xai/grok-imagine-image")
        await generator.generate("draw")
        await generator.generate("draw", size="1024x1024", count=2)
        assert call.await_count == 2
        assert call.call_args.kwargs["n"] == 2
        with pytest.raises(ValueError, match="Unsupported image parameters"):
            generator._validate_options(
                "xai/grok-imagine-image", {"invalid": True}, editing=False
            )


@pytest.mark.parametrize("editing", [False, True])
async def test_gemini_quality_degrades_without_dropping_size(editing: bool) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    model = "gemini/gemini-3.1-flash-image-preview"
    call = AsyncMock(
        return_value=SimpleNamespace(
            data=[SimpleNamespace(url="https://example.com/image.png")]
        )
    )
    with (
        patch(
            "suzent.llm._litellm",
            return_value=SimpleNamespace(aimage_generation=call, aimage_edit=call),
        ),
        patch("suzent.llm._litellm_model_and_kwargs", return_value=(model, {})),
    ):
        generator = ImageGenerator(model)
        await generator._request(
            "draw", "1024x1024", "high", 1, **({"image": b"image"} if editing else {})
        )
        assert "quality" not in call.call_args.kwargs
        assert call.call_args.kwargs["size"] == "1024x1024"
        assert generator.dropped_params == ["quality"]
        await generator._request("draw", None, None, 1)
        assert generator.dropped_params == []
        with pytest.raises(ValueError, match="mask"):
            generator._validate_options(
                model, {"mask": b"mask", "quality": "high"}, editing=True
            )
