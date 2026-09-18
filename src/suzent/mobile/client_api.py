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
    from suzent.core.stream_registry import is_background_streaming

    return reply(
        {
            "chats": [
                {
                    "id": chat_id,
                    "title": title,
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

    config = data.get("config") or {}
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
            "model": (config.get("model") or get_default_chat_model())
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

    payload = body.model_dump(exclude={"model"})
    if body.model is not None:
        from suzent.core.providers import get_enabled_models_from_db

        chat = get_database().get_chat(body.chat_id)
        if chat is None:
            raise HTTPException(404, "Conversation unavailable")
        if (
            str((chat.config or {}).get("runtime", "native")).lower() == "acp"
            or body.model not in get_enabled_models_from_db()
        ):
            raise HTTPException(400, "Model unavailable for this conversation")
        payload["config"] = {"model": body.model}
    return await chat_send(forwarded(request, payload))


async def stop(request: Request) -> JSONResponse:
    body = await parse(request, ChatRequest)
    authorize(request, body.chat_id, "stop")
    from suzent.routes.chat_routes import stop_chat

    return await stop_chat(forwarded(request, body.model_dump()))


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
    Route("/mobile/client/stop", stop, methods=["POST"]),
    Route("/mobile/client/live", observe, methods=["POST"]),
]
