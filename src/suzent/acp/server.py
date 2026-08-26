"""Serve Suzent itself as an Agent Client Protocol (ACP) agent over stdio.

Suzent already speaks ACP as a *client*: ``suzent.acp.client`` drives Claude
Code, Codex, and friends as subagents. This module is the other direction. It
turns Suzent into an ACP **agent**, so any ACP client — Zed, enoxian, an editor
that implements the protocol — can drive the local geist inside its own
workspace::

    client -> agent:  initialize
    client -> agent:  session/new       (cwd = the client's workspace)
    client -> agent:  session/prompt
    agent  -> client: session/update    (message chunks, thoughts, tool calls)
    agent  -> client: session/request_permission
    client -> agent:  session/cancel

The process is a translator, not a second agent. Every turn runs on the
already-running Suzent backend over the loopback API, so an ACP session is a
real chat: it shows up in the desktop UI, shares the same memory, skills, model
config, and permission rules, and one process stays the owner of the database.

The client's ``cwd`` is bound to the session as a sandbox volume mounted at
``/mnt/workspace``, so file tools act on the client's real workspace instead of
a private project directory — which is also what makes an ACP client's own
change tracking see the edits.

See <https://agentclientprotocol.com/protocol/schema>.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from suzent.logger import get_logger

logger = get_logger(__name__)

# The ACP major version this agent implements.
PROTOCOL_VERSION = 1

# Where the client's workspace is mounted for the agent's file tools. Sandbox
# mode needs a container path; host mode uses the real cwd (see _session_config).
WORKSPACE_MOUNT = "/mnt/workspace"

# Chat config key marking a chat as owned by this surface. session/load refuses
# anything else, so a client cannot address an arbitrary local conversation by
# guessing an id.
SESSION_MARKER = "_acp_server"

# JSON-RPC 2.0 error codes.
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Suzent tool name -> ACP tool-call kind. Anything unlisted is "other", which is
# what a client renders for a tool it has no special affordance for.
_TOOL_KINDS: dict[str, str] = {
    "read_file": "read",
    "glob_search": "search",
    "grep_search": "search",
    "session_search": "search",
    "memory_search": "search",
    "write_file": "edit",
    "edit_file": "edit",
    "run_command": "execute",
    "start_command": "execute",
    "check_command": "execute",
    "stop_command": "execute",
    "skill_execute": "execute",
    "web_search": "fetch",
    "webpage_fetch": "fetch",
    "browser_action": "fetch",
}


def tool_kind(tool_name: str) -> str:
    """Return the ACP tool-call kind for a Suzent tool name."""
    return _TOOL_KINDS.get(tool_name, "other")


class ACPServerError(Exception):
    """A failure to report to the client as a JSON-RPC error."""

    def __init__(self, message: str, code: int = INTERNAL_ERROR):
        super().__init__(message)
        self.code = code


# ── Backend ───────────────────────────────────────────────────────────────────


class SuzentBackend:
    """The loopback backend surface one ACP session needs.

    Thin on purpose: the ACP layer should own protocol translation and nothing
    else, and every call here is a request to the running daemon.
    """

    def __init__(self, base_url: str | None = None):
        from suzent.client.api import SuzentAsyncClient

        self._client = SuzentAsyncClient(base_url)

    @property
    def base_url(self) -> str:
        return self._client.base_url

    async def sandbox_enabled(self) -> bool:
        """Whether turns execute in the Docker sandbox rather than on the host."""
        data = await self._client.config.get()
        preference = (data.get("userPreferences") or {}).get("sandbox_enabled")
        if isinstance(preference, bool):
            return preference
        return bool(data.get("sandboxEnabled"))

    async def create_chat(self, title: str, config: dict[str, Any]) -> str:
        chat = await self._client.chat.create_chat(
            {"title": title, "config": config, "messages": []}
        )
        chat_id = str(chat.get("id") or "")
        if not chat_id:
            raise ACPServerError("the backend returned a chat without an id")
        return chat_id

    async def get_chat(self, chat_id: str) -> dict[str, Any] | None:
        from suzent.client.base import ClientError

        try:
            return await self._client.chat.get_chat(chat_id)
        except ClientError as exc:
            logger.debug(f"[acp-server] chat {chat_id} unavailable: {exc}")
            return None

    def stream_turn(self, payload: dict[str, Any]) -> AsyncIterator[bytes]:
        # No read timeout: a turn is as long as the model needs, and the client
        # cancels through session/cancel rather than by us giving up.
        return self._client.chat.stream_message(payload, timeout=None)

    async def stop_turn(self, chat_id: str) -> None:
        from suzent.client.base import ClientError

        try:
            await self._client.chat.stop(chat_id, "cancelled by the ACP client")
        except ClientError as exc:
            # A finished stream has nothing to stop; that is not an error here.
            logger.debug(f"[acp-server] stop for {chat_id} was a no-op: {exc}")

    async def aclose(self) -> None:
        await self._client.aclose()


# ── Turn translation ──────────────────────────────────────────────────────────


@dataclass
class Update:
    """A ``session/update`` payload to forward to the client."""

    payload: dict[str, Any]


@dataclass
class Approval:
    """The backend suspended the turn awaiting a tool-call decision."""

    info: dict[str, Any]


@dataclass
class TurnError:
    """The backend reported the turn as failed."""

    message: str


TurnItem = Update | Approval | TurnError


def _text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


class TurnTranslator:
    """Translate one Suzent AG-UI SSE turn into ACP session updates.

    Stateful across chunks: SSE frames arrive split at arbitrary byte
    boundaries, and tool-call arguments stream in as deltas that only become a
    ``rawInput`` once the call is closed.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._tool_names: dict[str, str] = {}
        self._tool_args: dict[str, str] = {}
        self._announced: set[str] = set()

    def feed(self, chunk: bytes | str) -> Iterator[TurnItem]:
        text = chunk if isinstance(chunk, str) else chunk.decode("utf-8", "replace")
        self._buffer += text
        while "\n\n" in self._buffer:
            block, self._buffer = self._buffer.split("\n\n", 1)
            for line in block.splitlines():
                if not line.startswith("data: "):
                    continue
                raw = line[6:].strip()
                if not raw or raw == "[DONE]":
                    continue
                try:
                    event = json.loads(raw)
                except ValueError:
                    logger.debug(f"[acp-server] unparseable SSE payload: {raw[:120]}")
                    continue
                if isinstance(event, dict):
                    yield from self._translate(event)

    def _translate(self, event: dict[str, Any]) -> Iterator[TurnItem]:
        kind = str(event.get("type") or "")

        if kind == "TEXT_MESSAGE_CONTENT":
            if delta := str(event.get("delta") or ""):
                yield Update(
                    {
                        "sessionUpdate": "agent_message_chunk",
                        "content": _text_block(delta),
                    }
                )

        # ag-ui-protocol 0.1.13 renamed the thinking family to REASONING_*, so
        # an ACP client sees this agent's thoughts only if both are translated.
        elif kind in {
            "THINKING_TEXT_MESSAGE_CONTENT",
            "REASONING_MESSAGE_CONTENT",
            "REASONING_MESSAGE_CHUNK",
        }:
            if delta := str(event.get("delta") or ""):
                yield Update(
                    {
                        "sessionUpdate": "agent_thought_chunk",
                        "content": _text_block(delta),
                    }
                )

        elif kind == "TOOL_CALL_START":
            tool_call_id = str(event.get("toolCallId") or "")
            if not tool_call_id:
                return
            name = str(event.get("toolCallName") or "tool")
            self._tool_names[tool_call_id] = name
            self._tool_args[tool_call_id] = ""
            if tool_call_id in self._announced:
                # Resuming after an approval replays the start for a call the
                # client already knows about — that is an update, not a new call.
                yield Update(
                    {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": tool_call_id,
                        "status": "in_progress",
                    }
                )
            else:
                self._announced.add(tool_call_id)
                yield Update(
                    {
                        "sessionUpdate": "tool_call",
                        "toolCallId": tool_call_id,
                        "title": name,
                        "kind": tool_kind(name),
                        "status": "in_progress",
                    }
                )

        elif kind == "TOOL_CALL_ARGS":
            tool_call_id = str(event.get("toolCallId") or "")
            if tool_call_id:
                self._tool_args[tool_call_id] = self._tool_args.get(
                    tool_call_id, ""
                ) + str(event.get("delta") or "")

        elif kind == "TOOL_CALL_END":
            tool_call_id = str(event.get("toolCallId") or "")
            arguments = self._decode_args(tool_call_id)
            if tool_call_id and arguments is not None:
                yield Update(
                    {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": tool_call_id,
                        "rawInput": arguments,
                    }
                )

        elif kind == "TOOL_CALL_RESULT":
            tool_call_id = str(event.get("toolCallId") or "")
            if not tool_call_id:
                return
            output = _stringify(
                event.get("content")
                if event.get("content") is not None
                else event.get("output")
            )
            update: dict[str, Any] = {
                "sessionUpdate": "tool_call_update",
                "toolCallId": tool_call_id,
                "status": "completed",
            }
            if output:
                update["content"] = [
                    {"type": "content", "content": _text_block(output)}
                ]
            yield Update(update)

        elif kind in ("CUSTOM", "CUSTOM_EVENT"):
            yield from self._translate_custom(event)

        elif kind == "RUN_ERROR":
            yield TurnError(str(event.get("message") or "the turn failed"))

    def _translate_custom(self, event: dict[str, Any]) -> Iterator[TurnItem]:
        name = event.get("name")
        value = event.get("value")
        if not name and isinstance(event.get("custom"), dict):
            custom = event["custom"]
            name = custom.get("name")
            value = custom.get("value")
        if name == "tool_approval_request" and isinstance(value, dict):
            yield Approval(value)

    def _decode_args(self, tool_call_id: str) -> dict[str, Any] | None:
        raw = self._tool_args.get(tool_call_id, "").strip()
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def tool_name(self, tool_call_id: str) -> str:
        return self._tool_names.get(tool_call_id, "tool")


