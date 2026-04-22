import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from suzent.tools.base import ToolErrorCode
from suzent.tools.image_vision_tool import ImageVisionTool


@pytest.fixture
def mock_ctx():
    class MockSandbox:
        def __init__(self, workspace):
            self.workspace = workspace

    class MockDeps:
        def __init__(self):
            self.sandbox = MockSandbox(Path("/tmp/mock_workspace"))
            self.file_tracker = None

    ctx = MagicMock()
    ctx.deps = MockDeps()
    return ctx


@pytest.mark.asyncio
async def test_image_vision_file_not_found(mock_ctx):
    mock_path = MagicMock()
    mock_path.exists.return_value = False

    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = mock_path

    with patch(
        "suzent.tools.image_vision_tool.get_or_create_path_resolver",
        return_value=mock_resolver,
    ):
        tool = ImageVisionTool()
        result = await tool.forward(mock_ctx, "does_not_exist.jpg", "What is this?")
        assert not result.success
        assert result.error_code == ToolErrorCode.FILE_NOT_FOUND


@pytest.mark.asyncio
@patch("suzent.tools.image_vision_tool.litellm.acompletion", new_callable=AsyncMock)
@patch("builtins.open", new_callable=MagicMock)
async def test_image_vision_success(mock_open, mock_acompletion, mock_ctx):
    mock_stat = MagicMock()
    mock_stat.st_size = 1024

    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path.is_file.return_value = True
    mock_path.stat.return_value = mock_stat
    mock_path.suffix = ".png"
    mock_path.name = "test.png"

    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = mock_path

    # Mock open and read
    mock_file = MagicMock()
    mock_file.read.return_value = b"fake_image_data"
    mock_open.return_value.__enter__.return_value = mock_file

    # Mock litellm response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "A beautiful cyber tentacle."
    mock_acompletion.return_value = mock_response

    with patch(
        "suzent.tools.image_vision_tool.get_or_create_path_resolver",
        return_value=mock_resolver,
    ):
        # Mock CONFIG.default_model issue by setting model directly
        with patch("suzent.tools.image_vision_tool.getattr", return_value="gpt-4o"):
            tool = ImageVisionTool()
            result = await tool.forward(mock_ctx, "test.png", "Describe")

            assert result.success
            assert "cyber tentacle" in result.message


@pytest.mark.asyncio
async def test_image_vision_no_model(mock_ctx):
    mock_stat = MagicMock()
    mock_stat.st_size = 1024

    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path.is_file.return_value = True
    mock_path.stat.return_value = mock_stat

    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = mock_path

    # Force getattr to return None for model lookup
    with patch(
        "suzent.tools.image_vision_tool.get_or_create_path_resolver",
        return_value=mock_resolver,
    ):
        with patch("suzent.tools.image_vision_tool.getattr", return_value=None):
            with patch("builtins.open", new_callable=MagicMock) as mock_open:
                mock_file = MagicMock()
                mock_file.read.return_value = b"fake_image_data"
                mock_open.return_value.__enter__.return_value = mock_file

                tool = ImageVisionTool()
                result = await tool.forward(mock_ctx, "huge.jpg", "Describe")

                assert not result.success
                assert result.error_code == ToolErrorCode.EXECUTION_FAILED
                assert "No vision_model" in result.message


@pytest.mark.asyncio
async def test_image_vision_too_large(mock_ctx):
    mock_stat = MagicMock()
    mock_stat.st_size = 50 * 1024 * 1024  # 50MB

    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path.is_file.return_value = True
    mock_path.stat.return_value = mock_stat

    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = mock_path

    with patch(
        "suzent.tools.image_vision_tool.get_or_create_path_resolver",
        return_value=mock_resolver,
    ):
        tool = ImageVisionTool()
        result = await tool.forward(mock_ctx, "huge.jpg", "Describe")

        assert not result.success
        assert result.error_code == ToolErrorCode.FILE_TOO_LARGE
