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
    tool = ImageVisionTool()
    result = await tool.forward(mock_ctx, "does_not_exist.jpg", "What is this?")
    assert not result.success
    assert result.error_code == ToolErrorCode.FILE_NOT_FOUND


@pytest.mark.asyncio
@patch("suzent.tools.image_vision_tool.litellm.acompletion", new_callable=AsyncMock)
@patch("suzent.tools.image_vision_tool.Path.exists", return_value=True)
@patch("suzent.tools.image_vision_tool.Path.is_file", return_value=True)
@patch("suzent.tools.image_vision_tool.Path.stat")
@patch("builtins.open", new_callable=MagicMock)
async def test_image_vision_success(
    mock_open, mock_stat, mock_is_file, mock_exists, mock_acompletion, mock_ctx
):
    # Mock file stat to pass size check
    mock_stat.return_value.st_size = 1024

    # Mock open and read
    mock_file = MagicMock()
    mock_file.read.return_value = b"fake_image_data"
    mock_open.return_value.__enter__.return_value = mock_file

    # Mock litellm response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "A beautiful cyber tentacle."
    mock_acompletion.return_value = mock_response

    tool = ImageVisionTool()
    result = await tool.forward(mock_ctx, "test.png", "Describe")

    assert result.success
    assert "cyber tentacle" in result.message

    # Verify acompletion was called with correct mime type in base64 string
    called_kwargs = mock_acompletion.call_args.kwargs
    assert "messages" in called_kwargs
    content = called_kwargs["messages"][0]["content"]
    image_url = content[1]["image_url"]["url"]
    assert "image/png" in image_url


@pytest.mark.asyncio
@patch("suzent.tools.image_vision_tool.Path.exists", return_value=True)
@patch("suzent.tools.image_vision_tool.Path.is_file", return_value=True)
@patch("suzent.tools.image_vision_tool.Path.stat")
async def test_image_vision_too_large(mock_stat, mock_is_file, mock_exists, mock_ctx):
    mock_stat.return_value.st_size = 50 * 1024 * 1024  # 50MB

    tool = ImageVisionTool()
    result = await tool.forward(mock_ctx, "huge.jpg", "Describe")

    assert not result.success
    assert result.error_code == ToolErrorCode.FILE_TOO_LARGE
