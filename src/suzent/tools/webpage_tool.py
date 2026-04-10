from crawl4ai import AsyncWebCrawler

from suzent.tools.base import Tool, ToolGroup


class WebpageTool(Tool):
    """
    A tool for retrieving content from web pages.
    """

    name: str = "WebpageTool"
    tool_name: str = "webpage_fetch"
    group: ToolGroup = ToolGroup.WEB

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
            if not markdown:
                return "Error: Unable to retrieve content from the specified URL."
            return str(markdown)

    async def forward(self, url: str) -> str:
        """Fetch and extract content from a web page as markdown.

        Args:
            url: The URL of the page to retrieve content from.
        """
        return await self._crawl_url(url)
