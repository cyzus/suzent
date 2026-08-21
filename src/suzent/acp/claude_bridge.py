"""Built-in CLI → ACP bridge: wraps ``claude -p`` for subscription users.

Speaks ACP v1 JSON-RPC over stdio.  Each ``session/prompt`` spawns
``claude -p --output-format stream-json`` and relays text chunks as
``session/update`` notifications.  Conversation continuity is preserved
across turns via ``--resume <id>`` when the CLI reports a session id.

Run directly::

    python -m suzent.acp.claude_bridge

Or launch through the ACP agent registry (built-in by default).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass
from typing import Any


# Auth variables that silently outrank the user's claude.ai login. This bridge
# exists to drive a Pro/Max subscription, so an API key inherited from the
# Suzent process would switch billing to the API and disable org connectors —
# the CLI warns about exactly this. The API-key path is a separate agent
# ("Claude Code (API)"), so stripping these here costs nothing.
_SUBSCRIPTION_CONFLICT_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


def _cli_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in _SUBSCRIPTION_CONFLICT_VARS:
        env.pop(key, None)
    return env


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


@dataclass
class _TurnResult:
    """Outcome of one ``claude -p`` invocation."""

    returncode: int | None
    text: str
    stderr: str
    timed_out: bool


class _Session:
    """State for one ACP session backed by the Claude CLI."""

    __slots__ = ("id", "cwd", "claude_conversation_id", "cancelled", "proc")

    def __init__(self, session_id: str, cwd: str) -> None:
        self.id = session_id
        self.cwd = cwd
        # The CLI process for this session's in-flight turn, if any.  Held per
        # session rather than per bridge so cancelling one session cannot kill
        # another session's child.
        self.proc: asyncio.subprocess.Process | None = None
        # Populated from the CLI's ``result`` event so subsequent turns can
        # ``--resume`` the same conversation and keep full context.
        self.claude_conversation_id: str | None = None
        self.cancelled = False


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------


class ClaudeACPBridge:
    """Minimal ACP v1 server that delegates prompts to ``claude -p``."""

    def __init__(self) -> None:
        self._sessions: dict[str, _Session] = {}
        self._write_lock = asyncio.Lock()
        # Cleared permanently the first time the CLI rejects the flag.
        self._partial = True

    # ── JSON-RPC plumbing ────────────────────────────────────────────

    async def _write(self, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        async with self._write_lock:
            sys.stdout.buffer.write(line.encode("utf-8"))
            sys.stdout.buffer.flush()

    async def _respond(self, req_id: Any, result: Any) -> None:
        await self._write({"jsonrpc": "2.0", "id": req_id, "result": result})

    async def _error(self, req_id: Any, code: int, message: str) -> None:
        await self._write(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": code, "message": message},
            }
        )

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        await self._write({"jsonrpc": "2.0", "method": method, "params": params})

    # ── ACP handlers ─────────────────────────────────────────────────

    async def handle_initialize(self, req_id: Any, _params: dict[str, Any]) -> None:
        await self._respond(
            req_id,
            {
                "protocolVersion": 1,
                "agentInfo": {
                    "name": "Claude Code (CLI Bridge)",
                    "version": "1.0.0",
                },
                "agentCapabilities": {"loadSession": False},
            },
        )

    async def handle_session_new(self, req_id: Any, params: dict[str, Any]) -> None:
        session_id = str(uuid.uuid4())
        cwd = str(params.get("cwd") or os.getcwd())
        self._sessions[session_id] = _Session(session_id, cwd)
        await self._respond(req_id, {"sessionId": session_id})

    async def handle_session_prompt(self, req_id: Any, params: dict[str, Any]) -> None:
        session_id = str(params.get("sessionId") or "")
        session = self._sessions.get(session_id)
        if session is None:
            await self._error(req_id, -32602, f"Unknown session: {session_id}")
            return

        prompt_text = _extract_prompt_text(params.get("prompt") or [])
        if not prompt_text.strip():
            await self._error(req_id, -32602, "Empty prompt")
            return

        session.cancelled = False

        turn = await self._run_claude(session, prompt_text, partial=self._partial)
        if turn is None:
            await self._error(
                req_id,
                -32603,
                "claude CLI not found — install Claude Code "
                "and run `claude auth login`",
            )
            return

        # Older CLIs reject --include-partial-messages. Nothing was emitted in
        # that case, so re-running without the flag can't duplicate output.
        if self._partial and _rejects_partial_messages(turn.stderr):
            self._partial = False
            turn = await self._run_claude(session, prompt_text, partial=False)
            if turn is None:  # pragma: no cover — CLI vanished mid-turn
                await self._error(req_id, -32603, "claude CLI not found")
                return

        if turn.timed_out:
            msg = (
                "claude CLI produced no output within 60 s — "
                "it may need authentication (`claude auth login`) "
                "or is stuck."
            )
            if turn.stderr:
                msg += f"\nstderr: {turn.stderr[:500]}"
            await self._fail_turn(req_id, session_id, msg)
            return

        if session.cancelled:
            await self._respond(req_id, {"stopReason": "cancelled", "text": turn.text})
        elif turn.returncode != 0 and not turn.text.strip():
            await self._fail_turn(
                req_id,
                session_id,
                turn.stderr or f"claude exited with code {turn.returncode}",
            )
        else:
            await self._respond(req_id, {"stopReason": "end_turn", "text": turn.text})

    async def _fail_turn(self, req_id: Any, session_id: str, message: str) -> None:
        """Report a failed turn on the session stream, then answer the RPC."""
        await self._notify(
            "session/update",
            {
                "sessionId": session_id,
                "status": "turn_error",
                "phase": "error",
                "message": message,
            },
        )
        await self._respond(req_id, {"stopReason": "error", "text": ""})

    async def _run_claude(
        self, session: _Session, prompt_text: str, *, partial: bool
    ) -> _TurnResult | None:
        """Run one ``claude -p`` invocation, relaying text as it arrives.

        Returns ``None`` when the CLI is not installed.
        """
        # ``-p`` is print mode; ``stream-json`` gives one JSON event per line.
        # ``--verbose`` is mandatory alongside ``--print --output-format
        # stream-json`` — without it the CLI refuses to start.
        cmd: list[str] = [
            "claude",
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
        ]
        if partial:
            # Emits `stream_event` deltas so text streams token-by-token
            # instead of arriving as one block at the end of the turn.
            cmd.append("--include-partial-messages")
        if session.claude_conversation_id:
            cmd.extend(["--resume", session.claude_conversation_id])
        cmd.append("--")
        cmd.append(prompt_text)

        try:
            # stdin must be DEVNULL: the bridge's own stdin is the ACP JSON-RPC
            # pipe.  Without this, the claude process inherits that handle and
            # may try to read from it — causing a deadlock on Windows (both the
            # bridge read-loop and the child fight over the same pipe) and
            # potential hangs on all platforms.
            extra: dict[str, Any] = {}
            if os.name == "nt":
                # Prevent a transient console window flash on Windows.
                extra["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=session.cwd,
                env=_cli_env(),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **extra,
            )
            session.proc = proc
        except FileNotFoundError:
            return None

        # stderr is a pipe, so someone has to read it while the child runs.
        # A chatty `claude -p` -- node deprecation warnings, auth notices --
        # otherwise fills the pipe buffer and blocks on its next write, with
        # nothing on stdout to break the deadlock until the ACP timeout.
        stderr_task = asyncio.create_task(_read_all(proc.stderr))

        full_text = ""
        got_first_line = False
        # With --include-partial-messages the same text arrives twice: once as
        # `stream_event` deltas and again in the final `assistant` message.
        # Prefer the deltas; fall back to `assistant` only if none appeared.
        saw_delta = False
        try:
            assert proc.stdout is not None
            while True:
                if session.cancelled:
                    break
                # Apply a generous startup timeout: if the CLI produces no
                # output at all within 60 s, it is likely stuck (auth prompt,
                # stdin deadlock, network hang).  Once any line arrives,
                # subsequent reads are untimed — the model can think.
                timeout = None if got_first_line else 60.0
                try:
                    line = await asyncio.wait_for(
                        proc.stdout.readline(), timeout=timeout
                    )
                except asyncio.TimeoutError:
                    # Kill the stalled process so we can report the error.
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
                    return _TurnResult(
                        returncode=None,
                        text="",
                        stderr=await _collect(stderr_task, 2.0),
                        timed_out=True,
                    )

                if not line:
                    break  # EOF — process exited
                got_first_line = True
                raw = line.decode("utf-8", errors="replace").strip()
                if not raw:
                    continue
                delta = _extract_text_delta(raw)
                if delta:
                    # Only a real stream event counts.  A non-JSON line is
                    # relayed verbatim, and letting a stray node warning set
                    # this flag would suppress the `assistant` fallback for
                    # the rest of the turn -- leaving the warning as the
                    # entire reply.
                    saw_delta = saw_delta or _is_json_object(raw)
                else:
                    whole = _extract_assistant_text(raw)
                    if whole and not saw_delta:
                        delta = whole
                if delta:
                    full_text += delta
                    await self._notify(
                        "session/update",
                        {
                            "sessionId": session.id,
                            "update": {
                                "sessionUpdate": "agent_message_chunk",
                                "content": {"type": "text", "text": delta},
                            },
                        },
                    )
                _try_capture_conversation_id(session, raw)
        finally:
            session.proc = None
            if session.cancelled and proc.returncode is None:
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass

        await proc.wait()
        return _TurnResult(
            returncode=proc.returncode,
            text=full_text,
            stderr=await _collect(stderr_task, 1.0),
            timed_out=False,
        )

    async def handle_session_cancel(self, params: dict[str, Any]) -> None:
        session_id = str(params.get("sessionId") or "")
        session = self._sessions.get(session_id)
        if session is None:
            return
        session.cancelled = True
        proc = session.proc
        if proc and proc.returncode is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass

    # ── Main loop ────────────────────────────────────────────────────

    async def run(self) -> None:
        """Read JSON-RPC messages from stdin and dispatch."""
        loop = asyncio.get_running_loop()
        # One entry per in-flight turn.  Keeping only the newest task leaked
        # the others when several sessions were prompted at once.
        prompt_tasks: set[asyncio.Task[None]] = set()

        while True:
            raw = await loop.run_in_executor(None, sys.stdin.buffer.readline)
            if not raw:
                break
            text = raw.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                continue

            method = str(msg.get("method") or "")
            req_id = msg.get("id")
            params = msg.get("params") or {}

            if method == "initialize":
                await self.handle_initialize(req_id, params)
            elif method == "session/new":
                await self.handle_session_new(req_id, params)
            elif method == "session/prompt":
                # Run concurrently so cancel messages can still be received.
                task = asyncio.create_task(self.handle_session_prompt(req_id, params))
                prompt_tasks.add(task)
                task.add_done_callback(prompt_tasks.discard)
            elif method == "session/cancel":
                await self.handle_session_cancel(params)
            elif req_id is not None:
                await self._error(req_id, -32601, f"Method not found: {method}")

        # Stdin closed — clean up any running prompts.
        pending = [t for t in prompt_tasks if not t.done()]
        for task in pending:
            task.cancel()
        for task in pending:
            try:
                await task
            except asyncio.CancelledError:
                pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_prompt_text(parts: list[Any]) -> str:
    """Join ACP prompt parts into a single text string."""
    texts: list[str] = []
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "text":
            texts.append(str(part.get("text") or ""))
        elif isinstance(part, str):
            texts.append(part)
    return "\n".join(texts)


def _extract_text_delta(line: str) -> str:
    """Pull displayable text from one ``stream-json`` line.

    Returns the empty string for metadata events so they are silently
    skipped rather than relayed as visible text.
    """
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        # Not JSON — treat as raw text (plain-text fallback).
        return line

    if not isinstance(event, dict):
        return ""

    etype = str(event.get("type") or "")

    # ``--include-partial-messages`` wraps the raw Anthropic stream events in a
    # `stream_event` envelope; unwrap it and read the inner event.
    if etype == "stream_event":
        inner = event.get("event")
        if isinstance(inner, dict):
            event = inner
            etype = str(event.get("type") or "")
        else:
            return ""

    # Standard Anthropic streaming: content_block_delta with text_delta.
    if etype == "content_block_delta":
        delta = event.get("delta")
        if isinstance(delta, dict) and delta.get("type") == "text_delta":
            return str(delta.get("text") or "")
        return ""

    # Metadata / structural events — skip.
    if etype in _METADATA_EVENTS:
        return ""

    # Unknown event — check for a bare text field.
    text = event.get("text")
    if isinstance(text, str):
        return text
    return ""


_METADATA_EVENTS = frozenset(
    {
        "message_start",
        "message_stop",
        "message_delta",
        "content_block_start",
        "content_block_stop",
        "result",
        "system",
        # CLI-level envelopes carrying no displayable text of their own.
        "assistant",
        "user",
        "rate_limit_event",
    }
)


def _extract_assistant_text(line: str) -> str:
    """Pull text from a whole ``assistant`` message event.

    Without ``--include-partial-messages`` the CLI reports each assistant turn
    as one ``{"type": "assistant", "message": {"content": [...]}}`` event
    rather than as incremental deltas. This is the fallback for CLIs too old
    to support partial messages.
    """
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return ""
    if not isinstance(event, dict) or event.get("type") != "assistant":
        return ""
    message = event.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    return "".join(
        str(block.get("text") or "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


def _rejects_partial_messages(stderr: str) -> bool:
    """True when the CLI failed because it doesn't know the partial flag."""
    lowered = stderr.lower()
    return "include-partial-messages" in lowered and (
        "unknown option" in lowered or "unknown argument" in lowered
    )


