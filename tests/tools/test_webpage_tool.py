import pytest

from suzent.tools.webpage_tool import WebpageTool


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
async def test_forward_returns_markdown(monkeypatch):
    dummy = _DummyCrawler("# title")

    monkeypatch.setattr("suzent.tools.webpage_tool.AsyncWebCrawler", lambda: dummy)

    result = await WebpageTool().forward("https://example.com")

    assert result.success
    assert result.message == "# title"
    assert dummy.arun_calls == ["https://example.com"]


@pytest.mark.asyncio
async def test_forward_handles_empty_result(monkeypatch):
    dummy = _DummyCrawler(None)

    monkeypatch.setattr("suzent.tools.webpage_tool.AsyncWebCrawler", lambda: dummy)

    result = await WebpageTool().forward("https://example.com")

    assert not result.success
    assert result.message == "Unable to retrieve content from the specified URL."
