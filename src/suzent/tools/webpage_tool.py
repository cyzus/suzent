import html
from typing import Annotated, Optional, TypedDict

from pydantic import ConfigDict, Field, with_config
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry

from suzent.core.agent_deps import AgentDeps
from suzent.core.citation_manager import CitationSourceType
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult

# Pages shorter than this are usually a JS shell ("enable JavaScript") rather
# than real content; the agent is told to fall back to the browser tool.
_MIN_CONTENT_CHARS = 200
_MAX_CONTENT_CHARS = 200_000
_TIMEOUT_SECONDS = 30


@with_config(ConfigDict(extra="allow", use_attribute_docstrings=True))
class WebpageMetadata(TypedDict, total=False):
    url: str
    title: str
    """The page's HTML title, else its first heading, else the URL."""
    source_id: Optional[str]
    """The citation id the message starts with, as "[source_id] title"."""
    media_type: str


class WebpageResult(ToolResult):
    metadata: WebpageMetadata = Field(default_factory=dict)


def _make_fetcher():
    """Build pydantic-ai's local web fetcher (lazy: keeps startup imports light)."""
    from pydantic_ai.common_tools.web_fetch import WebFetchLocalTool

    return WebFetchLocalTool(
        max_content_length=_MAX_CONTENT_CHARS,
        allow_local_urls=False,
        timeout=_TIMEOUT_SECONDS,
    )


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

    async def _fetch_url(self, url: str) -> tuple[ToolResult, str | None]:
        """Fetch ``url`` as markdown. Returns the result and the page title, if known."""
        import suzent.tools.webpage_tool as _self

        try:
            fetched = await _self._make_fetcher()(url)
        except ModelRetry as e:
            return (
                ToolResult.error_result(
                    ToolErrorCode.EXECUTION_FAILED, str(e), metadata={"url": url}
                ),
                None,
            )

        if not isinstance(fetched, dict):
            media_type = getattr(fetched, "media_type", "binary")
            return (
                ToolResult.error_result(
                    ToolErrorCode.EXECUTION_FAILED,
                    f"The URL returned non-text content ({media_type}). "
                    "Download it and use read_file to convert it instead.",
                    metadata={"url": url, "media_type": media_type},
                ),
                None,
            )

        markdown = (fetched.get("content") or "").strip()
        # pydantic-ai returns the raw <title> text, entities included (&#8212;).
        title = html.unescape(fetched.get("title") or "").strip() or None
        if not markdown:
            return (
                ToolResult.error_result(
                    ToolErrorCode.EXECUTION_FAILED,
                    "Unable to retrieve content from the specified URL. If the page "
                    "needs JavaScript, open it with the browser tool instead.",
                    metadata={"url": url},
                ),
                title,
            )
        if len(markdown) < _MIN_CONTENT_CHARS:
            markdown += (
                "\n\n[Note: very little text was extracted. If this page renders "
                "with JavaScript, open it with the browser tool instead.]"
            )
        return ToolResult.success_result(markdown, metadata={"url": url}), title

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        url: Annotated[
            str,
            Field(
                description="URL of a publicly accessible web page to fetch and convert to markdown."
            ),
        ],
    ) -> WebpageResult:
        """Fetch and extract content from a web page as markdown.

        Args:
            url: The URL of the page to retrieve content from.
        """
        fetched, page_title = await self._fetch_url(url)
        result = WebpageResult.model_validate(fetched.model_dump())
        if result.success:
            # Prefer the HTML <title>, then the first markdown heading, else the URL.
            title = (
                (page_title[:120] if page_title else None)
                or _title_from_markdown(result.message)
                or url
            )
            result.metadata["title"] = title
            mgr = getattr(ctx.deps, "citation_manager", None)
            if mgr is not None:
                source_id = mgr.register(
                    type=CitationSourceType.WEBPAGE,
                    title=title,
                    url=url,
                    snippet=result.message,
                )
                # Label the content with its id so the model cites it correctly.
                result.message = f"[{source_id}] {title}\n\n{result.message}"
                result.metadata["source_id"] = source_id
        return result
