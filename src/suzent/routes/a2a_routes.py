"""
A2A (Agent2Agent) protocol server routes.

Two surfaces:

* ``GET /.well-known/agent-card.json`` — the spec's discovery path. Served
  unauthenticated (that is what makes it discoverable) but only when the
  operator has switched on ``CONFIG.a2a_enabled``; otherwise it 404s so a
  disabled device is indistinguishable from one that never spoke A2A.
* ``POST /a2a/v1`` — the JSON-RPC endpoint carrying ``message/send``,
  ``message/stream``, ``tasks/get``, ``tasks/cancel`` and ``tasks/resubscribe``.
  This one requires a bearer device grant, exactly like the Suzent peer channel:
  publishing a card advertises that we exist, it does not authorize anyone.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from suzent.a2a.card import build_agent_card, card_metadata
from suzent.a2a.executor import A2AExecutionError, context_chat_id, run_task
from suzent.a2a.tasks import TaskEvent, TaskStore, TaskTransitionError, get_task_store
from suzent.a2a.types import Message, Task
from suzent.config import CONFIG
from suzent.logger import get_logger

logger = get_logger(__name__)

# JSON-RPC 2.0 reserved codes plus the A2A-specific range.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
TASK_NOT_FOUND = -32001
TASK_NOT_CANCELABLE = -32002
PUSH_NOTIFICATION_NOT_SUPPORTED = -32003
UNSUPPORTED_OPERATION = -32004

# Strong references to in-flight task runners (see _start_task).
_RUNNING_TASKS: set[asyncio.Task] = set()


def _rpc_error(request_id: Any, code: int, message: str, status: int = 200):
    """JSON-RPC errors ride a 200 unless the transport itself failed."""
    return JSONResponse(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        },
        status_code=status,
    )


def _rpc_result(request_id: Any, result: Any):
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})


def _dump(model) -> dict:
    return model.model_dump(exclude_none=True)


def _base_url(request: Request) -> str:
    """Externally reachable origin for this server, as the caller reached it."""
    forwarded_host = request.headers.get("x-forwarded-host")
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_host:
        return f"{forwarded_proto or request.url.scheme}://{forwarded_host}"
    return str(request.base_url).rstrip("/")


def _caller_identity(request: Request) -> tuple[str, str]:
    """Resolve the authenticated caller to (key, human label).

    Reuses the node device-grant store: an A2A caller is authorized by exactly
    the same per-peer token the Suzent pairing flow already mints. Loopback
    callers (the local app, tests) are trusted as ``local``.
    """
    from suzent.auth_boundary import extract_token, is_loopback

    app = getattr(request, "app", None)
    node_manager = getattr(getattr(app, "state", None), "node_manager", None)
    try:
        token = extract_token(request.headers.raw)
        record = (
            node_manager.device_store.verify(token)
            if node_manager is not None and token
            else None
        )
    except Exception:
        record = None

    if record:
        device_id = str(record.get("device_id") or "unknown")
        label = str(record.get("display_name") or device_id)
        return device_id, label

    client_host = request.client.host if request.client else ""
    if is_loopback(client_host):
        return "local", "local"
    return "", ""


# ─── Discovery ───────────────────────────────────────────────────────


async def a2a_agent_card(request: Request):
    """GET /.well-known/agent-card.json — public discovery document."""
    if not bool(getattr(CONFIG, "a2a_enabled", False)):
        return JSONResponse({"error": "Not found"}, status_code=404)
    card = build_agent_card(_base_url(request))
    return JSONResponse(_dump(card))


async def a2a_status(request: Request):
    """GET /a2a/status — local UI view of the card and its publish state."""
    base = _base_url(request)
    return JSONResponse(
        {
            "enabled": bool(getattr(CONFIG, "a2a_enabled", False)),
            "card_url": f"{base}/.well-known/agent-card.json",
            "rpc_url": f"{base}/a2a/v1",
            **card_metadata(),
            "card": _dump(build_agent_card(base)),
        }
    )


async def a2a_save_status(request: Request):
    """POST /a2a/status — toggle publication / rename this device's agent."""
    from suzent.routes.config_routes import (
        _load_local_config_file,
        _save_local_config_file,
    )

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    cfg = _load_local_config_file()
    if payload.get("enabled") is not None:
        value = bool(payload["enabled"])
        cfg["a2a_enabled"] = value
        CONFIG.a2a_enabled = value
    if payload.get("agent_name") is not None:
        name = str(payload["agent_name"]).strip()[:64]
        cfg["a2a_agent_name"] = name
        CONFIG.a2a_agent_name = name
    _save_local_config_file(cfg)

    base = _base_url(request)
    return JSONResponse(
        {
            "success": True,
            "enabled": bool(getattr(CONFIG, "a2a_enabled", False)),
            **card_metadata(),
            "card": _dump(build_agent_card(base)),
        }
    )


