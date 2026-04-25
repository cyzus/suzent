import base64
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext
import litellm

from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult
from suzent.tools.filesystem.file_tool_utils import get_or_create_path_resolver
from suzent.logger import get_logger

logger = get_logger(__name__)

MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB limit


class ImageVisionTool(Tool):
    """Tool for analyzing images using a Vision LLM."""

    name: str = "ImageVisionTool"
    tool_name: str = "analyze_image"
    group: ToolGroup = ToolGroup.CREATIVE
    requires_approval: bool = False

    def _resolve_vision_model(self) -> str | None:
        """Resolve vision model from RoleRouter only."""
        try:
            from suzent.core.role_router import get_role_router

            return get_role_router().get_model_id("vision")
        except Exception:
            return None

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
        ] = "Describe this image in detail.",
    ) -> ToolResult:
        try:
            resolver = get_or_create_path_resolver(ctx.deps)
            path = resolver.resolve(image_path)

            if not path.exists():
                return ToolResult.error_result(
                    ToolErrorCode.FILE_NOT_FOUND, f"Image file not found: {path}"
                )

            if not path.is_file():
                return ToolResult.error_result(
                    ToolErrorCode.FILE_REQUIRED, f"Path is not a file: {path}"
                )

            file_stat = path.stat()
            if file_stat.st_size > MAX_IMAGE_SIZE:
                return ToolResult.error_result(
                    ToolErrorCode.FILE_TOO_LARGE,
                    f"Image file too large ({file_stat.st_size} bytes). Max size is {MAX_IMAGE_SIZE} bytes.",
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

            model = self._resolve_vision_model()
            if not model:
                return ToolResult.error_result(
                    ToolErrorCode.EXECUTION_FAILED,
                    "No vision model configured. Set it in Settings → Model Roles.",
                )

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

            # Log cost
            try:
                usage = response.usage
                if usage:
                    from suzent.core.cost_tracker import get_cost_tracker

                    await get_cost_tracker().log_cost(
                        chat_id=getattr(ctx.deps, "chat_id", None),
                        model=model,
                        role="vision",
                        input_tokens=getattr(usage, "prompt_tokens", 0),
                        output_tokens=getattr(usage, "completion_tokens", 0),
                    )
            except Exception:
                pass

            return ToolResult.success_result(result_text)

        except Exception as e:
            logger.error(f"Image vision failed: {e}")
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED, f"Failed to analyze image: {str(e)}"
            )
