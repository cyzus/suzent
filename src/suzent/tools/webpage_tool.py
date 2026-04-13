from typing import Annotated

from pydantic import Field
from crawl4ai import AsyncWebCrawler

from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult


class WebpageTool(Tool):
    """
    A tool for retrieving content from web pages.
    """

    name: str = "WebpageTool"
    tool_name: str = "webpage_fetch"
    group: ToolGroup = ToolGroup.WEB

    async def _crawl_url(self, url: str) -> ToolResult:
        """Async helper to properly initialize and use the crawler."""
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)
            if not result:
                return ToolResult.error_result(
                    ToolErrorCode.EXECUTION_FAILED,
                    "Unable to retrieve content from the specified URL.",
                    metadata={"url": url},
                )
            # Convert to plain str to avoid pickle issues with StringCompatibleMarkdown
            # (crawl4ai's str subclass fails to unpickle because its __new__ expects
            #  a MarkdownGenerationResult object, not a raw string)
            markdown = result.markdown
            if not markdown:
                return ToolResult.error_result(
                    ToolErrorCode.EXECUTION_FAILED,
                    "Unable to retrieve content from the specified URL.",
                    metadata={"url": url},
                )
            return ToolResult.success_result(
                str(markdown),
                metadata={"url": url},
            )

    async def forward(
        self,
        url: Annotated[
            str,
            Field(
                description="URL of a publicly accessible web page to fetch and convert to markdown."
            ),
        ],
    ) -> ToolResult:
        """Fetch and extract content from a web page as markdown.

        Args:
            url: The URL of the page to retrieve content from.
        """
        return await self._crawl_url(url)
