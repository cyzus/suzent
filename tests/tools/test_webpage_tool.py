from unittest.mock import MagicMock

import pytest

from suzent.tools.webpage_tool import WebpageTool


@pytest.fixture
def mock_ctx():
    from suzent.core.citation_manager import CitationManager

    ctx = MagicMock()
    ctx.deps.citation_manager = CitationManager()
    return ctx


class _DummyCrawlerResult:
    def __init__(self, markdown):
        self.markdown = markdown


class _DummyCrawler:
    def __init__(self, markdown):
        self._markdown = markdown
        self.arun_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def arun(self, url):
        self.arun_calls.append(url)
        return _DummyCrawlerResult(self._markdown)


@pytest.mark.asyncio
async def test_forward_returns_markdown(monkeypatch, mock_ctx):
    dummy = _DummyCrawler("# title")

    monkeypatch.setattr("suzent.tools.webpage_tool.AsyncWebCrawler", lambda: dummy)

    result = await WebpageTool().forward(mock_ctx, "https://example.com")

    assert result.success
    assert dummy.arun_calls == ["https://example.com"]

    # The fetched page is registered as a citable source, titled from its heading.
    sources = mock_ctx.deps.citation_manager.get_all()
    assert len(sources) == 1
    assert sources[0].title == "title"
    assert sources[0].url == "https://example.com"

    # The content is labelled with its src id so the model can cite it inline,
    # and the original markdown is preserved after the label.
    assert result.message.startswith(f"[{sources[0].id}] title")
    assert "# title" in result.message


@pytest.mark.asyncio
async def test_forward_handles_empty_result(monkeypatch, mock_ctx):
    dummy = _DummyCrawler(None)

    monkeypatch.setattr("suzent.tools.webpage_tool.AsyncWebCrawler", lambda: dummy)

    result = await WebpageTool().forward(mock_ctx, "https://example.com")

    assert not result.success
    # A failed fetch registers no source.
    assert mock_ctx.deps.citation_manager.get_all() == []
    assert result.message == "Unable to retrieve content from the specified URL."
