import base64
import os
from pathlib import Path
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext
import litellm

from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult
from suzent.logger import get_logger

logger = get_logger(__name__)


class ImageVisionTool(Tool):
    """Tool for analyzing images using a Vision LLM."""

    name: str = "ImageVisionTool"
    tool_name: str = "analyze_image"
    group: ToolGroup = ToolGroup.CREATIVE
    requires_approval: bool = False

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        image_path: Annotated[
            str, Field(description="Absolute or relative path to the local image file.")
        ],
        prompt: Annotated[
            str,
            Field(
                default="Describe this image in detail.",
                description="What to ask the vision model about the image.",
            ),
        ],
    ) -> ToolResult:
        try:
            path = Path(image_path)
            if not path.is_absolute():
                path = Path(os.getcwd()) / path

            if not path.exists():
                return ToolResult.error(
                    f"Image file not found: {path}", code=ToolErrorCode.FILE_NOT_FOUND
                )

            # Read and base64 encode
            with open(path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")

            # Determine mime type
            ext = path.suffix.lower()
            mime_type = "image/jpeg"
            if ext == ".png":
                mime_type = "image/png"
            elif ext == ".webp":
                mime_type = "image/webp"
            elif ext == ".gif":
                mime_type = "image/gif"

            model = getattr(
                ctx.deps.config, "vision_model", ctx.deps.config.default_model
            )
            if not model:
                model = "gpt-4o"

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_data}"
                            },
                        },
                    ],
                }
            ]

            logger.info(f"Analyzing image {path.name} with model {model}")
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                max_tokens=1000,
            )

            result_text = response.choices[0].message.content
            return ToolResult.success(result_text)

        except Exception as e:
            logger.error(f"Image vision failed: {e}")
            return ToolResult.error(
                f"Failed to analyze image: {str(e)}", code=ToolErrorCode.EXECUTION_ERROR
            )