async def _read_all(stream: asyncio.StreamReader | None) -> str:
    """Consume a pipe to EOF.

    Run as a task for the lifetime of the child so its stderr buffer can
    never fill up.
    """
    if stream is None:
        return ""
    try:
        data = await stream.read()
    except Exception:
        return ""
    return data.decode("utf-8", errors="replace").strip()


async def _collect(task: asyncio.Task[str], timeout: float) -> str:
    """Take what a drain task has, giving up rather than hanging the turn."""
    try:
        return await asyncio.wait_for(task, timeout)
    except Exception:
        return ""


def _is_json_object(line: str) -> bool:
    """True when the line parsed as a JSON object -- i.e. a real CLI event."""
    try:
        return isinstance(json.loads(line), dict)
    except (json.JSONDecodeError, ValueError):
        return False


def _try_capture_conversation_id(session: _Session, line: str) -> None:
    """Extract the Claude conversation id from a ``result`` event.

    The ``result`` event at the end of a ``claude -p`` run carries a
    ``session_id`` (or ``conversation_id``) that can be fed back via
    ``--resume`` on the next turn to maintain full context.
    """
    try:
        event = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return
    if isinstance(event, dict):
        sid = event.get("session_id") or event.get("conversation_id")
        if isinstance(sid, str) and sid:
            session.claude_conversation_id = sid


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def _main() -> None:
    bridge = ClaudeACPBridge()
    await bridge.run()


if __name__ == "__main__":
    asyncio.run(_main())