# ── Sessions ──────────────────────────────────────────────────────────────────


@dataclass
class Session:
    """One ACP session, backed by a Suzent chat."""

    chat_id: str
    cwd: str
    config: dict[str, Any]
    running: bool = False
    cancelled: bool = False
    seen_tool_calls: set[str] = field(default_factory=set)


def _permission_options(decision: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn the backend's offered approval actions into ACP options.

    The backend decides what may be remembered and how widely (a shell command
    prefix, a whole tool, session or global), so the options a client sees are
    exactly the authority Suzent is willing to grant — never a scope the client
    invented.
    """
    options: list[dict[str, Any]] = []
    for action in decision.get("actions") or []:
        if not isinstance(action, dict):
            continue
        action_id = str(action.get("id") or "")
        if not action_id:
            continue
        if action.get("behavior") == "deny":
            kind = "reject_once"
        elif action.get("scope") in ("session", "global"):
            kind = "allow_always"
        else:
            kind = "allow_once"
        options.append(
            {
                "optionId": action_id,
                "name": str(action.get("label") or action_id),
                "kind": kind,
            }
        )
    return options


_LEGACY_OPTIONS = [
    {"optionId": "allow_once", "name": "Allow", "kind": "allow_once"},
    {"optionId": "reject", "name": "Reject", "kind": "reject_once"},
]


class ACPAgentServer:
    """Dispatch ACP JSON-RPC messages against a Suzent backend.

    Transport-free by design: ``dispatch`` takes decoded messages and ``send``
    delivers them, so the stdio loop in :func:`serve_stdio` is a thin shell and
    the protocol is testable without a subprocess.
    """

    def __init__(
        self,
        backend: SuzentBackend,
        send: Any,
        *,
        permission_mode: str = "default",
    ):
        self._backend = backend
        self._send = send
        self._permission_mode = permission_mode
        self._sessions: dict[str, Session] = {}
        self._pending: dict[int, asyncio.Future] = {}
        self._tasks: set[asyncio.Task] = set()
        self._next_id = 1
        self._client_capabilities: dict[str, Any] = {}
        self._sandbox: bool | None = None

    # ── inbound ──────────────────────────────────────────────────────────────

    async def dispatch(self, message: dict[str, Any]) -> None:
        """Handle one decoded JSON-RPC message from the client."""
        method = message.get("method")
        if method is None:
            self._resolve_response(message)
            return

        params = message.get("params")
        params = params if isinstance(params, dict) else {}
        message_id = message.get("id")

        if message_id is None:
            await self._notification(str(method), params)
            return

        # A prompt turn runs for minutes and must not block the read loop —
        # session/cancel arrives on the same connection while it is in flight.
        if method == "session/prompt":
            self._spawn(self._prompt(message_id, params))
            return

        try:
            result = await self._request(str(method), params)
        except ACPServerError as exc:
            await self._error(message_id, exc.code, str(exc))
        except Exception as exc:  # noqa: BLE001 — protocol must not die on one call
            logger.error(f"[acp-server] {method} failed: {exc}")
            await self._error(
                message_id, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}"
            )
        else:
            await self._reply(message_id, result)

    async def _request(self, method: str, params: dict[str, Any]) -> Any:
        match method:
            case "initialize":
                return await self._initialize(params)
            case "authenticate":
                # The loopback backend is the trust boundary; nothing to do.
                return {}
            case "session/new":
                return await self._new_session(params)
            case "session/load":
                return await self._load_session(params)
            case _:
                raise ACPServerError(f"unknown method '{method}'", METHOD_NOT_FOUND)

    async def _notification(self, method: str, params: dict[str, Any]) -> None:
        if method == "session/cancel":
            session = self._sessions.get(str(params.get("sessionId") or ""))
            if session and session.running:
                session.cancelled = True
                await self._backend.stop_turn(session.chat_id)
            return
        logger.debug(f"[acp-server] ignoring notification '{method}'")

    async def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        capabilities = params.get("clientCapabilities")
        self._client_capabilities = (
            capabilities if isinstance(capabilities, dict) else {}
        )
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "agentCapabilities": {
                # A session id is a chat id, so resuming is just addressing the
                # same conversation again.
                "loadSession": True,
                "promptCapabilities": {
                    "image": False,
                    "audio": False,
                    "embeddedContext": True,
                },
            },
            "authMethods": [],
            "agentInfo": {"name": "suzent", "version": _version()},
        }

    async def _new_session(self, params: dict[str, Any]) -> dict[str, Any]:
        cwd = self._require_cwd(params)
        config = await self._session_config(cwd)
        title = f"⇄ ACP {Path(cwd).name or cwd}"
        chat_id = await self._backend.create_chat(title, config)
        self._sessions[chat_id] = Session(chat_id=chat_id, cwd=cwd, config=config)
        logger.info(f"[acp-server] session {chat_id} created (cwd={cwd})")
        return {"sessionId": chat_id}

    async def _load_session(self, params: dict[str, Any]) -> None:
        session_id = str(params.get("sessionId") or "")
        if not session_id:
            raise ACPServerError("session/load requires a sessionId", INVALID_PARAMS)
        chat = await self._backend.get_chat(session_id)
        if chat is None:
            raise ACPServerError(f"no such session '{session_id}'", INVALID_PARAMS)
        if not (chat.get("config") or {}).get(SESSION_MARKER):
            # Only conversations this surface created are ACP sessions. Local
            # chats belong to the user, not to whoever spawned this process.
            raise ACPServerError(
                f"'{session_id}' is not an ACP session", INVALID_PARAMS
            )

        cwd = self._require_cwd(params) if params.get("cwd") else ""
        stored = (chat.get("config") or {}).get(SESSION_MARKER) or {}
        cwd = cwd or str(stored.get("cwd") or "")
        config = await self._session_config(cwd) if cwd else dict(chat["config"])
        self._sessions[session_id] = Session(chat_id=session_id, cwd=cwd, config=config)

        for update in _history_updates(chat.get("messages") or []):
            await self._update(session_id, update)
        logger.info(f"[acp-server] session {session_id} loaded (cwd={cwd})")
        return None

    # ── the turn ─────────────────────────────────────────────────────────────

    async def _prompt(self, message_id: Any, params: dict[str, Any]) -> None:
        session_id = str(params.get("sessionId") or "")
        session = self._sessions.get(session_id)
        if session is None:
            await self._error(
                message_id, INVALID_PARAMS, f"no such session '{session_id}'"
            )
            return
        if session.running:
            await self._error(
                message_id, INVALID_REQUEST, "a turn is already running in this session"
            )
            return

        text = _prompt_text(params.get("prompt"))
        if not text:
            await self._error(message_id, INVALID_PARAMS, "the prompt carries no text")
            return

        session.running = True
        session.cancelled = False
        try:
            stop_reason = await self._run_turn(session, text)
        except ACPServerError as exc:
            await self._error(message_id, exc.code, str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[acp-server] turn failed in {session_id}: {exc}")
            await self._error(
                message_id, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}"
            )
        else:
            await self._reply(message_id, {"stopReason": stop_reason})
        finally:
            session.running = False

    async def _run_turn(self, session: Session, text: str) -> str:
        """Stream turns until the backend stops asking for approvals.

        A suspended tool call ends the SSE stream; the turn continues by posting
        the client's decisions back as ``resume_approvals``. That loop is what
        makes an ACP permission request a real gate rather than a notification.
        """
        message = text
        resume_approvals: list[dict[str, Any]] = []
        failure: str | None = None

        while True:
            payload: dict[str, Any] = {
                "message": message,
                "chat_id": session.chat_id,
                "stream": True,
                "config": session.config,
            }
            if resume_approvals:
                payload["resume_approvals"] = resume_approvals

            translator = TurnTranslator()
            pending: list[dict[str, Any]] = []
            async for chunk in self._backend.stream_turn(payload):
                if session.cancelled:
                    break
                for item in translator.feed(chunk):
                    match item:
                        case Update(payload=update):
                            await self._update(session.chat_id, update)
                        case Approval(info=info):
                            pending.append(info)
                        case TurnError(message=error):
                            failure = error

            if session.cancelled:
                return "cancelled"
            if failure:
                raise ACPServerError(failure)
            if not pending:
                return "end_turn"

            resume_approvals = []
            for request in pending:
                decision = await self._ask_permission(session, request, translator)
                if decision is None:
                    return "cancelled"
                resume_approvals.append(decision)
            # Resuming carries decisions, not a new user message.
            message = ""

    async def _ask_permission(
        self,
        session: Session,
        request: dict[str, Any],
        translator: TurnTranslator,
    ) -> dict[str, Any] | None:
        """Ask the client to decide one tool call. ``None`` means cancelled."""
        approval_id = str(request.get("approvalId") or "")
        tool_call_id = str(request.get("toolCallId") or approval_id)
        tool_name = str(request.get("toolName") or translator.tool_name(tool_call_id))
        decision = request.get("decision")
        decision = decision if isinstance(decision, dict) else {}
        options = _permission_options(decision) or list(_LEGACY_OPTIONS)

        tool_call: dict[str, Any] = {
            "toolCallId": tool_call_id,
            "title": tool_name,
            "kind": tool_kind(tool_name),
            "status": "pending",
        }
        if isinstance(request.get("args"), dict):
            tool_call["rawInput"] = request["args"]

        result = await self._call(
            "session/request_permission",
            {
                "sessionId": session.chat_id,
                "toolCall": tool_call,
                "options": options,
            },
        )
        outcome = (result or {}).get("outcome") or {}
        if outcome.get("outcome") != "selected":
            await self._backend.stop_turn(session.chat_id)
            return None

        option_id = str(outcome.get("optionId") or "")
        chosen = next((o for o in options if o["optionId"] == option_id), None)
        if chosen is None:
            raise ACPServerError(f"the client selected unknown option '{option_id}'")

        resolution: dict[str, Any] = {
            "request_id": approval_id or tool_call_id,
            "tool_call_id": tool_call_id,
            "approved": chosen["kind"] != "reject_once",
        }
        if decision.get("actions"):
            # Let the backend resolve the offered action, so "always allow"
            # persists the rule it promised in the option label.
            resolution["action_id"] = option_id
        return resolution

    # ── config ───────────────────────────────────────────────────────────────

    def _require_cwd(self, params: dict[str, Any]) -> str:
        raw = str(params.get("cwd") or "")
        if not raw:
            raise ACPServerError("an absolute cwd is required", INVALID_PARAMS)
        path = Path(raw)
        if not path.is_absolute():
            raise ACPServerError(f"cwd '{raw}' is not absolute", INVALID_PARAMS)
        if not path.is_dir():
            raise ACPServerError(f"cwd '{raw}' is not a directory", INVALID_PARAMS)
        return str(path.resolve())

    async def _session_config(self, cwd: str) -> dict[str, Any]:
        """Build the per-turn config that binds a session to the client's cwd.

        Sent with every prompt, exactly as the desktop UI sends a chat's config
        on every turn, so a rebind on ``session/load`` takes effect immediately.
        """
        if self._sandbox is None:
            self._sandbox = await self._backend.sandbox_enabled()
        return {
            "sandbox_volumes": [f"{cwd}:{WORKSPACE_MOUNT}"],
            # Name the path the active execution mode can actually chdir into.
            "cwd": WORKSPACE_MOUNT if self._sandbox else cwd,
            "permission_mode": self._permission_mode,
            SESSION_MARKER: {"cwd": cwd, "mount": WORKSPACE_MOUNT},
        }

    # ── outbound ─────────────────────────────────────────────────────────────

    async def _update(self, session_id: str, update: dict[str, Any]) -> None:
        await self._send(
            {
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {"sessionId": session_id, "update": update},
            }
        )

    async def _call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a request to the client and await its response."""
        request_id = self._next_id
        self._next_id += 1
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        try:
            return await future
        finally:
            self._pending.pop(request_id, None)

    def _resolve_response(self, message: dict[str, Any]) -> None:
        raw_id = message.get("id")
        future = self._pending.get(raw_id if isinstance(raw_id, int) else -1)
        if future is None or future.done():
            logger.debug(f"[acp-server] unmatched response id {raw_id!r}")
            return
        if error := message.get("error"):
            future.set_exception(
                ACPServerError(f"the client refused the request: {_stringify(error)}")
            )
        else:
            result = message.get("result")
            future.set_result(result if isinstance(result, dict) else {})

    async def _reply(self, message_id: Any, result: Any) -> None:
        await self._send({"jsonrpc": "2.0", "id": message_id, "result": result})

    async def _error(self, message_id: Any, code: int, message: str) -> None:
        await self._send(
            {
                "jsonrpc": "2.0",
                "id": message_id,
                "error": {"code": code, "message": message},
            }
        )

    def _spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        """Await in-flight turns so a closing client does not truncate one."""
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(ACPServerError("the client disconnected"))
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)


