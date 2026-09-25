import traceback
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.llm import ImageGenerator
from suzent.logger import get_logger
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult
from suzent.tools.creative.image_output import save_images

logger = get_logger(__name__)


class ImageGenerationTool(Tool):
    """Generate new images from text. Use edit_image to modify existing images."""

    name: str = "ImageGenerationTool"
    tool_name: str = "generate_image"
    group: ToolGroup = ToolGroup.CREATIVE
    requires_approval: bool = True

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        prompt: Annotated[
            str, Field(description="Text description of the desired image.")
        ],
        style: Annotated[
            str | None, Field(description="Free-form style hint added to the prompt.")
        ] = None,
        size: Annotated[
            str | None,
            Field(
                description="Output size, e.g. 1536x1024. Supported values depend on the model."
            ),
        ] = None,
        count: Annotated[
            int,
            Field(
                ge=1,
                le=4,
                description="Number of images, subject to model limits (DALL-E 3 supports one).",
            ),
        ] = 1,
        quality: Annotated[
            str | None,
            Field(
                description="Model-specific quality, e.g. low/medium/high or standard/hd."
            ),
        ] = None,
    ) -> ToolResult:
        if not prompt.strip() or not 1 <= count <= 4:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "Provide a non-empty prompt and count between 1 and 4.",
            )
        try:
            generator = ImageGenerator()
            images = await generator.generate(
                f"{prompt}\nStyle: {style}" if style else prompt,
                size=size,
                quality=quality,
                count=count,
            )
            paths = await save_images(images, ctx.deps)
            note = (
                " Unsupported quality was ignored; provider defaults were used."
                if generator.dropped_params
                else ""
            )
            return ToolResult.success_result(
                f"Successfully generated and saved {len(paths)} image(s).{note}",
                metadata={
                    "saved_paths": paths,
                    "prompt": prompt,
                    "style": style,
                    "size": size,
                    "quality": None
                    if "quality" in generator.dropped_params
                    else quality,
                    "dropped_params": generator.dropped_params,
                    "count": count,
                },
            )
        except Exception as exc:  # noqa: BLE001 — tool boundary returns provider failures
            logger.error(f"Image generation failed: {traceback.format_exc()}")
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED, f"Failed to generate image: {exc}"
            )