# ─── JSON-RPC ────────────────────────────────────────────────────────


def _parse_message(params: dict) -> Message:
    raw = params.get("message")
    if not isinstance(raw, dict):
        raise ValidationError.from_exception_data("Message", [])
    return Message.model_validate(raw)


async def _start_task(
    store: TaskStore, request: Request, params: dict
) -> tuple[Task, str]:
    """Validate a send/stream request and kick off its background execution."""
    message = _parse_message(params)
    text = message.text()
    if not text:
        raise A2AExecutionError("message must contain at least one text part")

    caller_key, caller_label = _caller_identity(request)
    if not caller_key:
        raise PermissionError("A valid device grant is required")

    existing_task_id = message.task_id
    if existing_task_id:
        # Resuming an interrupted task: same task, same context, new input.
        existing = store.get(existing_task_id)
        if existing is None:
            raise TaskTransitionError(f"Unknown task '{existing_task_id}'")
        if existing.status.state.is_terminal:
            raise TaskTransitionError(
                f"Task '{existing_task_id}' is already {existing.status.state.value}"
            )
        await store.append_message(existing_task_id, message)
        task = existing
        chat_id = existing.context_id
    else:
        chat_id = context_chat_id(caller_key, message.context_id)
        task = await store.create(context_id=chat_id, message=message)

    # Hold a strong reference: asyncio only keeps a weak one, so a fire-and-forget
    # task can be garbage-collected mid-run and silently stall the request.
    runner = asyncio.create_task(
        run_task(
            store=store,
            task_id=task.id,
            chat_id=chat_id,
            content=text,
            caller_label=caller_label or caller_key,
        )
    )
    _RUNNING_TASKS.add(runner)
    runner.add_done_callback(_RUNNING_TASKS.discard)
    return task, caller_label


async def _await_settled(store: TaskStore, task_id: str) -> Task:
    """Block until the task leaves the live states — the non-streaming path."""
    record = store.record(task_id)
    if record is None:
        raise TaskTransitionError(f"Unknown task '{task_id}'")
    queue = record.subscribe()
    try:
        while True:
            current = store.get(task_id)
            if current and (
                current.status.state.is_terminal or current.status.state.is_interrupted
            ):
                return current
            event = await queue.get()
            if event is None:
                break
    finally:
        record.unsubscribe(queue)
    settled = store.get(task_id)
    if settled is None:
        raise TaskTransitionError(f"Unknown task '{task_id}'")
    return settled


def _sse(event: TaskEvent, request_id: Any) -> str:
    """Wrap one task event as a JSON-RPC result in an SSE frame."""
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": event.model_dump(exclude_none=True),
    }
    return f"data: {json.dumps(payload)}\n\n"


async def _stream_task(
    store: TaskStore, task_id: str, request_id: Any, *, initial: Task | None = None
) -> StreamingResponse:
    record = store.record(task_id)
    if record is None:
        raise TaskTransitionError(f"Unknown task '{task_id}'")
    queue = record.subscribe()

    async def _events():
        try:
            if initial is not None:
                # First frame is the Task itself, so a client that joins mid-flight
                # (tasks/resubscribe) immediately knows the current state.
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": initial.model_dump(exclude_none=True),
                        }
                    )
                    + "\n\n"
                )
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield _sse(event, request_id)
        except asyncio.CancelledError:
            raise
        finally:
            record.unsubscribe(queue)

    return StreamingResponse(_events(), media_type="text/event-stream")


