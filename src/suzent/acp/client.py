"""Async newline-delimited JSON-RPC client for local ACP v1 agents."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections.abc import Awaitable, Callable
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from typing import Any

NotificationHandler = Callable[[str, dict[str, Any]], Awaitable[None] | None]
# Given the request params, returns the ACP `outcome` payload.
PermissionHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

# ACP major protocol version this client speaks.
PROTOCOL_VERSION = 1

# How much trailing stderr to quote when an agent process dies.
_EXIT_DETAIL_CHARS = 400


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

        # Resolve the executable to its full path.  On Windows,
        # ``create_subprocess_exec`` calls ``CreateProcessW`` which does NOT
        # search for ``.cmd`` / ``.bat`` wrappers (only ``.exe``).  Tools like
        # ``npx``, ``node``, and ``gemini`` are often installed as ``.cmd``
        # shims by npm/installers, so an unresolved bare name fails with
        # ``[WinError 2] The system cannot find the specified file``.
        # ``shutil.which`` honours PATHEXT on Windows and returns the full
        # path including the extension, which ``CreateProcessW`` can execute.
        cmd = list(self.command)
        resolved = shutil.which(cmd[0])
        if resolved:
            cmd[0] = resolved

        # POSIX systems: create a new process group/session
        start_new_session = not os.name == "nt"

        extra: dict[str, Any] = {}
        if os.name == "nt":
            extra["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.cwd,
            env=process_env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=start_new_session,
            **extra,
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
            if any(not future.done() for future in self._pending.values()):
                error = await self._exit_error()
                for future in self._pending.values():
                    if not future.done():
                        future.set_exception(error)

    async def _exit_error(self) -> ACPError:
        """Explain an exit using whatever the agent printed on the way out.

        A bare "ACP process exited" gives the user nothing to act on -- a bad
        command line, a missing login, and a crash all look identical.
        """
        # stdout EOF can beat the stderr drain, so give the reader a moment to
        # finish; otherwise the agent's own complaint is lost to a race.
        if self._stderr_task is not None and not self._stderr_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._stderr_task), timeout=1.0)
            except (Exception, asyncio.CancelledError):
                # Timing out or being cancelled here only means we stop waiting
                # for more stderr; whatever is buffered is still worth saying.
                pass
        code = self.process.returncode if self.process else None
        if code is None and self.process is not None:
            # stdout EOF arrives before the child is reaped, so wait briefly
            # for the real exit status instead of reporting none at all.
            try:
                code = await asyncio.wait_for(self.process.wait(), timeout=0.5)
            except (Exception, asyncio.CancelledError):
                code = None
        detail = " | ".join(line for line in self.stderr_lines[-5:] if line.strip())
        # A usage dump can run for pages; the tail carries the actual complaint.
        if len(detail) > _EXIT_DETAIL_CHARS:
            detail = "..." + detail[-_EXIT_DETAIL_CHARS:]
        prefix = (
            "ACP process exited"
            if code is None
            else f"ACP process exited (code {code})"
        )
        return ACPError(f"{prefix}: {detail}" if detail else prefix)

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
