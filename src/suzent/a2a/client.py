"""
Outbound A2A client — delegating work to somebody else's agent.

This is the half that makes the mesh open rather than a closed Suzent
federation: the agent on the other end may be LangGraph, ADK, CrewAI, or
anything else that speaks A2A. We only rely on the standard.

Handles the full task lifecycle, including the one the Suzent-native peer flow
could not represent: a remote agent replying ``input-required`` because it needs
a clarification before it can continue. That is surfaced to the caller rather
than being treated as a failure, and answering it is a normal ``message/send``
carrying the same ``taskId``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from suzent.a2a.types import (
    Message,
    Role,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
    TextPart,
)
from suzent.logger import get_logger

logger = get_logger(__name__)

WELL_KNOWN_CARD_PATH = "/.well-known/agent-card.json"
_CARD_TIMEOUT = 10.0
_RPC_TIMEOUT = 120.0
# A delegated task can legitimately run for a long time; the read timeout has to
# outlast the remote agent's thinking, not our own patience.
_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0)


class A2AClientError(RuntimeError):
    """Raised when a remote A2A agent is unreachable or answers unusably."""


def _normalize_base(url: str) -> str:
    candidate = url.strip().rstrip("/")
    if not candidate:
        raise A2AClientError("An agent URL is required")
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    if candidate.endswith(WELL_KNOWN_CARD_PATH):
        candidate = candidate[: -len(WELL_KNOWN_CARD_PATH)]
    return candidate


async def fetch_agent_card(
    url: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> tuple[dict[str, Any], str, str]:
    """Fetch an agent's card. Returns (card, base_url, rpc_url).

    The card's own ``url`` field is authoritative for where RPCs go — an agent
    may serve its card and its RPC endpoint from different hosts.
    """
    base_url = _normalize_base(url)
    card_url = f"{base_url}{WELL_KNOWN_CARD_PATH}"
    try:
        async with httpx.AsyncClient(
            timeout=_CARD_TIMEOUT, trust_env=False, transport=transport
        ) as client:
            response = await client.get(
                card_url, headers={"Accept": "application/json"}
            )
    except httpx.HTTPError as exc:
        raise A2AClientError(
            f"Could not reach {card_url}: {type(exc).__name__}"
        ) from exc

    if response.status_code == 404:
        raise A2AClientError(
            f"No A2A agent card at {card_url} — the address may be wrong, or that "
            "agent has not published a card."
        )
    if response.status_code != 200:
        raise A2AClientError(
            f"Agent card fetch failed with HTTP {response.status_code}"
        )
    try:
        card = response.json()
    except ValueError as exc:
        raise A2AClientError("Agent card was not valid JSON") from exc
    if not isinstance(card, dict) or not card.get("name"):
        raise A2AClientError("Agent card is missing required fields")

    rpc_url = str(card.get("url") or f"{base_url}/a2a/v1")
    return card, base_url, rpc_url


class A2AClient:
    """Talks JSON-RPC to one remote A2A agent."""

    def __init__(
        self,
        rpc_url: str,
        token: str = "",
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.rpc_url = rpc_url
        self.token = token
        # Injected only by tests, to drive an in-process ASGI app instead of a
        # real socket. Production callers leave it None.
        self._transport = transport

    def _headers(self, *, stream: bool = False) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    @staticmethod
    def _envelope(method: str, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": uuid.uuid4().hex,
            "method": method,
            "params": params,
        }

    @staticmethod
    def _user_message(
        text: str, *, context_id: str | None, task_id: str | None
    ) -> Message:
        return Message(
            message_id=uuid.uuid4().hex,
            role=Role.user,
            parts=[TextPart(text=text)],
            context_id=context_id,
            task_id=task_id,
        )

    @staticmethod
    def _unwrap(payload: Any) -> Any:
        if not isinstance(payload, dict):
            raise A2AClientError("Remote agent returned a malformed response")
        if "error" in payload:
            error = payload["error"] or {}
            raise A2AClientError(
                f"Remote agent error {error.get('code')}: {error.get('message')}"
            )
        if "result" not in payload:
            raise A2AClientError("Remote agent response had no result")
        return payload["result"]

    async def _post(self, method: str, params: dict[str, Any]) -> Any:
        try:
            async with httpx.AsyncClient(
                timeout=_RPC_TIMEOUT, trust_env=False, transport=self._transport
            ) as client:
                response = await client.post(
                    self.rpc_url,
                    headers=self._headers(),
                    json=self._envelope(method, params),
                )
        except httpx.HTTPError as exc:
            raise A2AClientError(
                f"Could not reach remote agent: {type(exc).__name__}"
            ) from exc

        if response.status_code == 401:
            raise A2AClientError(
                "Remote agent rejected our credential (HTTP 401). It may require a "
                "token you have not supplied."
            )
        if response.status_code >= 400:
            raise A2AClientError(f"Remote agent returned HTTP {response.status_code}")
        try:
            return self._unwrap(response.json())
        except ValueError as exc:
            raise A2AClientError("Remote agent returned invalid JSON") from exc

    # ─── Methods ─────────────────────────────────────────────────────

    async def send(
        self, text: str, *, context_id: str | None = None, task_id: str | None = None
    ) -> Task | Message:
        """message/send — blocks until the remote task settles or interrupts.

        Returns a ``Task`` normally; some agents answer a trivial request with a
        bare ``Message`` instead, which the spec permits.
        """
        message = self._user_message(text, context_id=context_id, task_id=task_id)
        result = await self._post(
            "message/send", {"message": message.model_dump(exclude_none=True)}
        )
        return self._parse_result(result)

    async def stream(
        self, text: str, *, context_id: str | None = None, task_id: str | None = None
    ) -> AsyncIterator[
        Task | Message | TaskStatusUpdateEvent | TaskArtifactUpdateEvent
    ]:
        """message/stream — yields task events as the remote agent works."""
        message = self._user_message(text, context_id=context_id, task_id=task_id)
        envelope = self._envelope(
            "message/stream", {"message": message.model_dump(exclude_none=True)}
        )
        try:
            async with httpx.AsyncClient(
                timeout=_STREAM_TIMEOUT, trust_env=False, transport=self._transport
            ) as client:
                async with client.stream(
                    "POST",
                    self.rpc_url,
                    headers=self._headers(stream=True),
                    json=envelope,
                ) as response:
                    if response.status_code >= 400:
                        raise A2AClientError(
                            f"Remote agent returned HTTP {response.status_code}"
                        )
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        try:
                            payload = json.loads(line[6:])
                        except ValueError:
                            continue
                        yield self._parse_result(self._unwrap(payload))
        except httpx.HTTPError as exc:
            raise A2AClientError(
                f"Stream from remote agent failed: {type(exc).__name__}"
            ) from exc

    async def get_task(self, task_id: str) -> Task:
        result = await self._post("tasks/get", {"id": task_id})
        parsed = self._parse_result(result)
        if not isinstance(parsed, Task):
            raise A2AClientError("tasks/get did not return a task")
        return parsed

    async def cancel_task(self, task_id: str) -> Task:
        result = await self._post("tasks/cancel", {"id": task_id})
        parsed = self._parse_result(result)
        if not isinstance(parsed, Task):
            raise A2AClientError("tasks/cancel did not return a task")
        return parsed

    @staticmethod
    def _parse_result(
        result: Any,
    ) -> Task | Message | TaskStatusUpdateEvent | TaskArtifactUpdateEvent:
        """Discriminate a result by its ``kind``, as the spec requires."""
        if not isinstance(result, dict):
            raise A2AClientError("Remote agent returned a malformed result")
        kind = result.get("kind")
        try:
            if kind == "task":
                return Task.model_validate(result)
            if kind == "message":
                return Message.model_validate(result)
            if kind == "status-update":
                return TaskStatusUpdateEvent.model_validate(result)
            if kind == "artifact-update":
                return TaskArtifactUpdateEvent.model_validate(result)
        except Exception as exc:
            raise A2AClientError(f"Could not parse remote {kind}: {exc}") from exc
        raise A2AClientError(f"Remote agent returned an unknown result kind '{kind}'")


def summarize_task(task: Task) -> str:
    """Render a settled remote task as text our agent can read back.

    ``input-required`` is deliberately not an error: it is the remote agent
    asking a question, and the caller needs to see the question.
    """
    state = task.status.state
    reply = task.status.message.text() if task.status.message else ""
    if not reply and task.artifacts:
        reply = "\n".join(
            part.text
            for artifact in task.artifacts
            for part in artifact.parts
            if isinstance(part, TextPart)
        ).strip()

    if state is TaskState.completed:
        return reply or "(the remote agent completed with no output)"
    if state is TaskState.input_required:
        return (
            f"The remote agent needs more information before it can continue: "
            f"{reply or '(no question given)'}"
        )
    if state is TaskState.auth_required:
        return (
            "The remote agent requires additional authentication before it can "
            f"continue: {reply or '(no detail given)'}"
        )
    if state is TaskState.canceled:
        return "The remote task was canceled."
    if state is TaskState.rejected:
        return f"The remote agent rejected the task: {reply or '(no reason given)'}"
    return f"The remote task {state.value}: {reply or '(no detail given)'}"
