"""Hosted services a plugin connects the agent to, through their MCP servers.

A plugin declares an ``Integration`` with ``ctx.register_integration()``: how
the user signs in, and how to build the service's toolset once they have.
Suzent owns the rest: it stores the credential in its secret store, shows the
sign-in on the plugins page, and wraps every toolset so calls the server does
not mark read-only go through the user's tool approvals, like any MCP server.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from suzent.logger import get_logger

logger = get_logger(__name__)

AuthKind = Literal["oauth", "token"]

#: Secret store prefix for tokens the user pastes in (``auth="token"``).
TOKEN_KEY_PREFIX = "SUZENT_MCP_TOKEN::"


@dataclass(frozen=True)
class Integration:
    """One hosted service.

    ``build`` receives what the sign-in produced and returns a pydantic-ai
    toolset: for ``auth="oauth"`` a FastMCP client that refreshes its own
    tokens, for ``auth="token"`` the token string. It runs when the agent is
    built, only while the user is signed in.
    """

    id: str
    name: str
    url: str
    auth: AuthKind
    build: Callable[[Any], Any] = field(repr=False)
    scopes: tuple[str, ...] = ()
    #: For ``auth="token"``: where the user creates one, shown next to the field.
    token_help_url: str | None = None


#: Why each connected integration last failed to connect, by namespace.
_last_errors: dict[str, str] = {}


def _tolerant(toolset: Any, key: str) -> Any:
    """Wrap ``toolset`` so a service that can't connect offers no tools.

    Without this, an expired sign-in or an unreachable service would fail
    every chat, since the agent connects all its toolsets before a run.
    """
    from pydantic_ai.toolsets import WrapperToolset

    class TolerantToolset(WrapperToolset):
        # None until entered; True or False after the last attempt to connect.
        _connected: bool | None = None

        async def __aenter__(self):
            try:
                await self.wrapped.__aenter__()
            except Exception as exc:
                self._connected = False
                self._fail(exc)
            else:
                self._connected = True
                _last_errors.pop(key, None)
            return self

        async def __aexit__(self, *args: Any):
            connected, self._connected = self._connected, None
            if not connected:
                return None
            try:
                return await self.wrapped.__aexit__(*args)
            except Exception as exc:
                logger.debug("Closing integration {} failed: {}", key, exc)
                return None

        async def get_tools(self, ctx):
            if self._connected is False:
                return {}
            try:
                return await self.wrapped.get_tools(ctx)
            except Exception as exc:
                self._fail(exc)
                return {}

        async def get_instructions(self, ctx):
            if self._connected is False:
                return None
            try:
                return await super().get_instructions(ctx)
            except Exception as exc:
                self._fail(exc)
                return None

        def _fail(self, exc: BaseException) -> None:
            from suzent.core.mcp_oauth import _describe_error

            _last_errors[key] = _describe_error(exc)
            logger.warning("Integration {} unavailable: {}", key, _last_errors[key])

    return TolerantToolset(toolset)


def last_error(plugin_id: str, integration: "Integration") -> str | None:
    return _last_errors.get(namespace(plugin_id, integration))


def forget_error(plugin_id: str, integration: "Integration") -> None:
    _last_errors.pop(namespace(plugin_id, integration), None)


def namespace(plugin_id: str, integration: Integration) -> str:
    return f"{plugin_id}.{integration.id}"


def token_key(plugin_id: str, integration: Integration) -> str:
    return f"{TOKEN_KEY_PREFIX}{namespace(plugin_id, integration)}"


def is_connected(plugin_id: str, integration: Integration) -> bool:
    from suzent.core.secrets import get_secret_manager

    if integration.auth == "token":
        return get_secret_manager().has_backend_value(token_key(plugin_id, integration))
    from suzent.core.mcp_oauth import has_stored_tokens

    return has_stored_tokens(namespace(plugin_id, integration))


def build_toolset(plugin_id: str, integration: Integration) -> Any | None:
    """The integration's toolset, or None while the user is not signed in."""
    if not is_connected(plugin_id, integration):
        return None
    if integration.auth == "token":
        from suzent.core.secrets import get_secret_manager

        credential = get_secret_manager().get_backend_only(
            token_key(plugin_id, integration)
        )
    else:
        from suzent.core.mcp_oauth import build_client

        credential = build_client(
            namespace(plugin_id, integration),
            integration.url,
            scopes=list(integration.scopes) or None,
        )
    return _tolerant(integration.build(credential), namespace(plugin_id, integration))


def connected_toolsets() -> list[Any]:
    """Toolsets of every connected integration of every loaded plugin."""
    from suzent.plugins import get_plugin_manager

    toolsets = []
    for record in get_plugin_manager().records():
        for integration in record.integrations:
            try:
                toolset = build_toolset(record.id, integration)
            except Exception as exc:
                # One broken service must not stop the agent from starting.
                logger.warning(
                    "Integration {}/{} unavailable: {}",
                    record.id,
                    integration.id,
                    exc,
                )
                continue
            if toolset is not None:
                toolsets.append(toolset)
    return toolsets


def find(plugin_id: str, integration_id: str) -> Integration | None:
    from suzent.plugins import get_plugin_manager

    for record in get_plugin_manager().records():
        if record.id == plugin_id:
            return next(
                (i for i in record.integrations if i.id == integration_id), None
            )
    return None


def describe(plugin_id: str, integration: Integration) -> dict[str, Any]:
    from suzent.core.mcp_oauth import sign_in_status

    data: dict[str, Any] = {
        "id": integration.id,
        "name": integration.name,
        "auth": integration.auth,
        "connected": is_connected(plugin_id, integration),
        "tokenHelpUrl": integration.token_help_url,
    }
    if data["connected"] and (error := last_error(plugin_id, integration)):
        data["error"] = error
    if integration.auth == "oauth":
        status = sign_in_status(namespace(plugin_id, integration))
        if status is not None and status.state in ("waiting", "failed"):
            data["signIn"] = {"state": status.state, "error": status.error}
    return data
