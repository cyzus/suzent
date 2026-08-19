"""Async newline-delimited JSON-RPC client for local ACP v1 agents."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from typing import Any

NotificationHandler = Callable[[str, dict[str, Any]], Awaitable[None] | None]
# Given the request params, returns the ACP `outcome` payload.
PermissionHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

# ACP major protocol version this client speaks.
PROTOCOL_VERSION = 1


def _client_version() -> str:
    try:
        return _pkg_version("suzent")
    except PackageNotFoundError:
        return "0"


class ACPError(RuntimeError):
    pass


class ACPClient:
    def __init__(
        self,
        command: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        notification_handler: NotificationHandler | None = None,
        permission_handler: PermissionHandler | None = None,
    ):
        self.command = command
        self.cwd = cwd
        self.env = env or {}
        self.notification_handler = notification_handler
        self.permission_handler = permission_handler
        self.process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._next_id = 1
        self._write_lock = asyncio.Lock()
        self.stderr_lines: list[str] = []
        self._stderr_task: asyncio.Task | None = None
        self._reverse_tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        if self.process and self.process.returncode is None:
            return
        if not self.command:
            raise ACPError("ACP command is empty")
        process_env = os.environ.copy()
        process_env.update(self.env)

        # POSIX systems: create a new process group/session
        start_new_session = not os.name == "nt"

        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            cwd=self.cwd,
            env=process_env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=start_new_session,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._read_stderr())

    async def initialize(self) -> dict[str, Any]:
        """Perform the ACP handshake. Must be the first call on a connection."""
        result = await self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "clientInfo": {"name": "suzent", "version": _client_version()},
                "clientCapabilities": {
                    "fs": {"readTextFile": False, "writeTextFile": False}
                },
            },
        )
        return result if isinstance(result, dict) else {}

    async def request(
        self, method: str, params: dict[str, Any] | None = None, timeout: float = 120.0
    ) -> Any:
        if not self.process or self.process.returncode is not None:
            raise ACPError("ACP process is not running")
        request_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending[request_id] = future
        await self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or {},
            }
        )
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(request_id, None)

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    async def new_session(
        self, cwd: str, mcp_servers: list | None = None
    ) -> dict[str, Any]:
        result = await self.request(
            "session/new", {"cwd": cwd, "mcpServers": mcp_servers or []}
        )
        return result if isinstance(result, dict) else {}

    async def load_session(
        self, session_id: str, cwd: str, mcp_servers: list | None = None
    ) -> dict[str, Any]:
        result = await self.request(
            "session/load",
            {"sessionId": session_id, "cwd": cwd, "mcpServers": mcp_servers or []},
        )
        return result if isinstance(result, dict) else {}

    async def prompt(self, session_id: str, text: str) -> dict[str, Any]:
        result = await self.request(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]},
            timeout=3600.0,
        )
        return result if isinstance(result, dict) else {}

    async def cancel(self, session_id: str) -> None:
        await self.notify("session/cancel", {"sessionId": session_id})

    async def close(self) -> None:
        for task in list(self._reverse_tasks):
            if not task.done():
                task.cancel()
        self._reverse_tasks.clear()
        process = self.process
        if process and process.returncode is None:
            # Cancel reader tasks first
            for task in (self._reader_task, self._stderr_task):
                if task and not task.done():
                    task.cancel()

            try:
                if process.stdin:
                    process.stdin.close()
                await asyncio.wait_for(process.wait(), timeout=1.5)
            except (asyncio.TimeoutError, Exception):
                import signal

                if os.name != "nt":
                    try:
                        # Send signal to process group
                        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    except ProcessLookupError:
                        try:
                            process.terminate()
                        except ProcessLookupError:
                            pass
                else:
                    try:
                        process.terminate()
                    except ProcessLookupError:
                        pass

                try:
                    await asyncio.wait_for(process.wait(), timeout=1.5)
                except (asyncio.TimeoutError, Exception):
                    if os.name != "nt":
                        try:
                            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                        except ProcessLookupError:
                            try:
                                process.kill()
                            except ProcessLookupError:
                                pass
                    else:
                        try:
                            process.kill()
                        except ProcessLookupError:
                            pass
                    await process.wait()

        # Ensure tasks are cleared/gathered
        for task in (self._reader_task, self._stderr_task):
            if task:
                try:
                    await asyncio.wait_for(task, timeout=0.1)
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                    pass
        self.process = None

    async def _send(self, payload: dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            raise ACPError("ACP stdin is unavailable")
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        async with self._write_lock:
            self.process.stdin.write(data.encode("utf-8"))
            await self.process.stdin.drain()

    async def _read_loop(self) -> None:
        assert self.process and self.process.stdout
        try:
            while line := await self.process.stdout.readline():
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "id" in message and ("result" in message or "error" in message):
                    future = self._pending.get(message["id"])
                    if future and not future.done():
                        if "error" in message:
                            future.set_exception(ACPError(str(message["error"])))
                        else:
                            future.set_result(message.get("result"))
                    continue
                if "method" in message and "id" in message:
                    await self._handle_reverse_request(message)
                    continue
                handler = self.notification_handler
                if handler and isinstance(message.get("method"), str):
                    result = handler(message["method"], message.get("params") or {})
                    if asyncio.iscoroutine(result):
                        await result
        finally:
            error = ACPError("ACP process exited")
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(error)

    async def _handle_reverse_request(self, message: dict[str, Any]) -> None:
        method = str(message.get("method") or "")
        if method != "session/request_permission":
            await self._send(
                {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "error": {
                        "code": -32601,
                        "message": f"Unsupported client method: {method}",
                    },
                }
            )
            return
        if self.permission_handler is None:
            # No relay configured: fail closed rather than granting silently.
            await self._send(
                {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": {"outcome": {"outcome": "cancelled"}},
                }
            )
            return
        # Deciding can take as long as a human takes. Answer on a side task so the
        # read loop keeps draining session/update notifications meanwhile —
        # awaiting inline here would deadlock the whole turn.
        task = asyncio.create_task(
            self._resolve_permission(message["id"], message.get("params") or {})
        )
        self._reverse_tasks.add(task)
        task.add_done_callback(self._reverse_tasks.discard)

    async def _resolve_permission(
        self, request_id: Any, params: dict[str, Any]
    ) -> None:
        try:
            outcome = await self.permission_handler(params)
        except asyncio.CancelledError:
            raise
        except Exception:
            outcome = {"outcome": {"outcome": "cancelled"}}
        try:
            await self._send({"jsonrpc": "2.0", "id": request_id, "result": outcome})
        except Exception:
            # Process already gone; nothing to answer.
            pass

    async def _read_stderr(self) -> None:
        assert self.process and self.process.stderr
        while line := await self.process.stderr.readline():
            self.stderr_lines.append(line.decode("utf-8", errors="replace").rstrip())
            if len(self.stderr_lines) > 100:
                del self.stderr_lines[:-100]
