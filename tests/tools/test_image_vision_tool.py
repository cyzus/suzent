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

    mock_router = MagicMock()
    mock_router.get_model_id.return_value = "openai/gpt-4.1"

    with patch(
        "suzent.tools.image_vision_tool.get_or_create_path_resolver",
        return_value=mock_resolver,
    ):
        with patch("suzent.core.role_router.get_role_router", return_value=mock_router):
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

    # RoleRouter returns None → no vision model configured
    mock_router = MagicMock()
    mock_router.get_model_id.return_value = None

    with patch(
        "suzent.tools.image_vision_tool.get_or_create_path_resolver",
        return_value=mock_resolver,
    ):
        with patch("suzent.core.role_router.get_role_router", return_value=mock_router):
            with patch("builtins.open", new_callable=MagicMock) as mock_open:
                mock_file = MagicMock()
                mock_file.read.return_value = b"fake_image_data"
                mock_open.return_value.__enter__.return_value = mock_file

                tool = ImageVisionTool()
                result = await tool.forward(mock_ctx, "huge.jpg", "Describe")

                assert not result.success
                assert result.error_code == ToolErrorCode.EXECUTION_FAILED
                assert "vision model" in result.message.lower()


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


def _staged_image(mock_open):
    """The mocks every call-path test needs: a readable 1KB png."""
    mock_stat = MagicMock()
    mock_stat.st_size = 1024

    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path.is_file.return_value = True
    mock_path.stat.return_value = mock_stat
    mock_path.suffix = ".png"
    mock_path.name = "test.png"

    mock_file = MagicMock()
    mock_file.read.return_value = b"fake_image_data"
    mock_open.return_value.__enter__.return_value = mock_file

    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = mock_path
    return mock_resolver


@pytest.mark.asyncio
@patch("suzent.tools.image_vision_tool.litellm.acompletion", new_callable=AsyncMock)
@patch("builtins.open", new_callable=MagicMock)
async def test_a_self_hosted_vision_model_is_reachable_and_not_thinking(
    mock_open, mock_acompletion, mock_ctx
):
    """This call used to go straight to LiteLLM with nothing but the model id,
    so a self-hosted endpoint had no api_base to reach and no instruction to
    stop thinking — the budget went to reasoning and the answer came back
    empty."""
    mock_resolver = _staged_image(mock_open)

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "A photo of a server rack."
    mock_acompletion.return_value = mock_response

    mock_router = MagicMock()
    mock_router.get_model_id.return_value = "sglang/qwen3-vl"

    with patch(
        "suzent.tools.image_vision_tool.get_or_create_path_resolver",
        return_value=mock_resolver,
    ):
        with patch("suzent.core.role_router.get_role_router", return_value=mock_router):
            with patch(
                "suzent.tools.image_vision_tool.chat_completion_args",
                return_value=(
                    "openai/qwen3-vl",
                    {
                        "api_base": "http://localhost:30000/v1",
                        "extra_body": {
                            "chat_template_kwargs": {"enable_thinking": False}
                        },
                    },
                ),
            ):
                result = await ImageVisionTool().forward(mock_ctx, "test.png", "What?")

    assert result.success
    sent = mock_acompletion.call_args.kwargs
    assert sent["model"] == "openai/qwen3-vl"
    assert sent["api_base"] == "http://localhost:30000/v1"
    assert sent["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False


@pytest.mark.asyncio
@patch("suzent.tools.image_vision_tool.litellm.acompletion", new_callable=AsyncMock)
@patch("builtins.open", new_callable=MagicMock)
async def test_an_empty_completion_is_an_error_not_an_empty_description(
    mock_open, mock_acompletion, mock_ctx
):
    """A reasoning model that spends the budget before answering returns a 200
    with no content. Reported as a success it becomes an empty description the
    agent has no reason to doubt."""
    mock_resolver = _staged_image(mock_open)

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = ""
    mock_acompletion.return_value = mock_response

    mock_router = MagicMock()
    mock_router.get_model_id.return_value = "sglang/qwen3-vl"

    with patch(
        "suzent.tools.image_vision_tool.get_or_create_path_resolver",
        return_value=mock_resolver,
    ):
        with patch("suzent.core.role_router.get_role_router", return_value=mock_router):
            result = await ImageVisionTool().forward(mock_ctx, "test.png", "What?")

    assert not result.success
    assert result.error_code == ToolErrorCode.EXECUTION_FAILED
    assert "empty completion" in result.message.lower()