async def a2a_rpc(request: Request):
    """POST /a2a/v1 — the JSON-RPC surface."""
    try:
        body = await request.json()
    except Exception:
        return _rpc_error(None, PARSE_ERROR, "Invalid JSON payload")

    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
        return _rpc_error(
            body.get("id") if isinstance(body, dict) else None,
            INVALID_REQUEST,
            "Expected a JSON-RPC 2.0 request",
        )

    request_id = body.get("id")
    method = str(body.get("method") or "")
    params = body.get("params")
    if not isinstance(params, dict):
        params = {}

    store = get_task_store()

    try:
        if method in ("message/send", "message/stream"):
            task, _label = await _start_task(store, request, params)
            if method == "message/stream":
                return await _stream_task(store, task.id, request_id)
            settled = await _await_settled(store, task.id)
            return _rpc_result(request_id, _dump(settled))

        if method == "tasks/get":
            task_id = str(params.get("id") or "")
            task = store.get(task_id)
            if task is None:
                return _rpc_error(
                    request_id, TASK_NOT_FOUND, f"Task '{task_id}' not found"
                )
            return _rpc_result(request_id, _dump(task))

        if method == "tasks/cancel":
            task_id = str(params.get("id") or "")
            if store.get(task_id) is None:
                return _rpc_error(
                    request_id, TASK_NOT_FOUND, f"Task '{task_id}' not found"
                )
            try:
                task = await store.cancel(task_id)
            except TaskTransitionError as exc:
                return _rpc_error(request_id, TASK_NOT_CANCELABLE, str(exc))
            return _rpc_result(request_id, _dump(task))

        if method == "tasks/resubscribe":
            task_id = str(params.get("id") or "")
            task = store.get(task_id)
            if task is None:
                return _rpc_error(
                    request_id, TASK_NOT_FOUND, f"Task '{task_id}' not found"
                )
            return await _stream_task(store, task_id, request_id, initial=task)

        if method.startswith("tasks/pushNotificationConfig"):
            return _rpc_error(
                request_id,
                PUSH_NOTIFICATION_NOT_SUPPORTED,
                "This agent does not support push notifications",
            )

        return _rpc_error(request_id, METHOD_NOT_FOUND, f"Unknown method '{method}'")

    except PermissionError as exc:
        return _rpc_error(request_id, INVALID_REQUEST, str(exc), status=401)
    except ValidationError:
        return _rpc_error(request_id, INVALID_PARAMS, "Invalid A2A message payload")
    except A2AExecutionError as exc:
        return _rpc_error(request_id, INVALID_PARAMS, str(exc))
    except TaskTransitionError as exc:
        return _rpc_error(request_id, TASK_NOT_FOUND, str(exc))
    except Exception as exc:
        logger.error("A2A RPC {} failed: {}", method, exc)
        return _rpc_error(request_id, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")


# ─── Local UI: tasks we are running, and outbound agents ─────────────


async def a2a_list_tasks(request: Request):
    """GET /a2a/tasks — inbound tasks (work other agents gave us)."""
    store = get_task_store()
    return JSONResponse(
        {
            "tasks": [
                {
                    "id": task.id,
                    "context_id": task.context_id,
                    "state": task.status.state.value,
                    "timestamp": task.status.timestamp,
                    "message": (
                        task.status.message.text() if task.status.message else ""
                    ),
                }
                for task in store.list_tasks()
            ]
        }
    )


# ─── External agents (outbound federation) ───────────────────────────


async def a2a_list_agents(request: Request):
    """GET /a2a/agents — external A2A agents this device may delegate to."""
    from suzent.a2a.store import get_a2a_agent_store

    return JSONResponse({"agents": get_a2a_agent_store().list_agents()})


async def a2a_add_agent(request: Request):
    """POST /a2a/agents — add an agent by URL, fetching its card to verify it."""
    from suzent.a2a.client import A2AClientError, fetch_agent_card
    from suzent.a2a.store import get_a2a_agent_store

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    url = str(payload.get("url") or "").strip()
    if not url:
        return JSONResponse({"error": "url is required"}, status_code=400)
    token = str(payload.get("token") or "").strip()

    try:
        card, base_url, rpc_url = await fetch_agent_card(url)
    except A2AClientError as exc:
        # A failed card fetch is the normal "wrong address" case, not a server
        # fault — report it as such so the UI can show it inline.
        return JSONResponse({"error": str(exc)}, status_code=400)

    store = get_a2a_agent_store()
    agent_id = store.add(
        base_url=base_url,
        rpc_url=rpc_url,
        name=str(card.get("name") or base_url),
        card=card,
        token=token,
    )
    return JSONResponse({"success": True, "agent_id": agent_id, "card": card})


async def a2a_refresh_agent(request: Request):
    """POST /a2a/agents/{agent_id}/refresh — re-fetch a cached agent card."""
    from suzent.a2a.client import A2AClientError, fetch_agent_card
    from suzent.a2a.store import get_a2a_agent_store

    store = get_a2a_agent_store()
    agent_id = request.path_params["agent_id"]
    record = store.get(agent_id)
    if record is None:
        return JSONResponse({"error": "Unknown agent"}, status_code=404)

    try:
        card, base_url, rpc_url = await fetch_agent_card(record["base_url"])
    except A2AClientError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)

    store.add(
        base_url=base_url,
        rpc_url=rpc_url,
        name=str(card.get("name") or base_url),
        card=card,
    )
    return JSONResponse({"success": True, "card": card})


