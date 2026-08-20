"""
Expose external A2A agents to *our own agent* as delegation targets.

Without this, A2A is only reachable from the Mesh tab: a human clicks
"Delegate". This bridge puts external agents into the same ``agent_list`` /
``agent_send`` surface the agent already uses for Suzent peers, so the agent can
decide on its own that a task belongs somewhere else and hand it over.

Addresses are prefixed ``a2a:`` to sit alongside the peer transport's ``peer:``,
and the two never collide.
"""

from __future__ import annotations

import asyncio
from typing import Any

from suzent.a2a.client import A2AClient, A2AClientError, summarize_task
from suzent.a2a.outbound import get_outbound_tracker
from suzent.a2a.store import get_a2a_agent_store
from suzent.a2a.types import Task
from suzent.logger import get_logger

logger = get_logger(__name__)

A2A_AGENT_PREFIX = "a2a:"


class A2ABridgeError(RuntimeError):
    """Raised when an a2a: address cannot be resolved or reached."""


def agent_address(agent_id: str) -> str:
    return f"{A2A_AGENT_PREFIX}{agent_id}"


def parse_address(agent_id: str) -> str | None:
    """Return the store id for an ``a2a:`` address, else None."""
    if not agent_id.startswith(A2A_AGENT_PREFIX):
        return None
    return agent_id.removeprefix(A2A_AGENT_PREFIX).strip() or None


def list_agents() -> list[dict[str, Any]]:
    """External A2A agents, shaped like the peer transport's records.

    Skills come from the agent's own card, so the model can tell a summarizer
    from a code reviewer instead of guessing from a name.
    """
    records = []
    for agent in get_a2a_agent_store().list_agents():
        card = agent.get("card") or {}
        skills = [
            str(skill.get("name") or skill.get("id") or "")
            for skill in (card.get("skills") or [])
        ]
        description = str(card.get("description") or "").strip()
        title = agent.get("name") or agent.get("base_url") or "Remote A2A agent"
        if skills:
            title = f"{title} ({', '.join(s for s in skills if s)})"
        records.append(
            {
                "agent_id": agent_address(agent["agent_id"]),
                "title": title,
                "kind": "a2a",
                "status": "ready" if agent.get("enabled", True) else "paused",
                "project_id": None,
                "parent_agent_id": None,
                "updated_at": agent.get("added_at") or None,
                "description": description,
                "protocol": "a2a",
            }
        )
    return records


def resolve(agent_id: str, *, require_enabled: bool = True) -> dict[str, Any]:
    store_id = parse_address(agent_id)
    record = get_a2a_agent_store().get(store_id or "") if store_id else None
    if record is None:
        raise A2ABridgeError(f"Unknown A2A agent '{agent_id}'")
    if require_enabled and not record.get("enabled", True):
        raise A2ABridgeError(f"A2A agent '{agent_id}' is paused")
    return {**record, "agent_id": store_id}


def _run_blocking(coro):
    """Run an async call from the sync tool layer.

    Tools execute on a worker thread while the server's loop runs elsewhere, so
    a private loop here is safe and avoids re-entering the running one.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already inside a loop (rare for tools): hand off to a fresh one in a thread.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def delegate(agent_id: str, message: str) -> dict[str, Any]:
    """Send a task to an external A2A agent and return its outcome.

    Unlike the Suzent peer path — which enqueues durably and returns immediately
    — A2A ``message/send`` blocks until the remote task settles *or* interrupts,
    so the answer (or the remote agent's question) comes back in one step.
    """
    record = resolve(agent_id)
    client = A2AClient(record["rpc_url"], record.get("token", ""))

    try:
        result = _run_blocking(client.send(message))
    except A2AClientError as exc:
        raise A2ABridgeError(str(exc)) from exc

    if isinstance(result, Task):
        entry = get_outbound_tracker().record(
            agent_id=record["agent_id"],
            agent_name=record.get("name", ""),
            task=result,
            prompt=message,
        )
        return {
            "summary": summarize_task(result),
            "state": result.status.state.value,
            "task_id": result.id,
            "context_id": result.context_id,
            "agent_id": agent_id,
            "tracked": entry,
        }

    # A bare Message: the agent answered without opening a task.
    return {
        "summary": result.text(),
        "state": "completed",
        "task_id": None,
        "context_id": result.context_id,
        "agent_id": agent_id,
    }


def answer(agent_id: str, task_id: str, message: str) -> dict[str, Any]:
    """Answer a remote task waiting in ``input-required`` and let it resume."""
    record = resolve(agent_id)
    client = A2AClient(record["rpc_url"], record.get("token", ""))

    try:
        result = _run_blocking(client.send(message, task_id=task_id))
    except A2AClientError as exc:
        raise A2ABridgeError(str(exc)) from exc

    if isinstance(result, Task):
        get_outbound_tracker().record(
            agent_id=record["agent_id"],
            agent_name=record.get("name", ""),
            task=result,
        )
        return {
            "summary": summarize_task(result),
            "state": result.status.state.value,
            "task_id": result.id,
        }
    return {"summary": result.text(), "state": "completed", "task_id": task_id}
