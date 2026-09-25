import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from suzent.llm import ImageGenerator
from suzent.tools.image_edit_tool import ImageEditTool
from suzent.tools.image_generation_tool import ImageGenerationTool
from suzent.tools.image_output import save_images


@pytest.fixture(autouse=True)
def mock_option_validation():
    with patch.object(ImageGenerator, "_validate_options"):
        yield


PNG = b"\x89PNG\r\n\x1a\n" + b"test"


async def test_generation_passes_options_and_returns_all_images() -> None:
    client = SimpleNamespace(
        aimage_generation=AsyncMock(
            return_value=SimpleNamespace(
                data=[
                    SimpleNamespace(url="https://example.com/one.png"),
                    SimpleNamespace(b64_json=base64.b64encode(PNG).decode()),
                ]
            )
        )
    )
    with (
        patch("suzent.llm._litellm", return_value=client),
        patch(
            "suzent.llm._litellm_model_and_kwargs",
            return_value=("model", {"api_key": "test"}),
        ),
    ):
        images = await ImageGenerator("test/model").generate(
            "draw", "1536x1024", quality="high", count=2
        )
    assert len(images) == 2
    client.aimage_generation.assert_awaited_once_with(
        model="model",
        prompt="draw",
        size="1536x1024",
        quality="high",
        n=2,
        drop_params=False,
        api_key="test",
    )


async def test_edit_files_open_during_request_and_closed_on_failure(
    tmp_path: Path,
) -> None:
    paths = [tmp_path / name for name in ("one.png", "two.png", "mask.png")]
    for path in paths:
        path.write_bytes(PNG)
    handles = []

    async def edit(**kwargs: object) -> None:
        handles.extend([*kwargs["image"], kwargs["mask"]])
        assert all(not handle.closed for handle in handles)
        assert "size" not in kwargs and "quality" not in kwargs
        raise RuntimeError("provider rejected mask")

    with (
        patch("suzent.llm._litellm", return_value=SimpleNamespace(aimage_edit=edit)),
        patch("suzent.llm._litellm_model_and_kwargs", return_value=("model", {})),
        pytest.raises(RuntimeError, match="rejected mask"),
    ):
        await ImageGenerator("test/model").edit(
            "edit", [str(p) for p in paths[:2]], mask_path=str(paths[2])
        )
    assert all(handle.closed for handle in handles)


async def test_empty_response_is_error() -> None:
    client = SimpleNamespace(
        aimage_generation=AsyncMock(return_value=SimpleNamespace(data=[]))
    )
    with (
        patch("suzent.llm._litellm", return_value=client),
        patch("suzent.llm._litellm_model_and_kwargs", return_value=("model", {})),
        pytest.raises(ValueError, match="no images"),
    ):
        await ImageGenerator("test/model").generate("draw")


def test_missing_role_does_not_use_provider_default() -> None:
    with patch("suzent.core.role_router.get_role_router") as router:
        router.return_value.get_model_id.return_value = None
        with pytest.raises(ValueError, match="image_edit model configured"):
            ImageGenerator(role="image_edit")


async def test_save_formats_and_unique_paths(tmp_path: Path) -> None:
    jpeg = b"\xff\xd8\xff" + b"test"
    images = [
        "data:application/octet-stream;base64," + base64.b64encode(data).decode()
        for data in [PNG, jpeg]
    ]
    with patch(
        "suzent.tools.image_output.CONFIG",
        SimpleNamespace(workspace_root=str(tmp_path)),
    ):
        paths = await save_images(images, SimpleNamespace(chat_id=None))
        more = await save_images(images, SimpleNamespace(chat_id=None))
    assert Path(paths[0]).suffix == ".png"
    assert Path(paths[1]).suffix == ".jpg"
    assert Path(paths[1]).read_bytes() == jpeg
    assert not set(paths) & set(more)


async def test_generate_tool_keeps_style_and_passes_size() -> None:
    with (
        patch("suzent.tools.image_generation_tool.ImageGenerator") as factory,
        patch(
            "suzent.tools.image_generation_tool.save_images",
            new_callable=AsyncMock,
            return_value=["out.png"],
        ),
    ):
        factory.return_value.generate = AsyncMock(return_value=["image"])
        result = await ImageGenerationTool().forward(
            MagicMock(), "cat", style="ink", size="1536x1024", quality="high"
        )
        assert result.success
        factory.return_value.generate.assert_awaited_once_with(
            "cat\nStyle: ink", size="1536x1024", quality="high", count=1
        )


async def test_edit_validates_paths_before_request(tmp_path: Path) -> None:
    with (
        patch("suzent.tools.image_edit_tool.ImageGenerator") as factory,
        patch("suzent.tools.image_edit_tool.get_or_create_path_resolver") as resolver,
    ):
        resolver.return_value.resolve.return_value = tmp_path / "missing.png"
        result = await ImageEditTool().forward(MagicMock(), "edit", ["missing.png"])
        assert not result.success
        factory.return_value.edit.assert_not_called()


async def test_edit_tool_uses_saved_paths(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(PNG)
    with (
        patch("suzent.tools.image_edit_tool.ImageGenerator") as factory,
        patch("suzent.tools.image_edit_tool.get_or_create_path_resolver") as resolver,
        patch(
            "suzent.tools.image_edit_tool.save_images",
            new_callable=AsyncMock,
            return_value=["new.png"],
        ),
    ):
        resolver.return_value.resolve.return_value = source
        factory.return_value.edit = AsyncMock(return_value=["image"])
        result = await ImageEditTool().forward(
            MagicMock(), "blue background", [str(source)]
        )
        assert result.success
        factory.assert_called_once_with(role="image_edit")
        factory.return_value.edit.assert_awaited_once_with(
            "blue background",
            [str(source)],
            mask_path=None,
            size=None,
            quality=None,
            count=1,
        )
        assert source.read_bytes() == PNG
