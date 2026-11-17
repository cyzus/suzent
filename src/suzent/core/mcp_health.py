"""Keep one unreachable MCP server from failing every chat.

pydantic-ai connects every toolset before a run, so a single server that
cannot start (a bad command, an expired sign-in, an unreachable host, a
package still downloading on first launch) would fail the whole run. Every
MCP toolset is wrapped by :func:`tolerant`: a server that cannot connect
offers no tools for that run and records why, and the next run tries again.

Stdio servers launched through ``uvx``/``npx`` can spend minutes installing
their package the first time. :func:`warm_up` does that install in the
background, and runs skip the server until it is ready instead of waiting.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, MutableMapping
from typing import Any, Literal

from suzent.logger import get_logger

logger = get_logger(__name__)

#: How long a run waits for a server that is not warming to connect.
URL_CONNECT_TIMEOUT = 15.0
STDIO_CONNECT_TIMEOUT = 30.0

State = Literal["warming", "error"]

#: Why each user-added server last failed to connect, by server name.
_errors: dict[str, str] = {}
#: Servers whose first launch is still installing in the background.
_warming: set[str] = set()
#: Keeps background warm-up tasks referenced until they finish.
_tasks: dict[str, asyncio.Task[None]] = {}


def describe_error(exc: BaseException) -> str:
    from suzent.core.mcp_oauth import _describe_error

    return _describe_error(exc)


def status() -> dict[str, dict[str, str]]:
    """``{name: {"state": "warming"|"error", "error"?: str}}`` for servers not ready."""
    result: dict[str, dict[str, str]] = {
        name: {"state": "error", "error": error} for name, error in _errors.items()
    }
    for name in _warming:
        result[name] = {"state": "warming"}
    return result


def is_warming(name: str) -> bool:
    return name in _warming


def forget(name: str) -> None:
    _errors.pop(name, None)


def tolerant(
    toolset: Any,
    key: str,
    errors: MutableMapping[str, str],
    *,
    skip: Callable[[], bool] | None = None,
    connect_timeout: float | None = None,
) -> Any:
    """Wrap ``toolset`` so a server that can't connect offers no tools.

    ``errors`` receives why ``key`` last failed, and loses it once it
    connects. While ``skip()`` is true, runs don't try to connect at all.
    """
    from pydantic_ai.toolsets import WrapperToolset

    class TolerantToolset(WrapperToolset):
        """Shared by every run of the cached agent, so entries are counted.

        Like ``MCPToolset`` itself, the first entry connects and the last
        exit disconnects; runs entering while it is connected share the
        connection, and while a connection attempt failed they get no tools.
        """

        _entries: int = 0
        # None while not entered; whether the first entry's connect worked.
        _connected: bool | None = None
        _lock: asyncio.Lock | None = None

        def _guard(self) -> asyncio.Lock:
            if self._lock is None:
                self._lock = asyncio.Lock()
            return self._lock

        async def __aenter__(self):
            async with self._guard():
                if self._entries == 0:
                    self._connected = await self._connect()
                self._entries += 1
            return self

        async def _connect(self) -> bool:
            if skip is not None and skip():
                logger.debug("MCP server {} is still starting; skipped this run", key)
                return False
            try:
                # ``asyncio.timeout`` rather than ``wait_for``: the connection
                # must open in this task, since the run closes it from here too.
                async with asyncio.timeout(connect_timeout):
                    await self.wrapped.__aenter__()
            except TimeoutError:
                self._fail(f"Timed out after {connect_timeout:.0f}s")
                return False
            except Exception as exc:
                self._fail(describe_error(exc))
                return False
            errors.pop(key, None)
            return True

        async def __aexit__(self, *args: Any):
            async with self._guard():
                if self._entries == 0:
                    return None
                self._entries -= 1
                if self._entries > 0:
                    return None
                connected, self._connected = self._connected, None
                if not connected:
                    return None
                try:
                    return await self.wrapped.__aexit__(*args)
                except Exception as exc:
                    logger.debug("Closing MCP server {} failed: {}", key, exc)
                    return None

        async def get_tools(self, ctx):
            if self._connected is False:
                return {}
            try:
                return await self.wrapped.get_tools(ctx)
            except Exception as exc:
                self._fail(describe_error(exc))
                return {}

        async def get_instructions(self, ctx):
            if self._connected is False:
                return None
            try:
                return await super().get_instructions(ctx)
            except Exception as exc:
                self._fail(describe_error(exc))
                return None

        def _fail(self, error: str) -> None:
            errors[key] = error
            logger.warning("MCP server {} unavailable: {}", key, error)

    return TolerantToolset(toolset)


def tolerant_server(toolset: Any, name: str, *, stdio: bool) -> Any:
    """:func:`tolerant` for a user-added server, skipped while it warms up."""
    return tolerant(
        toolset,
        name,
        _errors,
        skip=lambda: name in _warming,
        connect_timeout=STDIO_CONNECT_TIMEOUT if stdio else URL_CONNECT_TIMEOUT,
    )


def warm_up(entries: Iterable[dict[str, Any]]) -> None:
    """Start installing each enabled stdio server's package in the background.

    Runs skip a server while it warms up; once its probe succeeds the next
    run connects to it from the local cache, well within the run timeout.
    """
    for entry in entries:
        name = entry.get("name")
        if (
            not name
            or entry.get("type") != "stdio"
            or not entry.get("enabled")
            or name in _tasks
        ):
            continue
        _warming.add(name)
        _tasks[name] = asyncio.create_task(_warm(name, entry), name=f"mcp-warm:{name}")


async def _warm(name: str, entry: dict[str, Any]) -> None:
    from suzent.agent_manager import probe_mcp_server

    try:
        # Long enough for a cold ``uvx``/``npx`` install on a slow connection.
        result = await probe_mcp_server(entry, timeout=600.0)
        if result.get("ok"):
            _errors.pop(name, None)
            logger.info("MCP server {} is ready", name)
        else:
            _errors[name] = result.get("error") or "Connection failed"
            logger.warning("MCP server {} failed to start: {}", name, _errors[name])
    except Exception as exc:
        _errors[name] = describe_error(exc)
        logger.warning("MCP server {} failed to start: {}", name, _errors[name])
    finally:
        _warming.discard(name)
        _tasks.pop(name, None)