# ── prompt and history helpers ────────────────────────────────────────────────


def _prompt_text(blocks: Any) -> str:
    """Flatten ACP prompt content blocks into the text of one user message."""
    if isinstance(blocks, str):
        return blocks.strip()
    if not isinstance(blocks, list):
        return ""

    parts: list[str] = []
    for block in blocks:
        if isinstance(block, str):
            parts.append(block)
            continue
        if not isinstance(block, dict):
            continue
        match block.get("type"):
            case "text":
                parts.append(str(block.get("text") or ""))
            case "resource_link":
                if uri := str(block.get("uri") or block.get("name") or ""):
                    parts.append(f"@{uri}")
            case "resource":
                resource = block.get("resource")
                if isinstance(resource, dict):
                    uri = str(resource.get("uri") or "")
                    text = str(resource.get("text") or "")
                    if text:
                        parts.append(f"{uri}\n{text}" if uri else text)
                    elif uri:
                        parts.append(f"@{uri}")
            case _:
                # image/audio are not advertised in promptCapabilities, so a
                # client should not send them; note it rather than drop it.
                parts.append(f"[unsupported {block.get('type')} content]")
    return "\n\n".join(part for part in parts if part).strip()


def _history_updates(messages: list[Any]) -> Iterator[dict[str, Any]]:
    """Replay a chat transcript as ACP message-chunk updates."""
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        role = str(message.get("role") or "")
        if role == "user":
            yield {
                "sessionUpdate": "user_message_chunk",
                "content": _text_block(content),
            }
        elif role == "assistant":
            yield {
                "sessionUpdate": "agent_message_chunk",
                "content": _text_block(content),
            }


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("suzent")
    except PackageNotFoundError:
        return "0"


