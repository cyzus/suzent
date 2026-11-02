from unittest.mock import MagicMock

import pytest
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import BinaryContent

from suzent.tools.webpage_tool import WebpageTool


@pytest.fixture
def mock_ctx():
    from suzent.core.citation_manager import CitationManager

    ctx = MagicMock()
    ctx.deps.citation_manager = CitationManager()
    return ctx


class _DummyFetcher:
    """Stands in for pydantic-ai's WebFetchLocalTool: an async callable on a URL."""

    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.calls = []

    async def __call__(self, url):
        self.calls.append(url)
        if self._error is not None:
            raise self._error
        return self._result


def _install(monkeypatch, fetcher):
    monkeypatch.setattr("suzent.tools.webpage_tool._make_fetcher", lambda: fetcher)


LONG_BODY = "# heading\n\n" + "Real article text. " * 20


@pytest.mark.asyncio
async def test_forward_returns_markdown(monkeypatch, mock_ctx):
    fetcher = _DummyFetcher(
        {
            "url": "https://example.com",
            "title": "Page &#8212; Title",
            "content": LONG_BODY,
        }
    )
    _install(monkeypatch, fetcher)

    result = await WebpageTool().forward(mock_ctx, "https://example.com")

    assert result.success
    assert fetcher.calls == ["https://example.com"]

    # The fetched page is registered as a citable source, titled from <title>.
    sources = mock_ctx.deps.citation_manager.get_all()
    assert len(sources) == 1
    assert sources[0].title == "Page — Title"
    assert sources[0].url == "https://example.com"

    # The content is labelled with its src id so the model can cite it inline,
    # and the original markdown is preserved after the label.
    assert result.message.startswith(f"[{sources[0].id}] Page — Title")
    assert "# heading" in result.message
    assert "browser tool" not in result.message


@pytest.mark.asyncio
async def test_forward_falls_back_to_heading_title(monkeypatch, mock_ctx):
    _install(
        monkeypatch,
        _DummyFetcher(
            {"url": "https://example.com", "title": "", "content": LONG_BODY}
        ),
    )

    result = await WebpageTool().forward(mock_ctx, "https://example.com")

    assert result.success
    assert mock_ctx.deps.citation_manager.get_all()[0].title == "heading"


@pytest.mark.asyncio
async def test_forward_flags_thin_pages(monkeypatch, mock_ctx):
    _install(
        monkeypatch,
        _DummyFetcher(
            {"url": "https://example.com", "title": "", "content": "Enable JS"}
        ),
    )

    result = await WebpageTool().forward(mock_ctx, "https://example.com")

    assert result.success
    assert "browser tool" in result.message


@pytest.mark.asyncio
async def test_forward_handles_empty_result(monkeypatch, mock_ctx):
    _install(
        monkeypatch,
        _DummyFetcher({"url": "https://example.com", "title": "", "content": "  "}),
    )

    result = await WebpageTool().forward(mock_ctx, "https://example.com")

    assert not result.success
    # A failed fetch registers no source.
    assert mock_ctx.deps.citation_manager.get_all() == []
    assert result.message.startswith(
        "Unable to retrieve content from the specified URL."
    )


@pytest.mark.asyncio
async def test_forward_reports_fetch_errors(monkeypatch, mock_ctx):
    _install(
        monkeypatch,
        _DummyFetcher(error=ModelRetry("Failed to fetch https://example.com: 404")),
    )

    result = await WebpageTool().forward(mock_ctx, "https://example.com")

    assert not result.success
    assert "404" in result.message
    assert mock_ctx.deps.citation_manager.get_all() == []


@pytest.mark.asyncio
async def test_forward_rejects_binary_content(monkeypatch, mock_ctx):
    _install(
        monkeypatch,
        _DummyFetcher(BinaryContent(data=b"%PDF", media_type="application/pdf")),
    )

    result = await WebpageTool().forward(mock_ctx, "https://example.com/a.pdf")

    assert not result.success
    assert "application/pdf" in result.message
    assert "read_file" in result.message


@pytest.mark.asyncio
async def test_real_fetcher_blocks_local_urls(mock_ctx):
    # SSRF guard: the real pydantic-ai fetcher refuses private/loopback hosts.
    result = await WebpageTool().forward(mock_ctx, "http://127.0.0.1:1/")

    assert not result.success
    assert mock_ctx.deps.citation_manager.get_all() == []
