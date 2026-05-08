from types import SimpleNamespace
import asyncio

import pytest
from pydantic_ai import Tool as PydanticTool

from suzent.tools.base import ToolErrorCode
from suzent.tools.render_ui_tool import RenderUITool


@pytest.mark.asyncio
async def test_render_ui_accepts_surface_id_aliases_and_text_alias():
    queue: asyncio.Queue = asyncio.Queue()
    ctx = SimpleNamespace(deps=SimpleNamespace(a2ui_queue=queue))

    result = await RenderUITool().forward(
        ctx,
        id="choices",
        component={"type": "text", "text": "Pick one"},
        target="inline",
    )

    assert result.success
    event = queue.get_nowait()
    assert event["id"] == "choices"
    assert event["target"] == "inline"
    assert event["component"] == {
        "type": "text",
        "content": "Pick one",
        "variant": "body",
        "markdown": False,
    }


@pytest.mark.asyncio
async def test_render_ui_returns_validation_error_for_invalid_component():
    queue: asyncio.Queue = asyncio.Queue()
    ctx = SimpleNamespace(deps=SimpleNamespace(a2ui_queue=queue))

    result = await RenderUITool().forward(
        ctx,
        surface_id="results",
        component={"type": "table", "rows": [{"name": "Ada"}]},
    )

    assert not result.success
    assert result.error_code == ToolErrorCode.INVALID_ARGUMENT
    assert "errors" in result.metadata
    assert queue.empty()


def test_render_ui_schema_allows_extra_root_fields():
    schema = PydanticTool(RenderUITool().forward).function_schema.json_schema

    assert schema["additionalProperties"] is True
    assert "id" in schema["properties"]
