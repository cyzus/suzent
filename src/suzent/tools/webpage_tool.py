from smolagents.tools import Tool
from typing import Optional, Union

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
        "url": {"type": "string", "description": "The URL of the page to retrieve content from."},
    }
    output_type: str = "string"

    def __init__(self):
        self.crawler = AsyncWebCrawler()

    def forward(self, url: str) -> str:
        result = asyncio.run(self.crawler.arun(url=url))
        return result.markdown if result else "Error: Unable to retrieve content from the specified URL."


        
        

