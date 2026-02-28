"""
Web search tool that can use either DDGS or SearXNG.

This tool provides flexible web search capabilities:
- If SEARXNG_BASE_URL is set in .env, it uses a SearXNG instance
- Otherwise, it falls back to DDGS

SearXNG provides privacy-focused meta-search with customizable parameters.
"""

import os
import json
import httpx
from urllib.parse import urlparse
from typing import Optional, List, Dict, Any

from suzent.tools.base import Tool
from suzent.logger import get_logger

logger = get_logger(__name__)


class WebSearchTool(Tool):
    """
    A unified web search tool that uses SearXNG if configured, otherwise falls back to DDGS.

    If SEARXNG_BASE_URL is set in environment variables, this tool will use a SearXNG instance
    for privacy-focused meta-search. Otherwise, it defaults to using the DDGS library.
    """

    name: str = "WebSearchTool"
    description: str = "Performs a web search using either SearXNG or DDGS. Returns search results formatted as markdown with titles, links, and descriptions."
    is_initialized: bool = False

    # Constants
    TIME_RANGE_MAPPING = {
        "day": "d",
        "d": "d",
        "week": "w",
        "w": "w",
        "month": "m",
        "m": "m",
        "year": "y",
        "y": "y",
    }

    inputs = {
        "query": {"type": "string", "description": "The search query string."},
        "categories": {
            "type": "string",
            "description": "Search category",
            "enum": ["general", "news", "images", "videos"],
            "nullable": True,
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of results to return. Default: 10.",
            "nullable": True,
        },
        "time_range": {
            "type": "string",
            "description": "Time range for general/news search.",
            "enum": ["day", "week", "month", "year"],
            "nullable": True,
        },
        "page": {
            "type": "integer",
            "description": "Page number for results (default: 1). General search only.",
            "nullable": True,
        },
    }
    output_type = "string"

    def __init__(self):
        """Initialize the tool by checking for SearXNG configuration."""
        self.searxng_base_url = os.getenv("SEARXNG_BASE_URL")
        self.use_searxng = self._validate_searxng_url(self.searxng_base_url)

        self.client: Optional[httpx.Client] = None

        if self.use_searxng:
            self._init_searxng_client()

        # DDGS is initialized lazily per request

    def _validate_searxng_url(self, url: Optional[str]) -> bool:
        """Validate the SearXNG URL."""
        if not url or not url.strip():
            return False

        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            logger.warning(f"Invalid SEARXNG_BASE_URL provided: {url}")
            return False

    def _init_searxng_client(self):
        """Initialize the HTTP client for SearXNG."""
        logger.info(f"Using SearXNG at {self.searxng_base_url}")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        }
        self.client = httpx.AsyncClient(
            base_url=self.searxng_base_url,
            timeout=30.0,
            headers=headers,
            follow_redirects=True,
        )

    async def forward(
        self,
        query: str,
        categories: Optional[str] = None,
        max_results: Optional[int] = 10,
        time_range: Optional[str] = None,
        page: Optional[int] = 1,
    ) -> str:
        """
        Perform a web search using either SearXNG or the default search tool.
        """
        if self.use_searxng:
            return await self._search_with_searxng(
                query, categories, max_results, time_range, page
            )
        else:
            return await self._search_with_ddgs(
                query, categories, max_results, time_range, page
            )

    async def _search_with_ddgs(
        self,
        query: str,
        category: Optional[str] = None,
        max_results: Optional[int] = 10,
        time_range: Optional[str] = None,
        page: Optional[int] = 1,
    ) -> str:
        """Perform search using DuckDuckGo."""
        timelimit = (
            self.TIME_RANGE_MAPPING.get(time_range.lower()) if time_range else None
        )

        max_results = max_results if max_results else 10
        if max_results > 20:
            max_results = 20  # Cap to reasonable limit

        try:
            import asyncio
            from ddgs import DDGS
            import ddgs.http_client

            def _do_search():
                # Runs in a separate thread to prevent blocking main loop
                # Monkey-patch duckduckgo-search to use a safe impersonation target
                # to prevent the underlying primp (Rust) client from deadlocking on deprecated browsers
                ddgs.http_client.HttpClient._impersonates = (None,)
                
                with DDGS(timeout=15) as ddgs_client:
                    if not category or category == "general":
                        return list(ddgs_client.text(query, timelimit=timelimit, max_results=max_results))
                    elif category == "news":
                        return list(ddgs_client.news(query, timelimit=timelimit, max_results=max_results))
                    elif category == "images":
                        return list(ddgs_client.images(query, timelimit=timelimit, max_results=max_results))
                    elif category == "videos":
                        return list(ddgs_client.videos(query, timelimit=timelimit, max_results=max_results))
                    else:
                        raise ValueError(f"Error: Unsupported category '{category}'")

            source_label = f"DDGS ({category or 'general'})"
            try:
                results = await asyncio.wait_for(asyncio.to_thread(_do_search), timeout=20.0)
            except asyncio.TimeoutError:
                logger.error("DDGS search timed out at the thread level.")
                return f"Error: DDGS search timed out. The search library might be hanging."

            if not results:
                return f"No results found for query: '{query}'"

            return self._format_results(
                results, source=source_label, category=category
            )

        except Exception as e:
            logger.error(f"DDGS search failed: {e}")
            return f"Error querying DDGS: {str(e)}"

    async def _search_with_searxng(
        self,
        query: str,
        categories: Optional[str] = None,
        max_results: Optional[int] = 10,
        time_range: Optional[str] = None,
        page: Optional[int] = 1,
    ) -> str:
        """Perform a search using SearXNG instance."""
        try:
            params = {
                "q": query,
                "format": "json",
                "page": page or 1,
            }

            if categories:
                params["categories"] = categories
            if time_range:
                params["time_range"] = time_range

            if not self.client:
                self._init_searxng_client()

            response = await self.client.get("/search", params=params)

            if response.status_code == 403:
                logger.warning("SearXNG JSON format restricted, falling back to DDGS")
                return await self._search_with_ddgs(
                    query, category=categories, max_results=max_results, time_range=time_range, page=page
                )

            response.raise_for_status()

            try:
                data = json.loads(response.text)
                return self._format_results(
                    data.get("results", []),
                    source="SearXNG",
                    query=data.get("query", query),
                )
            except json.JSONDecodeError:
                return response.text

        except httpx.HTTPStatusError as e:
            logger.warning(f"SearXNG failed with {e.response.status_code}. Falling back to DDGS.")
            return await self._search_with_ddgs(query, category=categories, max_results=max_results, time_range=time_range, page=page)

        except (httpx.RequestError, Exception) as e:
            logger.warning(f"SearXNG connection failed: {str(e)}. Falling back to DDGS.")
            return await self._search_with_ddgs(query, category=categories, max_results=max_results, time_range=time_range, page=page)

    def _format_results(
        self,
        results: List[Dict[str, Any]],
        source: str,
        query: str = "",
        category: Optional[str] = None,
    ) -> str:
        """
        Unified results formatting for both providers.
        """
        if not results:
            return "No results found."

        output = [f"# Search Results (via {source})\n"]

        for i, result in enumerate(results, 1):
            # Normalize fields based on category/source

            # Common defaults
            title = result.get("title", "No title")
            url = result.get("url") or result.get("href") or ""
            content = result.get("content") or result.get("body") or ""

            # Special handling for Images/Videos/News fields if distinct
            if category == "images":
                # DDGS images: 'title', 'image', 'thumbnail', 'url', 'height', 'width', 'source'
                image_url = result.get("image", "")
                thumbnail = result.get("thumbnail", "")
                url = result.get("url")  # Page URL
                content = f"Image: {image_url}\nThumbnail: {thumbnail}"
            elif category == "videos":
                # DDGS videos: 'title', 'content', 'embed_url', 'deputy_id', 'description', 'images', 'uploader', 'duration', 'published'
                description = result.get("description", "")
                uploader = result.get("uploader", "")
                duration = result.get("duration", "")
                content = f"{description}\nUploader: {uploader} | Duration: {duration}"
            elif category == "news":
                # DDGS news: 'date', 'title', 'body', 'url', 'image', 'source'
                date = result.get("date", "")
                source_news = result.get("source", "")
                content = f"{content}\nDate: {date} | Source: {source_news}"

            engines = result.get("engines", [])

            # Clean content if string
            if isinstance(content, str):
                content = " ".join(content.split())
                if len(content) > 300:  # Allow slightly more context
                    content = content[:297] + "..."

            output.append(f"## {i}. {title}")
            output.append(f"**URL:** {url}")
            output.append(f"**Description:** {content}")
            if engines:
                output.append(f"**Sources:** {', '.join(engines)}")
            output.append("")

        return "\n".join(output)

    def __del__(self):
        """Clean up HTTP client."""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
