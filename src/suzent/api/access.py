"""Authentication and resource authorization for every interactive client."""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError
from starlette.exceptions import HTTPException
from starlette.requests import HTTPConnection, Request

from suzent.auth_boundary import (
    extract_token,
    host_header_is_local,
    is_loopback,
    token_scope,
)
from suzent.mobile.pairing import ClientGrant, ClientPermissions
from suzent.routes.mobile_routes import get_mobile_store

_HOST_PERMISSIONS = ClientPermissions(
    all_chats=True,
    create_chats=True,
    manage_chats=True,
    send=True,
    stop=True,
    approve_tools=True,
)


@dataclass(frozen=True)
class Principal:
    grant: ClientGrant | None = None

    @property
    def permissions(self) -> ClientPermissions:
        return self.grant.permissions if self.grant else _HOST_PERMISSIONS

    @property
    def device_id(self) -> str:
        return self.grant.device_id if self.grant else "host"

    def model_dump(self) -> dict[str, object]:
        if self.grant:
            return self.grant.model_dump()
        return {
            "device_id": "host",
            "display_name": "Desktop",
            "platform": "desktop",
            "permissions": self.permissions.model_dump(),
        }


def principal(connection: HTTPConnection) -> Principal:
    token = extract_token(connection.scope.get("headers", []))
    legacy = connection.url.path.startswith("/mobile/")
    # The LAN/relay gateway deliberately replaces even a loopback caller's address.
    if (
        not legacy
        and not token
        and is_loopback(connection.client.host if connection.client else "")
        and host_header_is_local(connection.headers.get("host", ""))
    ):
        return Principal()
    grant = get_mobile_store(connection).verify(token)
    if grant is not None:
        return Principal(grant)
    if not legacy and connection.client and connection.client.host != "mobile-gateway":
        manager = getattr(connection.app.state, "node_manager", None)
        store = getattr(manager, "device_store", None)
        if token_scope(token, store) == "full":
            return Principal()
    raise HTTPException(401, "Credential revoked or invalid")


def is_host(connection: HTTPConnection) -> bool:
    return principal(connection).grant is None


def authorize(
    connection: HTTPConnection, chat_id: str | None = None, action: str = "read"
) -> Principal:
    identity = principal(connection)
    if chat_id is not None and not identity.permissions.permits_chat(chat_id):
        raise HTTPException(403, "Conversation not shared with this device")
    if action != "read" and not getattr(identity.permissions, action, False):
        raise HTTPException(403, "Action not permitted for this device")
    return identity


async def parse[T: BaseModel](request: Request, model: type[T]) -> T:
    try:
        return model.model_validate(await request.json())
    except (ValidationError, ValueError):
        raise HTTPException(400, "Invalid API request") from None


def forwarded(request: Request, body: dict) -> Request:
    result = Request(dict(request.scope), request.receive)
    result._body = json.dumps(body).encode()
    return result
