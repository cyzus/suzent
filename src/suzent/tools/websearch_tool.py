"""
Web search tool that can use either smolagents WebSearchTool or SearXNG.

This tool provides flexible web search capabilities:
- If SEARXNG_BASE_URL is set in .env, it uses a SearXNG instance
- Otherwise, it falls back to smolagents' built-in WebSearchTool

SearXNG provides privacy-focused meta-search with customizable parameters.
"""
import os
import json
from typing import Optional
import httpx
from smolagents.tools import Tool
from smolagents import WebSearchTool as SmolWebSearchTool


class WebSearchTool(Tool):
    """
    A unified web search tool that uses SearXNG if configured, otherwise falls back to default web search.
    
    If SEARXNG_BASE_URL is set in environment variables, this tool will use a SearXNG instance
    for privacy-focused meta-search. Otherwise, it uses the default smolagents WebSearchTool.
    """
    name: str = "WebSearchTool"
    description: str = "Performs a web search using either SearXNG or default search. Returns search results formatted as markdown with titles, links, and descriptions."
    is_initialized: bool = False

    inputs = {
        "query": {
            "type": "string",
            "description": "The search query string."
        },
        "categories": {
            "type": "string",
            "description": "Optional categories to search (e.g., 'general', 'news', 'images'). SearXNG only.",
            "nullable": True
        },
        "language": {
            "type": "string",
            "description": "Optional language code (e.g., 'en', 'fr'). SearXNG only.",
            "nullable": True
        },
        "time_range": {
            "type": "string",
            "description": "Optional time range filter (e.g., 'day', 'week', 'month', 'year'). SearXNG only.",
            "nullable": True
        },
        "page": {
            "type": "integer",
            "description": "Optional page number for results (default: 1). SearXNG only.",
            "nullable": True
        },
    }
    output_type = "string"

    def __init__(self):
        """Initialize the tool by checking for SearXNG configuration."""
        self.searxng_base_url = os.getenv("SEARXNG_BASE_URL")
        self.use_searxng = bool(self.searxng_base_url)
        
        if self.use_searxng:
            print(f"WebSearch: Using SearXNG at {self.searxng_base_url}")
            # Add headers to avoid 403 errors from SearXNG
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
            }
            self.client = httpx.Client(
                base_url=self.searxng_base_url, 
                timeout=30.0,
                headers=headers,
                follow_redirects=True
            )
        else:
            print("WebSearch: Using default smolagents WebSearchTool")
            self.fallback_tool = SmolWebSearchTool()
            self.client = None

    def forward(
        self,
        query: str,
        categories: Optional[str] = None,
        language: Optional[str] = None,
        time_range: Optional[str] = None,
        page: Optional[int] = 1,
    ) -> str:
        """
        Perform a web search using either SearXNG or the default search tool.
        
        Args:
            query: The search query string
            categories: Optional categories for SearXNG (ignored for default search)
            language: Optional language code for SearXNG (ignored for default search)
            time_range: Optional time range filter for SearXNG (ignored for default search)
            page: Optional page number for SearXNG (ignored for default search)
        
        Returns:
            Search results as a string
        """
        if self.use_searxng:
            return self._search_with_searxng(query, categories, language, time_range, page)
        else:
            # Use the fallback tool, which only accepts query parameter
            return self.fallback_tool.forward(query=query)

    def _search_with_searxng(
        self,
        query: str,
        categories: Optional[str] = None,
        language: Optional[str] = None,
        time_range: Optional[str] = None,
        page: Optional[int] = 1,
    ) -> str:
        """
        Perform a search using SearXNG instance.
        
        Args:
            query: The search query string
            categories: Optional categories to search
            language: Optional language code
            time_range: Optional time range filter
            page: Optional page number
        
        Returns:
            JSON string with search results or error message
        """
        try:
            params = {
                "q": query,
                "format": "json",
                "page": page or 1,
            }
            
            # Add optional parameters if provided
            if categories:
                params["categories"] = categories
            if language:
                params["language"] = language
            if time_range:
                params["time_range"] = time_range

            response = self.client.get("/search", params=params)
            
            # If JSON format is forbidden (403), try without format parameter
            if response.status_code == 403:
                print("Warning: SearXNG JSON format restricted, falling back to smolagents WebSearchTool")
                # Fall back to the default tool
                if hasattr(self, 'fallback_tool'):
                    return self.fallback_tool.forward(query=query)
                else:
                    self.fallback_tool = SmolWebSearchTool()
                    return self.fallback_tool.forward(query=query)
            
            response.raise_for_status()
            
            # Parse and format the JSON response
            try:
                data = json.loads(response.text)
                return self._format_search_results(data)
            except json.JSONDecodeError:
                # If parsing fails, return raw response
                return response.text
            
        except httpx.HTTPStatusError as e:
            error_msg = f"Error: SearXNG returned status {e.response.status_code}"
            if e.response.text:
                error_msg += f": {e.response.text[:200]}"  # Limit error text length
            error_msg += f"\nURL: {e.request.url}\nHeaders sent: {dict(e.request.headers)}"
            return error_msg
        except httpx.RequestError as e:
            return f"Error: Failed to connect to SearXNG at {self.searxng_base_url}: {str(e)}"
        except Exception as e:
            return f"Error querying SearXNG: {str(e)}"

    def _format_search_results(self, data: dict) -> str:
        """
        Format SearXNG JSON results into a readable markdown string.
        
        Args:
            data: Parsed JSON response from SearXNG
        
        Returns:
            Formatted markdown string with search results
        """
        query = data.get("query", "")
        results = data.get("results", [])
        
        if not results:
            return f"No results found for query: '{query}'"
        
        # Build formatted output
        output = [f"# Search Results for: {query}\n"]
        
        # Limit to top 10 results for readability
        for i, result in enumerate(results[:10], 1):
            title = result.get("title", "No title")
            url = result.get("url", "")
            content = result.get("content", "No description available")
            engines = result.get("engines", [])
            
            # Clean up content - remove extra whitespace and limit length
            content = " ".join(content.split())
            if len(content) > 200:
                content = content[:197] + "..."
            
            output.append(f"## {i}. {title}")
            output.append(f"**URL:** {url}")
            output.append(f"**Description:** {content}")
            if engines:
                output.append(f"**Sources:** {', '.join(engines)}")
            output.append("")  # Empty line for spacing
        
        return "\n".join(output)

    def __del__(self):
        """Clean up HTTP client when tool is destroyed."""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass


