from pathlib import Path
import aiohttp
from datetime import datetime
from typing import Annotated, Optional

from pydantic import Field
from pydantic_ai import RunContext
from suzent.core.agent_deps import AgentDeps

from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult
from suzent.llm import ImageGenerator
from suzent.config import CONFIG
from suzent.logger import get_logger

logger = get_logger(__name__)


class ImageGenerationTool(Tool):
    """Tool for generating images from text prompts using LiteLLM."""

    name: str = "ImageGenerationTool"
    tool_name: str = "generate_image"
    group: ToolGroup = ToolGroup.CREATIVE
    requires_approval: bool = True

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        prompt: Annotated[
            str, Field(description="Text prompt describing the image to generate.")
        ],
        style: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Optional style hint to fold into the generation prompt.",
            ),
        ] = None,
        size: Annotated[
            Optional[str],
            Field(
                default=None, description="Optional image size hint, such as 1024x1024."
            ),
        ] = None,
        count: Annotated[
            int,
            Field(
                default=1,
                ge=1,
                le=4,
                description="Number of images to generate. The tool returns up to four images.",
            ),
        ] = 1,
    ) -> ToolResult:
        """Generate an image from the given prompt.

        Args:
            prompt: Text description of the image to generate

        Returns:
            String indicating success and the path where the image was saved
        """
        if not prompt.strip():
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "prompt is required.",
            )

        try:
            generator = ImageGenerator()
            generated_images = []
            for _ in range(count):
                generation_prompt = prompt
                if style:
                    generation_prompt = f"{generation_prompt}\nStyle: {style}"
                if size:
                    generation_prompt = f"{generation_prompt}\nSize: {size}"
                image_url = await generator.generate(prompt=generation_prompt)
                generated_images.append(image_url)

            # Save the image locally to the session persistence directory if available
            chat_id = ctx.deps.chat_id
            if chat_id:
                workspace_dir = (
                    Path(CONFIG.sandbox_data_path) / "sessions" / chat_id / "images"
                )
            else:
                workspace_dir = Path(CONFIG.workspace_root) / "images"

            workspace_dir.mkdir(parents=True, exist_ok=True)

            saved_paths = []

            import base64

            async with aiohttp.ClientSession() as session:
                for index, image_url in enumerate(generated_images, 1):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"generated_image_{timestamp}_{index}.png"
                    file_path = workspace_dir / filename

                    if image_url.startswith("data:image/png;base64,"):
                        b64_data = image_url.split("data:image/png;base64,")[1]
                        image_data = base64.b64decode(b64_data)
                        with open(file_path, "wb") as f:
                            f.write(image_data)
                        saved_paths.append(str(file_path))
                        continue

                    async with session.get(image_url) as response:
                        if response.status == 200:
                            image_data = await response.read()
                            with open(file_path, "wb") as f:
                                f.write(image_data)
                            saved_paths.append(str(file_path))
                        else:
                            logger.error(
                                f"Failed to download generated image. Status: {response.status}"
                            )
                            return ToolResult.error_result(
                                ToolErrorCode.EXECUTION_FAILED,
                                f"Generated image at {image_url} but failed to download it.",
                                metadata={
                                    "prompt": prompt,
                                    "style": style,
                                    "size": size,
                                    "count": count,
                                },
                            )

            return ToolResult.success_result(
                f"Successfully generated and saved {len(saved_paths)} image(s).",
                metadata={
                    "prompt": prompt,
                    "style": style,
                    "size": size,
                    "count": count,
                    "saved_paths": saved_paths,
                },
            )

        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"Failed to generate image: {str(e)}",
                metadata={
                    "prompt": prompt,
                    "style": style,
                    "size": size,
                    "count": count,
                },
            )
