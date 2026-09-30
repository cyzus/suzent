"""Small, resource-scoped HTTP surface for paired interactive clients."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from suzent.auth_boundary import extract_token
from suzent.database import get_database
from suzent.mobile.pairing import ClientGrant, PairingStore
from suzent.routes.mobile_routes import get_mobile_store, reply


class CreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="New conversation", min_length=1, max_length=200)
    project_id: str | None = Field(default=None, min_length=1, max_length=200)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat_id: str = Field(min_length=1, max_length=200, pattern=r"^[^/]+$")


class SendRequest(ChatRequest):
    message: str = Field(min_length=1, max_length=100000)
    model: str | None = Field(default=None, min_length=1, max_length=300)
    client_message_id: str | None = Field(default=None, min_length=1, max_length=100)


class ManageRequest(ChatRequest):
    action: Literal["pin", "unpin", "rename", "move", "delete"]
    value: str | None = Field(default=None, min_length=1, max_length=200)


class MessageActionRequest(ChatRequest):
    action: Literal["retry", "edit", "fork"]
    message_index: Annotated[StrictInt, Field(ge=0)]
    text: str | None = Field(default=None, min_length=1, max_length=100000)
    model: str | None = Field(default=None, min_length=1, max_length=300)


class ObserveRequest(ChatRequest):
    wait_ms: int = Field(default=1000, ge=0, le=1000)
    protocol: Literal[1] = 1
    run_id: str | None = Field(default=None, max_length=200)
    after_seq: Annotated[StrictInt, Field(ge=0)] | None = None


def authorize(
    request: Request, chat_id: str | None = None, action: str = "read"
) -> ClientGrant:
    token = extract_token(request.scope.get("headers", []))
    grant = get_mobile_store(request).verify(token)
    if grant is None:
        raise HTTPException(401, "Mobile credential revoked or invalid")
    if chat_id is not None and not grant.permissions.permits_chat(chat_id):
        raise HTTPException(403, "Conversation not shared with this device")
    if action != "read" and not getattr(grant.permissions, action, False):
        raise HTTPException(403, "Action not permitted for this device")
    return grant


async def parse[T: BaseModel](request: Request, model: type[T]) -> T:
    try:
        return model.model_validate(await request.json())
    except (ValidationError, ValueError):
        raise HTTPException(400, "Invalid mobile request") from None


def forwarded(request: Request, body: dict) -> Request:
    # Only validated fields reach the shared handlers; config, resume_approvals,
    # file paths, and tool-policy overrides are never accepted from this surface.
    result = Request(dict(request.scope), request.receive)
    result._body = json.dumps(body).encode()
    return result


async def session(request: Request) -> JSONResponse:
    return reply(
        {
            "device": authorize(request).model_dump(),
            "client_protocol": 1,
            "stream_protocols": [1],
        }
    )


async def chats(request: Request) -> JSONResponse:
    grant = authorize(request)
    db = get_database()
    records = db.list_chat_titles(
        chat_ids=None if grant.permissions.all_chats else grant.permissions.chat_ids,
        limit=1000,
    )
    projects_by_chat = db.get_chat_projects([chat_id for chat_id, _ in records])
    pinned = db.get_pinned_chat_ids([chat_id for chat_id, _ in records])
    from suzent.core.stream_registry import is_background_streaming

    return reply(
        {
            "chats": [
                {
                    "id": chat_id,
                    "title": title,
                    "pinned": chat_id in pinned,
                    "isRunning": is_background_streaming(chat_id),
                    "projectId": projects_by_chat.get(chat_id, (None, None))[0],
                    "projectName": projects_by_chat.get(chat_id, (None, None))[1],
                }
                for chat_id, title in records
            ]
        }
    )


async def chat(request: Request) -> JSONResponse:
    chat_id = request.path_params["chat_id"]
    authorize(request, chat_id)
    from suzent.routes.chat_routes import get_chat

    response = await get_chat(request, include_runtime=False)
    if response.status_code != 200:
        return response
    data = json.loads(response.body)
    from suzent.core.providers import get_default_chat_model, get_enabled_models_from_db

    db = get_database()
    stored_chat = db.get_chat(chat_id)
    if stored_chat is None:
        raise HTTPException(404, "Conversation unavailable")
    # The lightweight transcript deliberately excludes configuration.
    config = stored_chat.config or {}
    native = str(config.get("runtime", "native")).lower() != "acp"
    metadata = get_database().get_chat_projects([chat_id]).get(chat_id, (None, None))
    return reply(
        {
            **{
                key: data[key]
                for key in ("id", "title", "messages", "isRunning")
                if key in data
            },
            "projectId": metadata[0],
            "projectName": metadata[1],
            "pinned": chat_id in get_database().get_pinned_chat_ids([chat_id]),
            "model": (
                config.get("model")
                or config.get("subagent_model")
                or get_default_chat_model()
            )
            if native
            else None,
            "models": get_enabled_models_from_db() if native else [],
        }
    )


def allowed_projects(grant: ClientGrant) -> list[dict[str, str]]:
    db = get_database()
    allowed = (
        None
        if grant.permissions.all_chats
        else {
            value[0]
            for value in db.get_chat_projects(grant.permissions.chat_ids).values()
        }
    )
    return [
        {"id": project.id, "name": project.name}
        for project in db.list_projects()
        if allowed is None or project.id in allowed
    ]


async def composer(request: Request) -> JSONResponse:
    authorize(request)
    from suzent.core.providers import get_default_chat_model, get_enabled_models_from_db

    return reply(
        {
            "id": "",
            "title": "",
            "messages": [],
            "model": get_default_chat_model(),
            "models": get_enabled_models_from_db(),
        }
    )


async def projects(request: Request) -> JSONResponse:
    return reply({"projects": allowed_projects(authorize(request))})


async def create(request: Request) -> JSONResponse:
    grant = authorize(request, action="create_chats")
    body = await parse(request, CreateRequest)
    if body.project_id is not None and body.project_id not in {
        project["id"] for project in allowed_projects(grant)
    }:
        raise HTTPException(403, "Project not shared with this device")
    from suzent.routes.chat_routes import create_chat

    response = await create_chat(forwarded(request, body.model_dump(exclude_none=True)))
    if response.status_code != 201:
        return response
    data = json.loads(response.body)
    store = get_mobile_store(request)
    if not store.add_chat(grant.device_id, data["id"]):
        raise HTTPException(401, "Mobile credential revoked")
    return reply(
        {key: data[key] for key in ("id", "title", "messages") if key in data}, 201
    )


async def send(request: Request) -> JSONResponse:
    body = await parse(request, SendRequest)
    authorize(request, body.chat_id, "send")
    if body.message.lstrip().startswith("/"):
        raise HTTPException(403, "Desktop commands are not available to mobile clients")
    from suzent.routes.chat_routes import chat_send
    from suzent.core.providers import get_default_chat_model, get_enabled_models_from_db

    db = get_database()
    chat = db.get_chat(body.chat_id)
    if chat is None:
        raise HTTPException(404, "Conversation unavailable")
    config = dict(chat.config or {})
    native = str(config.get("runtime", "native")).lower() != "acp"
    payload = body.model_dump(exclude={"model"}, exclude_none=True)
    if body.model is not None:
        if not native or body.model not in get_enabled_models_from_db():
            raise HTTPException(400, "Model unavailable for this conversation")
        config["model"] = body.model
    elif native and not config.get("model"):
        config["model"] = config.get("subagent_model") or get_default_chat_model()
    payload["config"] = config
    already_sent = body.client_message_id is not None and db.has_client_message(
        body.chat_id, body.client_message_id
    )
    response = await chat_send(forwarded(request, payload))
    if (
        response.status_code == 202
        and native
        and not already_sent
        and config.get("model")
    ):
        db.merge_chat_config(body.chat_id, {"model": config["model"]})
    return response


async def stop(request: Request) -> JSONResponse:
    body = await parse(request, ChatRequest)
    authorize(request, body.chat_id, "stop")
    from suzent.routes.chat_routes import stop_chat

    return await stop_chat(forwarded(request, body.model_dump()))


async def message_action(request: Request) -> JSONResponse:
    body = await parse(request, MessageActionRequest)
    grant = authorize(request, body.chat_id)
    db = get_database()
    stored = db.get_chat(body.chat_id)
    if stored is None:
        raise HTTPException(404, "Conversation unavailable")
    from suzent.core.stream_registry import is_background_streaming

    if is_background_streaming(body.chat_id):
        raise HTTPException(409, "Conversation is running")
    messages = stored.messages or []
    if body.message_index >= len(messages):
        raise HTTPException(400, "Message unavailable")
    if body.action == "fork":
        authorize(request, body.chat_id, "create_chats")
        from suzent.core.fork import assistant_message_boundaries, fork_chat

        if messages[body.message_index].get("role") not in {"assistant", "tool"}:
            raise HTTPException(400, "Select an assistant reply to branch")
        boundary = next(
            (
                end
                for end in assistant_message_boundaries(messages)
                if end > body.message_index
            ),
            None,
        )
        if boundary is None:
            raise HTTPException(400, "Assistant reply unavailable")
        try:
            new_id, _ = fork_chat(body.chat_id, message_index=boundary)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        if not get_mobile_store(request).add_chat(grant.device_id, new_id):
            raise HTTPException(401, "Mobile credential revoked")
        return reply({"chat_id": new_id})
    authorize(request, body.chat_id, "send")
    authorize(request, body.chat_id, "manage_chats")
    config = dict(stored.config or {})
    if str(config.get("runtime", "native")).lower() == "acp":
        raise HTTPException(400, "Retry is unavailable for this runtime")
    if body.action == "edit" and (body.text or "").lstrip().startswith("/"):
        raise HTTPException(403, "Desktop commands are not available to mobile clients")
    if body.model is not None:
        from suzent.core.providers import get_enabled_models_from_db

        if body.model not in get_enabled_models_from_db():
            raise HTTPException(400, "Model unavailable for this conversation")
        config["model"] = body.model
    elif not config.get("model") and config.get("subagent_model"):
        config["model"] = config["subagent_model"]
    last_user = next(
        (
            i
            for i in range(len(messages) - 1, -1, -1)
            if messages[i].get("role") == "user"
        ),
        -1,
    )
    if last_user < 0 or body.message_index < last_user:
        raise HTTPException(409, "Only the latest turn can be retried")
    if body.action == "edit" and (
        body.message_index != last_user or not (body.text or "").strip()
    ):
        raise HTTPException(400, "Only the latest user message can be edited")
    from suzent.core.retry import load_retry_checkpoint

    checkpoint = load_retry_checkpoint(body.chat_id)
    if checkpoint is None:
        raise HTTPException(409, "No retry checkpoint available")
    checkpoint_revision = checkpoint.config_snapshot.get("_retry_revision")
    if (
        not isinstance(checkpoint_revision, int)
        or checkpoint_revision != stored.state_revision
    ):
        raise HTTPException(
            409, "The conversation has changed since the retry checkpoint"
        )
    from suzent.core.fork import assistant_message_boundaries

    latest_content = messages[last_user].get("content")
    if (
        not isinstance(latest_content, str)
        or any(
            row.get("role") in {"system_triggered", "trigger"}
            for row in messages[last_user + 1 :]
        )
        or latest_content.strip() != checkpoint.user_message.strip()
        or len(assistant_message_boundaries(messages[last_user + 1 :])) > 1
    ):
        raise HTTPException(409, "The latest turn does not match the retry checkpoint")
    from suzent.routes.chat_routes import chat_send

    response = await chat_send(
        forwarded(
            request,
            {
                "chat_id": body.chat_id,
                "message": f"/retry-edit {body.text.strip()}"
                if body.action == "edit"
                else "/retry",
                "config": config,
            },
        )
    )
    if response.status_code == 202 and config.get("model"):
        db.merge_chat_config(body.chat_id, {"model": config["model"]})
    return response


async def manage(request: Request) -> JSONResponse:
    body = await parse(request, ManageRequest)
    grant = authorize(request, body.chat_id, "manage_chats")
    db = get_database()
    if db.get_chat(body.chat_id) is None:
        raise HTTPException(404, "Conversation unavailable")
    if body.action in {"rename", "move"} and not (body.value or "").strip():
        raise HTTPException(400, "A value is required")
    from suzent.core.stream_registry import is_background_streaming

    if body.action in {"move", "delete"} and is_background_streaming(body.chat_id):
        raise HTTPException(409, "Stop the response before moving or deleting")
    if body.action == "move":
        if body.value not in {project["id"] for project in allowed_projects(grant)}:
            raise HTTPException(403, "Project not shared with this device")
        # Shared project moves also move descendants. Never affect unshared chats.
        descendants = db.get_subagent_chat_ids_for_parent_chat(body.chat_id)
        if any(not grant.permissions.permits_chat(child) for child in descendants):
            raise HTTPException(
                403, "Conversation descendants not shared with this device"
            )
        if any(is_background_streaming(child) for child in descendants):
            raise HTTPException(409, "Stop descendant responses before moving")
        from suzent.routes.project_routes import move_chat_to_project

        target = forwarded(request, {"project_id": body.value})
        target.scope["path_params"] = {"chat_id": body.chat_id}
        return await move_chat_to_project(target)
    if body.action == "delete":
        from suzent.routes.chat_routes import delete_chat

        target = forwarded(request, {})
        target.scope["path_params"] = {"chat_id": body.chat_id}
        target.scope["query_string"] = b""
        return await delete_chat(target)
    updated = db.update_chat(
        body.chat_id,
        **(
            {"title": body.value.strip()}
            if body.action == "rename"
            else {"pinned": body.action == "pin"}
        ),
    )
    return reply({"ok": updated}, 200 if updated else 404)


async def revocable_stream(
    source: AsyncIterator, store: PairingStore, token: str, chat_id: str
) -> AsyncIterator:
    pending: asyncio.Task | None = None
    try:
        while True:
            grant = store.verify(token)
            if grant is None or not grant.permissions.permits_chat(chat_id):
                return
            if pending is None:
                pending = asyncio.create_task(anext(source))
            done, _ = await asyncio.wait({pending}, timeout=0.25)
            if not done:
                continue
            grant = store.verify(token)
            if grant is None or not grant.permissions.permits_chat(chat_id):
                return
            try:
                chunk = pending.result()
            except StopAsyncIteration:
                return
            pending = None
            yield chunk
    finally:
        if pending is not None:
            pending.cancel()
            with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                await pending
        if hasattr(source, "aclose"):
            await source.aclose()


async def observe(request: Request) -> Response:
    body = await parse(request, ObserveRequest)
    authorize(request, body.chat_id)
    from suzent.routes.chat_routes import live_stream

    response = await live_stream(forwarded(request, body.model_dump()))
    authorize(request, body.chat_id)
    if isinstance(response, StreamingResponse):
        response.body_iterator = revocable_stream(
            response.body_iterator,
            get_mobile_store(request),
            extract_token(request.scope.get("headers", [])),
            body.chat_id,
        )
    return response


async def list_approvals(request: Request) -> JSONResponse:
    from suzent.mobile.approvals import listing

    return await listing(request)


async def decide_approvals(request: Request) -> JSONResponse:
    from suzent.mobile.approvals import decide

    return await decide(request)


async def confirm_pairing(request: Request) -> JSONResponse:
    token = extract_token(request.scope.get("headers", []))
    if not get_mobile_store(request).confirm(token):
        raise HTTPException(401, "Mobile credential revoked or invalid")
    return reply({"ok": True})


client_routes = [
    Route("/mobile/client/pairing/confirm", confirm_pairing, methods=["POST"]),
    Route("/mobile/client/composer", composer, methods=["GET"]),
    Route("/mobile/client/projects", projects, methods=["GET"]),
    Route("/mobile/client/chats/{chat_id}/approvals", list_approvals, methods=["GET"]),
    Route("/mobile/client/approvals", decide_approvals, methods=["POST"]),
    Route("/mobile/client/session", session, methods=["GET"]),
    Route("/mobile/client/chats", chats, methods=["GET"]),
    Route("/mobile/client/chats", create, methods=["POST"]),
    Route("/mobile/client/chats/{chat_id}", chat, methods=["GET"]),
    Route("/mobile/client/send", send, methods=["POST"]),
    Route("/mobile/client/message-action", message_action, methods=["POST"]),
    Route("/mobile/client/stop", stop, methods=["POST"]),
    Route("/mobile/client/manage", manage, methods=["POST"]),
    Route("/mobile/client/live", observe, methods=["POST"]),
]
