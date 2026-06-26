import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from suzent.tools.websearch_tool import WebSearchTool


@pytest.fixture
def mock_ctx():
    """Minimal RunContext stand-in: deps with a real CitationManager."""
    from suzent.core.citation_manager import CitationManager

    ctx = MagicMock()
    ctx.deps.citation_manager = CitationManager()
    return ctx


@pytest.fixture
def clean_env():
    # Store original env
    original_url = os.environ.get("SEARXNG_BASE_URL")
    if "SEARXNG_BASE_URL" in os.environ:
        del os.environ["SEARXNG_BASE_URL"]

    yield

    # Restore
    if original_url:
        os.environ["SEARXNG_BASE_URL"] = original_url
    else:
        if "SEARXNG_BASE_URL" in os.environ:
            del os.environ["SEARXNG_BASE_URL"]


def test_init_defaults_to_ddgs_when_env_unset(clean_env):
    tool = WebSearchTool()
    assert tool.use_searxng is False
    assert tool.client is None


def test_init_uses_searxng_when_env_set(clean_env):
    os.environ["SEARXNG_BASE_URL"] = "http://localhost:8080"
    with patch("httpx.AsyncClient") as mock_client:
        tool = WebSearchTool()
        assert tool.use_searxng is True
        assert tool.client is not None
        mock_client.assert_called_once()


async def test_ddgs_search_usage(clean_env, mock_ctx):
    """Verify DDGS is used with correct parameters."""
    # We patch 'ddgs.DDGS' so when 'from ddgs import DDGS' runs, it gets our mock
    with patch("ddgs.DDGS") as MockDDGS:
        mock_instance = MockDDGS.return_value
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.text.return_value = [
            {"title": "Test", "href": "http://test.com", "body": "content"}
        ]

        tool = WebSearchTool()
        result = await tool.forward(mock_ctx, query="test", max_results=5)

        assert "Test" in result.message

        # The result is registered and its src id is embedded in the output the
        # model reads, so it can cite the source inline.
        import json

        sources = mock_ctx.deps.citation_manager.get_all()
        assert len(sources) == 1
        payload = json.loads(result.message)
        assert payload["results"][0]["source_id"] == sources[0].id

        # Verify context manager usage
        MockDDGS.assert_called_once()
        mock_instance.__enter__.assert_called_once()
        mock_instance.__exit__.assert_called_once()

        # Verify arguments
        mock_instance.text.assert_called_with("test", timelimit=None, max_results=5)


async def test_ddgs_category_dispatch(clean_env, mock_ctx):
    with patch("ddgs.DDGS") as MockDDGS:
        mock_instance = MockDDGS.return_value
        mock_instance.__enter__.return_value = mock_instance

        tool = WebSearchTool()

        # News
        mock_instance.news.return_value = []
        await tool.forward(mock_ctx, query="news test", categories="news")
        mock_instance.news.assert_called_once()

        # Images
        mock_instance.images.return_value = []
        await tool.forward(mock_ctx, query="image test", categories="images")
        mock_instance.images.assert_called_once()


async def test_searxng_search(clean_env, mock_ctx):
    os.environ["SEARXNG_BASE_URL"] = "http://localhost:8080"
    with patch("httpx.AsyncClient") as MockClient:
        mock_client_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = (
            '{"results": [{"title": "SearXNG", "url": "http://s.me", "content": "c"}]}'
        )
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        MockClient.return_value = mock_client_instance

        tool = WebSearchTool()

        await tool.forward(mock_ctx, query="test")

        mock_client_instance.get.assert_awaited_with(
            "/search", params={"q": "test", "format": "json", "page": 1}
        )


async def test_searxng_fallback_to_ddgs(clean_env, mock_ctx):
    os.environ["SEARXNG_BASE_URL"] = "http://localhost:8080"
    with patch("httpx.AsyncClient") as MockClient:
        mock_client_instance = MagicMock()

        # Mock 403 Forbidden
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        MockClient.return_value = mock_client_instance

        with patch("ddgs.DDGS") as MockDDGS:
            mock_instance = MockDDGS.return_value
            mock_instance.__enter__.return_value = mock_instance
            mock_instance.text.return_value = [
                {"title": "Fallback", "href": "url", "body": "b"}
            ]

            tool = WebSearchTool()
            result = await tool.forward(mock_ctx, query="test", max_results=5)

            assert "Fallback" in result.message
            # Verify DDGS called with forwarded params
            mock_instance.text.assert_called_with("test", timelimit=None, max_results=5)
