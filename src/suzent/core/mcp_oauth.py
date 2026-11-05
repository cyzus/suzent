"""OAuth sign-in for hosted MCP servers, with tokens kept in Suzent's secret store.

FastMCP's ``OAuth`` does discovery, client registration, PKCE and refresh.
Suzent adds two things around it:

- **Persistent tokens.** ``SecretKeyValueStore`` puts FastMCP's token cache in
  ``core/secrets.py`` (the OS keychain, or the encrypted database), so a
  restart doesn't sign the user out.
- **Sign-in only from Settings.** During an agent run the provider never
  opens a browser: when it has no usable token it raises
  ``SignInRequired``. ``start_sign_in`` is the one place that runs the
  browser flow, and it hands the authorization URL to the caller (the
  settings page opens it) instead of opening a browser on the server.

The access token is only ever sent to the MCP server as a bearer header. No
tool returns it, and it never enters the model's context.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Literal

from key_value.aio._utils.managed_entry import ManagedEntry
from key_value.aio._utils.serialization import BasicSerializationAdapter
from key_value.aio.stores.base import BaseStore

from suzent.core.secrets import get_secret_manager
from suzent.logger import get_logger

logger = get_logger(__name__)

_KEY_PREFIX = "SUZENT_MCP_OAUTH"
#: How long a started sign-in waits for the browser to come back.
SIGN_IN_TIMEOUT_SECONDS = 300.0


class SignInRequired(RuntimeError):
    """The server needs the user to sign in again from Settings."""


def secret_key(namespace: str, collection: str, key: str) -> str:
    # Keychain entries are flat strings; keep each FastMCP record in its own one
    # so no single entry grows past what Windows Credential Manager accepts.
    return f"{_KEY_PREFIX}::{namespace}::{collection}::{key}"


class SecretKeyValueStore(BaseStore):
    """FastMCP's ``AsyncKeyValue`` token cache, stored in Suzent's secrets.

    ``namespace`` keeps each server's records apart, so signing out of one
    removes only its own.
    """

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self._adapter = BasicSerializationAdapter(date_format="isoformat")
        super().__init__(stable_api=True)

    async def _get_managed_entry(
        self, *, key: str, collection: str
    ) -> ManagedEntry | None:
        raw = await asyncio.to_thread(
            get_secret_manager().get_backend_only,
            secret_key(self.namespace, collection, key),
        )
        if not raw:
            return None
        return self._adapter.load_json(json_str=raw)

    async def _put_managed_entry(
        self, *, key: str, collection: str, managed_entry: ManagedEntry
    ) -> None:
        raw = self._adapter.dump_json(
            entry=managed_entry, key=key, collection=collection
        )
        await asyncio.to_thread(
            get_secret_manager().set_backend_only,
            secret_key(self.namespace, collection, key),
            raw,
        )

    async def _delete_managed_entry(self, *, key: str, collection: str) -> bool:
        name = secret_key(self.namespace, collection, key)
        manager = get_secret_manager()
        existed = await asyncio.to_thread(manager.has_backend_value, name)
        if existed:
            await asyncio.to_thread(manager.delete, name)
        return existed


def clear_namespace(namespace: str) -> None:
    """Forget every token and client registration stored for ``namespace``."""
    manager = get_secret_manager()
    prefix = f"{_KEY_PREFIX}::{namespace}::"
    for name in manager.list_keys():
        if name.startswith(prefix):
            manager.delete(name)


def has_stored_tokens(namespace: str) -> bool:
    prefix = f"{_KEY_PREFIX}::{namespace}::mcp-oauth-token::"
    manager = get_secret_manager()
    return any(
        name.startswith(prefix) and manager.has_backend_value(name)
        for name in manager.list_keys()
    )


def _oauth_class():
    from fastmcp.client.auth.oauth import OAuth

    class SuzentOAuth(OAuth):
        """FastMCP ``OAuth`` that asks the caller to open the browser.

        Outside a sign-in (``on_authorize`` unset) it refuses to start the
        browser flow, so a run whose refresh token stopped working fails fast
        instead of waiting for a login nobody sees.
        """

        def __init__(self, *args: Any, on_authorize=None, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._on_authorize = on_authorize

        async def redirect_handler(self, authorization_url: str) -> None:
            if self._on_authorize is None:
                raise SignInRequired(
                    "Sign in again from Settings → Plugins to use this service."
                )
            self._on_authorize(authorization_url)

    return SuzentOAuth


def build_oauth(
    namespace: str,
    url: str,
    *,
    scopes: list[str] | None = None,
    on_authorize=None,
):
    """A FastMCP ``httpx.Auth`` for ``url`` whose tokens live under ``namespace``."""
    return _oauth_class()(
        url,
        scopes=scopes,
        client_name="Suzent",
        token_storage=SecretKeyValueStore(namespace),
        callback_host="127.0.0.1",
        callback_timeout=SIGN_IN_TIMEOUT_SECONDS,
        on_authorize=on_authorize,
    )


def build_client(namespace: str, url: str, *, scopes: list[str] | None = None):
    """A FastMCP client for an agent run: refreshes tokens, never signs in."""
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    return Client(
        StreamableHttpTransport(url, auth=build_oauth(namespace, url, scopes=scopes))
    )


SignInState = Literal["idle", "waiting", "signed_in", "failed"]


@dataclass
class SignIn:
    namespace: str
    state: SignInState = "idle"
    authorize_url: str | None = None
    error: str | None = None
    task: asyncio.Task | None = field(default=None, repr=False)


_sign_ins: dict[str, SignIn] = {}


def sign_in_status(namespace: str) -> SignIn | None:
    return _sign_ins.get(namespace)


async def start_sign_in(
    namespace: str,
    url: str,
    *,
    scopes: list[str] | None = None,
    on_success=None,
) -> SignIn:
    """Begin the browser sign-in and return once the authorization URL is known.

    The flow then waits in the background for the browser to come back to the
    loopback callback on this machine. ``on_success`` runs after the tokens
    are stored, for example to rebuild the agent.
    """
    previous = _sign_ins.get(namespace)
    if previous is not None and previous.task is not None:
        previous.task.cancel()
    # The loopback port changes per sign-in, and a client registered with an
    # old redirect address would be refused; register afresh each time.
    await asyncio.to_thread(clear_namespace, namespace)

    sign_in = SignIn(namespace=namespace, state="waiting")
    _sign_ins[namespace] = sign_in
    loop = asyncio.get_running_loop()
    url_ready: asyncio.Future[str] = loop.create_future()

    def on_authorize(authorization_url: str) -> None:
        sign_in.authorize_url = authorization_url
        if not url_ready.done():
            url_ready.set_result(authorization_url)

    async def run() -> None:
        from fastmcp import Client
        from fastmcp.client.transports import StreamableHttpTransport

        auth = build_oauth(namespace, url, scopes=scopes, on_authorize=on_authorize)
        try:
            async with Client(StreamableHttpTransport(url, auth=auth)) as client:
                await client.list_tools()
        except asyncio.CancelledError:
            sign_in.state = "failed"
            sign_in.error = "Sign-in was cancelled."
            raise
        except Exception as exc:
            sign_in.state, sign_in.error = "failed", _describe_error(exc)
            logger.warning("MCP sign-in for {} failed: {}", namespace, sign_in.error)
            if not url_ready.done():
                url_ready.set_exception(exc)
            return
        sign_in.state, sign_in.error = "signed_in", None
        logger.info("Signed in to MCP server {}", namespace)
        if not url_ready.done():
            # Stored tokens were still valid: no browser step was needed.
            url_ready.set_result("")
        if on_success is not None:
            try:
                on_success()
            except Exception as exc:
                logger.warning("After sign-in to {}: {}", namespace, exc)

    sign_in.task = asyncio.create_task(run())
    try:
        await asyncio.wait_for(asyncio.shield(url_ready), timeout=30)
    except asyncio.TimeoutError:
        sign_in.task.cancel()
        url_ready.cancel()
        sign_in.state, sign_in.error = "failed", "The server did not answer in time."
    except Exception:
        pass  # Recorded on sign_in by run().
    return sign_in


def sign_out(namespace: str) -> None:
    previous = _sign_ins.pop(namespace, None)
    if previous is not None and previous.task is not None:
        previous.task.cancel()
    clear_namespace(namespace)


def _describe_error(exc: BaseException) -> str:
    # Exception groups from anyio task groups hide the real cause.
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    message = str(exc) or type(exc).__name__
    try:
        json.dumps(message)
    except (TypeError, ValueError):
        message = type(exc).__name__
    return message[:300]
