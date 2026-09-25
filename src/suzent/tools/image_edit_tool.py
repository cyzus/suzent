import traceback
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.llm import ImageGenerator
from suzent.logger import get_logger
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult
from suzent.tools.filesystem.file_tool_utils import get_or_create_path_resolver
from suzent.tools.image_output import image_suffix, save_images

logger = get_logger(__name__)
MAX_INPUT_BYTES = 20 * 1024 * 1024


class ImageEditTool(Tool):
    """Edit existing images with instructions, references, or a mask. Use generate_image for new images. Outputs new files; reuse saved_paths for further edits."""

    name: str = "ImageEditTool"
    tool_name: str = "edit_image"
    group: ToolGroup = ToolGroup.CREATIVE
    requires_approval: bool = True

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        prompt: Annotated[
            str, Field(description="Changes to make to the input images.")
        ],
        image_paths: Annotated[
            list[str],
            Field(
                min_length=1,
                max_length=16,
                description="Local source/reference image paths, including previous saved_paths. Multi-image support depends on the model.",
            ),
        ],
        mask_path: Annotated[
            str | None,
            Field(
                description="Optional PNG mask; transparent areas mark edits. Must match the source dimensions and be supported by the model."
            ),
        ] = None,
        size: Annotated[
            str | None, Field(description="Model-supported output dimensions.")
        ] = None,
        quality: Annotated[
            str | None, Field(description="Model-supported output quality.")
        ] = None,
        count: Annotated[int, Field(ge=1, le=4)] = 1,
    ) -> ToolResult:
        if not prompt.strip() or not 1 <= len(image_paths) <= 16 or not 1 <= count <= 4:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "Provide a prompt, 1–16 input images, and count between 1 and 4.",
            )
        try:
            generator = ImageGenerator(role="image_edit")
            resolver = get_or_create_path_resolver(ctx.deps)
            paths = [resolver.resolve(path) for path in image_paths]
            mask = resolver.resolve(mask_path) if mask_path else None
            for path in [*paths, *([mask] if mask else [])]:
                if not path.exists():
                    return ToolResult.error_result(
                        ToolErrorCode.FILE_NOT_FOUND, "Input image does not exist."
                    )
                if not path.is_file():
                    return ToolResult.error_result(
                        ToolErrorCode.FILE_REQUIRED, "Input image must be a file."
                    )
                if path.stat().st_size > MAX_INPUT_BYTES:
                    return ToolResult.error_result(
                        ToolErrorCode.FILE_TOO_LARGE,
                        "Each input image must be at most 20 MB.",
                    )
                with path.open("rb") as handle:
                    suffix = image_suffix(handle.read(16))
                if path == mask and suffix != ".png":
                    return ToolResult.error_result(
                        ToolErrorCode.INVALID_ARGUMENT, "Mask must be PNG."
                    )
            images = await generator.edit(
                prompt,
                [str(path) for path in paths],
                mask_path=str(mask) if mask else None,
                size=size,
                quality=quality,
                count=count,
            )
            saved_paths = await save_images(images, ctx.deps)
            return ToolResult.success_result(
                f"Successfully edited and saved {len(saved_paths)} image(s).",
                metadata={"saved_paths": saved_paths, "count": len(saved_paths)},
            )
        except Exception as exc:  # noqa: BLE001 — tool boundary returns provider failures
            logger.error(f"Image editing failed: {traceback.format_exc()}")
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED, f"Failed to edit image: {exc}"
            )
