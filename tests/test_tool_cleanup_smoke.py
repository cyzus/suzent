from types import SimpleNamespace

import pytest

from suzent.tools.ask_question_tool import AskQuestionTool, QuestionItem
from suzent.tools.filesystem.glob_tool import GlobTool
from suzent.tools.filesystem.grep_tool import GrepTool
from suzent.tools.memory_tools import MemoryBlockUpdateTool, MemorySearchTool
from suzent.tools.planning_tool import PlanningTool
from suzent.tools.render_ui_tool import RenderUITool
from suzent.tools.webpage_tool import WebpageTool
from suzent.tools.websearch_tool import WebSearchTool


class _DummyResolver:
    def __init__(self, sandbox_enabled=False):
        self.sandbox_enabled = sandbox_enabled
        self.find_files_calls = []

    def find_files(self, pattern, path):
        self.find_files_calls.append((pattern, path))
        return []


class _DummyMemoryManager:
    async def search_memories(self, query, limit, chat_id, user_id):
        return [
            {
                "content": "remember the test",
                "created_at": None,
                "metadata": {"tags": ["test"]},
                "similarity": 0.91,
                "importance": 0.7,
            }
        ]

    async def get_core_memory(self, chat_id, user_id):
        return {"persona": "old", "user": "", "facts": "", "context": ""}

    async def update_memory_block(self, label, content, chat_id, user_id):
        return True


class _DummyGrepResolver:
    def __init__(self, files, sandbox_enabled=False):
        self._files = files
        self.sandbox_enabled = sandbox_enabled

    def find_files(self, pattern, path):
        return self._files


@pytest.mark.asyncio
async def test_glob_tool_returns_structured_result(tmp_path):
    tool = GlobTool()
    tool._resolver = _DummyResolver()
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            chat_id="chat-1",
            sandbox_enabled=False,
            custom_volumes=[],
            workspace_root=str(tmp_path),
            path_resolver=None,
        )
    )

    result = tool.forward(ctx, pattern="*.py", path=str(tmp_path))

    assert result.success
    assert result.metadata["match_count"] == 0


@pytest.mark.asyncio
async def test_glob_tool_no_match_includes_recursive_hint(tmp_path):
    tool = GlobTool()
    tool._resolver = _DummyResolver()
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            chat_id="chat-1",
            sandbox_enabled=False,
            custom_volumes=[],
            workspace_root=str(tmp_path),
            path_resolver=None,
        )
    )

    result = tool.forward(ctx, pattern="*edit*.py", path=str(tmp_path))

    assert result.success
    assert "non-recursive" in result.message
    assert "**/*edit*.py" in result.message


@pytest.mark.asyncio
async def test_grep_tool_skips_large_files(tmp_path):
    large_file = tmp_path / "huge.py"
    large_file.write_bytes(b"a" * (2 * 1024 * 1024 + 10))

    tool = GrepTool()
    tool._resolver = _DummyGrepResolver([(large_file, str(large_file))])
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            chat_id="chat-1",
            sandbox_enabled=False,
            custom_volumes=[],
            workspace_root=str(tmp_path),
            path_resolver=tool._resolver,
        )
    )

    result = tool.forward(ctx, pattern="def edit_file", path=str(tmp_path))

    assert result.success
    assert result.metadata["scanned_files"] == 0
    assert result.metadata["skipped_large_files"] == 1


@pytest.mark.asyncio
async def test_grep_tool_reports_capped_scan(tmp_path):
    files = []
    for i in range(5001):
        p = tmp_path / f"f_{i}.py"
        p.write_text("print('x')\n", encoding="utf-8")
        files.append((p, str(p)))

    tool = GrepTool()
    tool._resolver = _DummyGrepResolver(files)
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            chat_id="chat-1",
            sandbox_enabled=False,
            custom_volumes=[],
            workspace_root=str(tmp_path),
            path_resolver=tool._resolver,
        )
    )

    result = tool.forward(ctx, pattern="def edit_file", path=str(tmp_path))

    assert result.success
    assert result.metadata["capped"] is True
    assert "scan capped" in result.message


@pytest.mark.asyncio
async def test_memory_tools_return_structured_results():
    manager = _DummyMemoryManager()
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            memory_manager=manager,
            user_id="user-1",
            chat_id="chat-1",
        )
    )

    search_result = await MemorySearchTool().forward(ctx, query="test", limit=5)
    assert search_result.success
    assert search_result.metadata["match_count"] == 1

    update_result = await MemoryBlockUpdateTool().forward(
        ctx,
        block="persona",
        operation="append",
        content="new fact",
    )
    assert update_result.success
    assert update_result.metadata["block"] == "persona"


@pytest.mark.asyncio
async def test_planning_tool_rejects_unknown_action():
    tool = PlanningTool()
    ctx = SimpleNamespace(deps=SimpleNamespace(chat_id="planning_session_temp"))

    result = tool.forward(ctx, action="oops")

    assert not result.success
    assert "Invalid action" in result.message


@pytest.mark.asyncio
async def test_ask_question_tool_headless_returns_result():
    tool = AskQuestionTool()
    ctx = SimpleNamespace(deps=SimpleNamespace(chat_id="chat-1", a2ui_queue=None))

    result = await tool.forward(
        ctx,
        questions=[QuestionItem(question="Preferred language?")],
    )

    assert result.success
    assert result.metadata["questions"][0]["question"] == "Preferred language?"


@pytest.mark.asyncio
async def test_render_ui_tool_headless_returns_result():
    tool = RenderUITool()
    ctx = SimpleNamespace(deps=SimpleNamespace(a2ui_queue=None))

    result = await tool.forward(
        ctx,
        surface_id="test-surface",
        component={"type": "text", "content": "hello"},
    )

    assert result.success
    assert result.metadata["surface_id"] == "test-surface"


@pytest.mark.asyncio
async def test_webpage_tool_wraps_result(monkeypatch):
    class _DummyResult:
        markdown = "# title"

    class _DummyCrawler:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def arun(self, url):
            return _DummyResult()

    monkeypatch.setattr(
        "suzent.tools.webpage_tool.AsyncWebCrawler", lambda: _DummyCrawler()
    )

    result = await WebpageTool().forward("https://example.com")

    assert result.success
    assert result.metadata["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_websearch_tool_can_be_mocked(monkeypatch):
    tool = WebSearchTool()

    async def fake_ddgs(query, category, max_results, time_range, page):
        from suzent.tools.base import ToolResult

        return ToolResult.success_result(
            "ok",
            metadata={
                "query": query,
                "category": category,
                "max_results": max_results,
                "time_range": time_range,
                "page": page,
            },
        )

    monkeypatch.setattr(tool, "_search_with_ddgs", fake_ddgs)

    result = await tool.forward(
        query="test", categories="general", max_results=3, time_range="day", page=1
    )

    assert result.success
    assert result.metadata["query"] == "test"
