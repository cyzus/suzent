from pathlib import Path
import aiohttp
from datetime import datetime

from pydantic_ai import RunContext
from suzent.core.agent_deps import AgentDeps

from suzent.tools.base import Tool
from suzent.llm import ImageGenerator
from suzent.config import CONFIG
from suzent.logger import get_logger

logger = get_logger(__name__)


class ImageGenerationTool(Tool):
    """Tool for generating images from text prompts using LiteLLM."""

    name: str = "ImageGenerationTool"
    tool_name: str = "generate_image"
    requires_approval: bool = True

    async def forward(self, ctx: RunContext[AgentDeps], prompt: str) -> str:
        """Generate an image from the given prompt.

        Args:
            prompt: Text description of the image to generate

        Returns:
            String indicating success and the path where the image was saved
        """
        try:
            generator = ImageGenerator()
            image_url = await generator.generate(prompt=prompt)

            # Save the image locally to the session persistence directory if available
            chat_id = ctx.deps.chat_id
            if chat_id:
                workspace_dir = (
                    Path(CONFIG.sandbox_data_path) / "sessions" / chat_id / "images"
                )
            else:
                workspace_dir = Path(CONFIG.workspace_root) / "images"

            workspace_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"generated_image_{timestamp}.png"
            file_path = workspace_dir / filename

            import base64

            # Handle Base64 encoded images directly
            if image_url.startswith("data:image/png;base64,"):
                b64_data = image_url.split("data:image/png;base64,")[1]
                image_data = base64.b64decode(b64_data)
                with open(file_path, "wb") as f:
                    f.write(image_data)
                return f"Successfully generated and saved image to {file_path}"

            # Otherwise download the image URL
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        with open(file_path, "wb") as f:
                            f.write(image_data)
                        return f"Successfully generated and saved image to {file_path}"
                    else:
                        logger.error(
                            f"Failed to download generated image. Status: {response.status}"
                        )
                        return (
                            f"Generated image at {image_url} but failed to download it."
                        )

        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            return f"Failed to generate image: {str(e)}"