async def a2a_update_agent(request: Request):
    """PATCH /a2a/agents/{agent_id} — enable or pause delegation to an agent."""
    from suzent.a2a.store import get_a2a_agent_store

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    store = get_a2a_agent_store()
    agent_id = request.path_params["agent_id"]
    if payload.get("enabled") is not None:
        if not store.set_enabled(agent_id, bool(payload["enabled"])):
            return JSONResponse({"error": "Unknown agent"}, status_code=404)
    return JSONResponse({"success": True})


async def a2a_remove_agent(request: Request):
    """DELETE /a2a/agents/{agent_id} — forget an agent and its tracked tasks."""
    from suzent.a2a.outbound import get_outbound_tracker
    from suzent.a2a.store import get_a2a_agent_store

    agent_id = request.path_params["agent_id"]
    removed = get_a2a_agent_store().remove(agent_id)
    get_outbound_tracker().forget_agent(agent_id)
    if not removed:
        return JSONResponse({"error": "Unknown agent"}, status_code=404)
    return JSONResponse({"success": True})


async def a2a_send_to_agent(request: Request):
    """POST /a2a/agents/{agent_id}/send — delegate a task to a remote agent.

    Also the path for answering an ``input-required`` question: pass the
    ``task_id`` the remote agent is waiting on and the answer as ``text``.
    """
    from suzent.a2a.client import A2AClient, A2AClientError, summarize_task
    from suzent.a2a.outbound import get_outbound_tracker
    from suzent.a2a.store import get_a2a_agent_store
    from suzent.a2a.types import Task as RemoteTask

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    text = str(payload.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=400)

    store = get_a2a_agent_store()
    agent_id = request.path_params["agent_id"]
    record = store.get(agent_id)
    if record is None:
        return JSONResponse({"error": "Unknown agent"}, status_code=404)
    if not record.get("enabled", True):
        return JSONResponse({"error": "This agent is paused"}, status_code=409)

    client = A2AClient(record["rpc_url"], record.get("token", ""))
    try:
        result = await client.send(
            text,
            context_id=payload.get("context_id") or None,
            task_id=payload.get("task_id") or None,
        )
    except A2AClientError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)

    if isinstance(result, RemoteTask):
        entry = get_outbound_tracker().record(
            agent_id=agent_id,
            agent_name=record.get("name", ""),
            task=result,
            prompt=text,
        )
        return JSONResponse(
            {
                "success": True,
                "kind": "task",
                "task": entry,
                "summary": summarize_task(result),
            }
        )

    # Some agents answer trivially with a bare Message and never open a task.
    return JSONResponse({"success": True, "kind": "message", "summary": result.text()})


async def a2a_outbound_tasks(request: Request):
    """GET /a2a/outbound — our view of tasks delegated to remote agents."""
    from suzent.a2a.outbound import get_outbound_tracker

    return JSONResponse({"tasks": get_outbound_tracker().list_tasks()})


async def a2a_refresh_outbound_task(request: Request):
    """POST /a2a/outbound/{agent_id}/{task_id}/refresh — re-poll a remote task."""
    from suzent.a2a.client import A2AClient, A2AClientError
    from suzent.a2a.outbound import get_outbound_tracker
    from suzent.a2a.store import get_a2a_agent_store

    agent_id = request.path_params["agent_id"]
    task_id = request.path_params["task_id"]
    record = get_a2a_agent_store().get(agent_id)
    if record is None:
        return JSONResponse({"error": "Unknown agent"}, status_code=404)

    client = A2AClient(record["rpc_url"], record.get("token", ""))
    try:
        task = await client.get_task(task_id)
    except A2AClientError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)

    entry = get_outbound_tracker().record(
        agent_id=agent_id, agent_name=record.get("name", ""), task=task
    )
    return JSONResponse({"success": True, "task": entry})


async def a2a_cancel_outbound_task(request: Request):
    """POST /a2a/outbound/{agent_id}/{task_id}/cancel — stop a delegated task."""
    from suzent.a2a.client import A2AClient, A2AClientError
    from suzent.a2a.outbound import get_outbound_tracker
    from suzent.a2a.store import get_a2a_agent_store

    agent_id = request.path_params["agent_id"]
    task_id = request.path_params["task_id"]
    record = get_a2a_agent_store().get(agent_id)
    if record is None:
        return JSONResponse({"error": "Unknown agent"}, status_code=404)

    client = A2AClient(record["rpc_url"], record.get("token", ""))
    try:
        task = await client.cancel_task(task_id)
    except A2AClientError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)

    entry = get_outbound_tracker().record(
        agent_id=agent_id, agent_name=record.get("name", ""), task=task
    )
    return JSONResponse({"success": True, "task": entry})
