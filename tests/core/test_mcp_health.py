import asyncio

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset

from suzent.core import mcp_health


@pytest.fixture(autouse=True)
def _clean_state():
    mcp_health._errors.clear()
    mcp_health._warming.clear()
    mcp_health._tasks.clear()
    yield
    mcp_health._errors.clear()
    mcp_health._warming.clear()
    mcp_health._tasks.clear()


class _Broken(FunctionToolset):
    entered = 0

    async def __aenter__(self):
        type(self).entered += 1
        raise RuntimeError(
            "Client failed to connect: Failed to initialize server session"
        )


class _Hangs(FunctionToolset):
    async def __aenter__(self):
        await asyncio.sleep(60)
        return self


def _working_toolset() -> FunctionToolset:
    tools = FunctionToolset()

    @tools.tool_plain
    def ping() -> str:
        return "pong"

    return tools


async def test_a_broken_server_does_not_fail_the_run():
    broken = mcp_health.tolerant_server(_Broken(), "broken", stdio=True)
    agent = Agent(TestModel(), toolsets=[broken.prefixed("broken"), _working_toolset()])

    result = await agent.run("hi")

    assert isinstance(result.output, str)
    assert "Failed to initialize" in mcp_health.status()["broken"]["error"]


async def test_a_server_that_never_answers_times_out():
    hangs = mcp_health.tolerant(
        _Hangs(), "slow", mcp_health._errors, connect_timeout=0.01
    )

    async with hangs:
        assert await hangs.get_tools(None) == {}

    assert mcp_health.status()["slow"] == {
        "state": "error",
        "error": "Timed out after 0s",
    }


async def test_runs_skip_a_server_while_it_warms_up():
    _Broken.entered = 0
    mcp_health._warming.add("cold")
    wrapper = mcp_health.tolerant_server(_Broken(), "cold", stdio=True)

    async with wrapper:
        assert await wrapper.get_tools(None) == {}

    assert _Broken.entered == 0
    assert mcp_health.status() == {"cold": {"state": "warming"}}


async def test_warm_up_marks_a_stdio_server_ready(monkeypatch):
    from suzent import agent_manager

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_probe(entry, timeout=None):
        started.set()
        await release.wait()
        return {"ok": True, "count": 1, "tools": []}

    monkeypatch.setattr(agent_manager, "probe_mcp_server", fake_probe)
    mcp_health._errors["local"] = "old failure"

    mcp_health.warm_up(
        [
            {"name": "local", "type": "stdio", "command": "uvx", "enabled": True},
            {"name": "off", "type": "stdio", "command": "uvx", "enabled": False},
            {"name": "remote", "type": "url", "url": "https://x", "enabled": True},
        ]
    )
    await started.wait()
    assert mcp_health.is_warming("local")
    assert set(mcp_health._tasks) == {"local"}

    release.set()
    await mcp_health._tasks["local"]

    assert mcp_health.status() == {}


async def test_warm_up_records_why_a_server_failed(monkeypatch):
    from suzent import agent_manager

    async def fake_probe(entry, timeout=None):
        return {"ok": False, "error": "command not found: uvx"}

    monkeypatch.setattr(agent_manager, "probe_mcp_server", fake_probe)

    mcp_health.warm_up([{"name": "local", "type": "stdio", "enabled": True}])
    await mcp_health._tasks["local"]

    assert mcp_health.status() == {
        "local": {"state": "error", "error": "command not found: uvx"}
    }
