from smolagents.tools import Tool
from typing import Union

import asyncio
from crawl4ai import AsyncWebCrawler


class WebpageTool(Tool):
    """
    A tool for retrieving content from web pages.
    """

    description: str = "A tool for retrieving content from web pages."
    name: str = "WebpageTool"
    is_initialized: bool = False

    inputs: dict[str, dict[str, Union[str, type, bool]]] = {
        "url": {
            "type": "string",
            "description": "The URL of the page to retrieve content from.",
        },
    }
    output_type: str = "string"

    async def _crawl_url(self, url: str) -> str:
        """Async helper to properly initialize and use the crawler."""
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)
            if not result:
                return "Error: Unable to retrieve content from the specified URL."
            # Convert to plain str to avoid pickle issues with StringCompatibleMarkdown
            # (crawl4ai's str subclass fails to unpickle because its __new__ expects
            #  a MarkdownGenerationResult object, not a raw string)
            markdown = result.markdown
            return str(markdown) if markdown else ""

    def forward(self, url: str) -> str:
        return asyncio.run(self._crawl_url(url))
