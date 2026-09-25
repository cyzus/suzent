"""Submit provider video jobs and recover their results across agent turns."""

import asyncio
from contextlib import ExitStack
from pathlib import Path
import re
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from suzent.config import CONFIG
from suzent.core.agent_deps import AgentDeps
from suzent.core.role_router import get_role_router
from suzent.llm import _litellm, _litellm_model_and_kwargs
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult
from suzent.tools.creative.image_output import image_suffix
from suzent.tools.filesystem.file_tool_utils import get_or_create_path_resolver


class VideoJob(BaseModel):
    model: str
    provider_id: str
    chat_id: str | None
    status: str = "queued"
    progress: float | None = None
    saved_paths: list[str] = Field(default_factory=list)
    error: str | None = None


def _directory(deps: AgentDeps) -> Path:
    if deps.chat_id:
        from suzent.database import get_database

        root = get_database().get_project_dir(deps.chat_id)
    else:
        root = Path(CONFIG.workspace_root)
    directory = root / "videos"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _save(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class VideoGenerationTool(Tool):
    """Start a video generation job. Use check_video with the returned job_id to retrieve progress and save the completed video. Do not resubmit a pending job."""

    name = "VideoGenerationTool"
    tool_name = "generate_video"
    group = ToolGroup.CREATIVE
    requires_approval = True

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        prompt: Annotated[
            str, Field(description="Describe the video, action and camera movement.")
        ],
        image_path: Annotated[
            str | None,
            Field(
                description="Optional local reference image for image-to-video; model must support it."
            ),
        ] = None,
        seconds: Annotated[
            int | None,
            Field(
                ge=1,
                le=120,
                description="Duration in seconds, subject to model limits.",
            ),
        ] = None,
        size: Annotated[
            str | None,
            Field(description="Model-supported dimensions, e.g. 1280x720 or 720x1280."),
        ] = None,
    ) -> ToolResult:
        if not prompt.strip() or (seconds is not None and not 1 <= seconds <= 120):
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT, "Provide a prompt and a valid duration."
            )
        model = get_role_router().get_model_id("video_generation")
        if not model:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "Configure Settings → Model Roles → Video generation first.",
            )
        try:
            directory = _directory(ctx.deps)
            routed_model, auth = _litellm_model_and_kwargs(model)
            options = {
                key: value
                for key, value in {
                    "seconds": str(seconds) if seconds is not None else None,
                    "size": size,
                }.items()
                if value is not None
            }
            with ExitStack() as stack:
                if image_path:
                    path = get_or_create_path_resolver(ctx.deps).resolve(image_path)
                    if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
                        raise ValueError(
                            "Reference must be an image file of at most 20 MB."
                        )
                    handle = stack.enter_context(path.open("rb"))
                    image_suffix(handle.read(16))
                    handle.seek(0)
                    options["input_reference"] = handle
                response = await _litellm().avideo_generation(
                    model=routed_model,
                    prompt=prompt,
                    **auth,
                    **options,
                    drop_params=False,
                    max_retries=0,
                    timeout=120,
                )
            job_id = uuid4().hex
            job = VideoJob(
                model=model,
                provider_id=response.id,
                chat_id=ctx.deps.chat_id,
                status=response.status,
            )
            await asyncio.to_thread(
                _save, directory / f"{job_id}.json", job.model_dump_json().encode()
            )
            return ToolResult.success_result(
                "Video submitted. Use check_video to query progress; wait at least 10 seconds between checks.",
                metadata={"job_id": job_id, "status": job.status},
            )
        except Exception as exc:
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"Video submission failed: {exc}. If the request timed out, verify provider jobs before resubmitting to avoid duplicate charges.",
            )


class VideoStatusTool(Tool):
    """Query a previously submitted video job in this chat. Saves completed video and returns saved_paths. Safe to retry after a download failure; never creates a new generation."""

    name = "VideoStatusTool"
    tool_name = "check_video"
    group = ToolGroup.CREATIVE

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        job_id: Annotated[str, Field(description="job_id returned by generate_video.")],
    ) -> ToolResult:
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT, "Invalid video job ID."
            )
        try:
            directory = _directory(ctx.deps)
            path = directory / f"{job_id}.json"
            job = VideoJob.model_validate_json(await asyncio.to_thread(path.read_bytes))
            if job.chat_id != ctx.deps.chat_id:
                return ToolResult.error_result(
                    ToolErrorCode.PERMISSION_DENIED,
                    "Video job belongs to another chat.",
                )
            if not job.saved_paths and job.status != "failed":
                model, auth = _litellm_model_and_kwargs(job.model)
                client = _litellm()
                response = await client.avideo_status(
                    video_id=job.provider_id, model=model, **auth, timeout=60
                )
                job.status = response.status
                job.progress = getattr(response, "progress", None)
                error = getattr(response, "error", None)
                job.error = str(error) if error else None
                await asyncio.to_thread(_save, path, job.model_dump_json().encode())
                if job.status == "completed":
                    content = await client.avideo_content(
                        video_id=job.provider_id, model=model, **auth, timeout=120
                    )
                    if not isinstance(content, bytes) or not content:
                        raise ValueError("Provider returned empty video content.")
                    video = directory / f"{job_id}.mp4"
                    await asyncio.to_thread(_save, video, content)
                    job.saved_paths = [str(video)]
                    await asyncio.to_thread(_save, path, job.model_dump_json().encode())
            metadata = {
                "job_id": job_id,
                "status": job.status,
                "progress": job.progress,
                "saved_paths": job.saved_paths,
            }
            if job.status == "failed":
                return ToolResult.error_result(
                    ToolErrorCode.EXECUTION_FAILED,
                    job.error or "Video generation failed.",
                    metadata=metadata,
                )
            return ToolResult.success_result(
                f"Video {job.status}"
                + (f" ({job.progress:g}%)." if job.progress is not None else "."),
                metadata=metadata,
            )
        except Exception as exc:
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"Unable to retrieve video: {exc}. Retry check_video with the same job_id.",
            )
