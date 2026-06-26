from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.core.citation_manager import CitationSourceType
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult


def __getattr__(name):
    if name == "AsyncWebCrawler":
        from crawl4ai import AsyncWebCrawler

        return AsyncWebCrawler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _title_from_markdown(markdown: str) -> str | None:
    """Return the first markdown heading text, if any, for use as a source title."""
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title[:120]
    return None


class WebpageTool(Tool):
    """
    A tool for retrieving content from web pages.
    """

    name: str = "WebpageTool"
    tool_name: str = "webpage_fetch"
    group: ToolGroup = ToolGroup.WEB

    async def _crawl_url(self, url: str) -> ToolResult:
        """Async helper to properly initialize and use the crawler."""
        import suzent.tools.webpage_tool as _self

        async with _self.AsyncWebCrawler() as crawler:
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
        ctx: RunContext[AgentDeps],
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
        result = await self._crawl_url(url)
        if result.success:
            mgr = getattr(ctx.deps, "citation_manager", None)
            if mgr is not None:
                # Derive a display title from the first markdown heading, else host.
                title = _title_from_markdown(result.message) or url
                source_id = mgr.register(
                    type=CitationSourceType.WEBPAGE,
                    title=title,
                    url=url,
                    snippet=result.message,
                )
                # Label the content with its id so the model cites it correctly.
                result.message = f"[{source_id}] {title}\n\n{result.message}"
        return result
