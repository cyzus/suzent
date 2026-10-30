import asyncio
import base64
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext
import litellm

from suzent.core.agent_deps import AgentDeps
from suzent.core.model_registry import get_model_registry
from suzent.llm import EmptyCompletionError, chat_completion_args
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult
from suzent.tools.filesystem.file_tool_utils import get_or_create_path_resolver
from suzent.logger import get_logger

logger = get_logger(__name__)

MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB limit
MAX_INLINE_VIDEO_SIZE = 20 * 1024 * 1024
MAX_DASHSCOPE_VIDEO_SIZE = 7 * 1024 * 1024
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv"}
VIDEO_MIME_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/mov",
    ".webm": "video/webm",
    ".avi": "video/avi",
    ".mkv": "video/x-matroska",
}
IMAGE_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

#: Room for a description, and for the reasoning a self-hosted server may
#: insist on emitting first despite being asked not to.
VISION_MAX_TOKENS = 2000


class VisualAnalysisTool(Tool):
    """Analyze images or send complete videos to a compatible vision model."""

    name: str = "VisualAnalysisTool"
    tool_name: str = "analyze_visual"
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
        visual_path: Annotated[
            str,
            Field(
                description="Absolute or relative path to a local image or video file."
            ),
        ],
        prompt: Annotated[
            str,
            Field(
                description="What to ask the vision model about the image or video.",
            ),
        ] = "Describe this visual in detail.",
    ) -> ToolResult:
        try:
            resolver = get_or_create_path_resolver(ctx.deps)
            path = resolver.resolve(visual_path)

            if not path.exists():
                return ToolResult.error_result(
                    ToolErrorCode.FILE_NOT_FOUND, f"Visual file not found: {path}"
                )

            if not path.is_file():
                return ToolResult.error_result(
                    ToolErrorCode.FILE_REQUIRED, f"Path is not a file: {path}"
                )

            ext = path.suffix.lower()
            is_video = ext in VIDEO_EXTENSIONS
            if not is_video and ext not in IMAGE_MIME_TYPES:
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT,
                    f"Unsupported visual file type: {ext}",
                )

            file_stat = path.stat()
            size_limit = MAX_INLINE_VIDEO_SIZE if is_video else MAX_IMAGE_SIZE
            if file_stat.st_size > size_limit:
                return ToolResult.error_result(
                    ToolErrorCode.FILE_TOO_LARGE,
                    f"Visual file too large ({file_stat.st_size} bytes). Max size is {size_limit} bytes.",
                )

            model = self._resolve_vision_model()
            if not model:
                return ToolResult.error_result(
                    ToolErrorCode.EXECUTION_FAILED,
                    "No vision model configured. Set it in Settings → Model Roles.",
                )

            provider = model.partition("/")[0]
            if is_video and provider == "gemini" and ext == ".mkv":
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT,
                    "Gemini does not accept MKV video input. Use MP4, MOV, WebM, or AVI.",
                )
            if (
                is_video
                and provider == "dashscope"
                and file_stat.st_size > MAX_DASHSCOPE_VIDEO_SIZE
            ):
                return ToolResult.error_result(
                    ToolErrorCode.FILE_TOO_LARGE,
                    "DashScope inline video must be under 7 MB to fit its encoded request limit.",
                )
            if is_video and (
                not get_model_registry().supports_video(model)
                or provider not in {"gemini", "dashscope", "openrouter"}
            ):
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT,
                    f"The configured Vision model ({model}) has no supported native video input. Choose a video-capable Vision model in Settings → Model Roles.",
                )

            content: list[dict] = [{"type": "text", "text": prompt}]
            if is_video:
                video_bytes = await asyncio.to_thread(path.read_bytes)
                if provider == "gemini":
                    # LiteLLM's Gemini adapter converts a video MIME data URL
                    # in image_url into Gemini inline_data.
                    content = [
                        self._image_part(video_bytes, VIDEO_MIME_TYPES[ext]),
                        {"type": "text", "text": prompt},
                    ]
                else:
                    encoded = base64.b64encode(video_bytes).decode("ascii")
                    content = [
                        {
                            "type": "video_url",
                            "video_url": {
                                "url": f"data:{VIDEO_MIME_TYPES[ext]};base64,{encoded}"
                            },
                        },
                        {"type": "text", "text": prompt},
                    ]
            else:
                with open(path, "rb") as image_file:
                    content.append(
                        self._image_part(image_file.read(), IMAGE_MIME_TYPES[ext])
                    )

            messages = [
                {
                    "role": "user",
                    "content": content,
                }
            ]

            logger.info("Analyzing visual {} with model {}", path.name, model)
            # Through the shared resolution rather than straight to LiteLLM: a
            # self-hosted vision endpoint needs its api_base and its thinking
            # switched off, and neither is visible from here.
            litellm_model, call_kwargs = chat_completion_args(model, multimodal=True)
            response = await litellm.acompletion(
                model=litellm_model,
                messages=messages,
                max_tokens=VISION_MAX_TOKENS,
                **call_kwargs,
            )

            # Billed before it is read: an answerless response is the
            # expensive case, not the free one — the tokens went to reasoning
            # that never reached a description. Logging after the content check
            # would drop exactly those from the ledger.
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

            result_text = response.choices[0].message.content
            if not result_text or not result_text.strip():
                # A 200 with nothing in it. Reported as itself, because the
                # alternative is a success result holding an empty string and a
                # reader with no idea the model never answered.
                raise EmptyCompletionError(model)

            return ToolResult.success_result(
                result_text,
                metadata={
                    "visual_path": str(path),
                    "analysis_mode": "native_video" if is_video else "image",
                },
            )

        except Exception as e:
            logger.error("Visual analysis failed: {}", e)
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED, f"Failed to analyze visual: {str(e)}"
            )

    @staticmethod
    def _image_part(data: bytes, mime_type: str) -> dict:
        encoded = base64.b64encode(data).decode("ascii")
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
        }