# ── stdio transport ───────────────────────────────────────────────────────────


def redirect_logs_to_stderr(level: str = "WARNING") -> None:
    """Keep stdout for protocol traffic only.

    Suzent's default loguru sink is stdout; one log line there would corrupt the
    JSON-RPC stream, so this must run before anything else can log.
    """
    from loguru import logger as loguru_logger

    import suzent.logger as suzent_logger

    loguru_logger.remove()
    loguru_logger.add(
        sys.stderr,
        level=level.upper(),
        format="{time:HH:mm:ss} | {level:8} | {name}:{function} | {message}",
    )
    suzent_logger._logging_configured = True


async def serve_stdio(
    *,
    base_url: str | None = None,
    permission_mode: str = "default",
) -> int:
    """Run the ACP agent over stdin/stdout until the client closes the pipe."""
    backend = SuzentBackend(base_url)
    write_lock = asyncio.Lock()

    async def send(message: dict[str, Any]) -> None:
        line = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        async with write_lock:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()

    server = ACPAgentServer(backend, send, permission_mode=permission_mode)
    logger.info(f"[acp-server] serving ACP over stdio against {backend.base_url}")

    try:
        while True:
            # A thread read keeps this portable: connect_read_pipe on stdin is
            # unavailable on Windows' proactor loop.
            line = await asyncio.to_thread(sys.stdin.readline)
            if line == "":
                break
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                logger.warning(
                    f"[acp-server] unparseable line from client: {line[:120]}"
                )
                continue
            if isinstance(message, dict):
                await server.dispatch(message)
    finally:
        await server.drain()
        await backend.aclose()
    return 0
