"""Resource routes share one principal/policy boundary across desktop and devices."""

from __future__ import annotations

from importlib import import_module
from collections.abc import Awaitable, Callable
from typing import Any
from starlette.exceptions import HTTPException
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Route, WebSocketRoute
from starlette.websockets import WebSocket
from suzent.api.access import authorize, parse
from suzent.api.contracts import EmptyRequest
from suzent.api.operations import LEGACY_PATHS, OPERATIONS, Operation


def handler(name: str) -> Callable[..., Awaitable[Any]]:
    if "." not in name:
        return getattr(import_module("suzent.api.resources"), name)
    module, name = name.split(".", 1)
    return getattr(import_module("suzent.routes." + module), name)


def endpoint(operation: Operation) -> Callable[[Request], Awaitable[Response]]:
    async def dispatch(request: Request) -> Response:
        identity = authorize(request)
        host = identity.grant is None
        if operation.host_only and not host:
            raise HTTPException(403, "Host access required")
        for action in operation.actions:
            authorize(request, action=action)
        if (
            operation.request
            and not (host and operation.host_handler)
            and request.url.path.startswith("/api/v1/")
        ):
            if operation.request is not EmptyRequest or await request.body():
                await parse(request, operation.request)
        if operation.query:
            try:
                operation.query.model_validate(dict(request.query_params))
            except ValidationError:
                raise HTTPException(400, "Invalid query parameters") from None
        chat_id = None
        if operation.chat == "path":
            chat_id = request.path_params.get("chat_id")
        elif operation.chat == "query":
            chat_id = request.query_params.get("chat_id")
        elif operation.chat == "body":
            try:
                body = await request.json()
                chat_id = body.get("chat_id") if isinstance(body, dict) else None
            except ValueError:
                raise HTTPException(400, "Invalid API request") from None
        for action in operation.actions or ("read",):
            authorize(request, chat_id, action)
        target = (
            operation.host_handler
            if host and operation.host_handler
            else operation.handler
        )
        return await handler(target)(request)

    dispatch.__name__ = operation.name
    return dispatch


async def capabilities(request: Request) -> JSONResponse:
    identity = authorize(request)
    return JSONResponse(
        {
            "version": 1,
            "operations": [
                op.name
                for op in OPERATIONS
                if (not op.host_only or identity.grant is None)
                and all(
                    getattr(identity.permissions, action, False)
                    for action in op.actions
                )
            ],
        },
        headers={"Cache-Control": "no-store"},
    )


async def openapi(request: Request) -> JSONResponse:
    authorize(request)
    from suzent.api.schema import contract

    return JSONResponse(contract(), headers={"Cache-Control": "no-store"})


def websocket_endpoint(operation: Operation) -> Callable[[WebSocket], Awaitable[None]]:
    async def dispatch(connection: WebSocket) -> None:
        await handler(operation.handler)(connection)

    return dispatch


def build_legacy_routes() -> list[BaseRoute]:
    routes = [
        WebSocketRoute(LEGACY_PATHS[op.name], websocket_endpoint(op))
        if op.transport == "websocket"
        else Route(LEGACY_PATHS[op.name], endpoint(op), methods=[op.method])
        for op in OPERATIONS
        if op.name in LEGACY_PATHS
    ]
    routes.extend(
        [
            Route(
                "/mobile/client/pairing/confirm",
                handler("confirm_pairing"),
                methods=["POST"],
            ),
            Route(
                "/mobile/client/pairing/forget",
                handler("forget_pairing"),
                methods=["POST"],
            ),
        ]
    )
    return routes


resource_routes = [
    Route("/api/v1/capabilities", capabilities, methods=["GET"]),
    Route("/api/v1/openapi.json", openapi, methods=["GET"]),
] + [
    WebSocketRoute("/api/v1" + op.path, websocket_endpoint(op))
    if op.transport == "websocket"
    else Route("/api/v1" + op.path, endpoint(op), methods=[op.method])
    for op in OPERATIONS
]
