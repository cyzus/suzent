import os
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlsplit

import httpx


class ClientError(Exception):
    pass


def get_server_url() -> str:
    """Get the server URL from environment or default."""

    # 1. Environment variable (explicit override)
    port = os.getenv("SUZENT_PORT")

    if port == "0":
        port = None

    # 2. File (running instance)
    if not port:
        try:
            from suzent.config import RUNTIME_DIR

            port_file = RUNTIME_DIR / "server.port"
            if port_file.exists():
                port = port_file.read_text(encoding="utf-8").strip()

        except Exception:
            pass

    # 3. Default
    if not port:
        from suzent.config import DEFAULT_PORT

        port = str(DEFAULT_PORT)

    host = os.getenv("SUZENT_HOST", "localhost")
    return os.getenv("SUZENT_SERVER_URL", f"http://{host}:{port}")


def _is_loopback_url(url: str) -> bool:
    """Return whether *url* targets the local machine's loopback interface."""
    hostname = urlsplit(url).hostname
    if hostname is None:
        return False

    normalized_hostname = hostname.rstrip(".").lower()
    if normalized_hostname == "localhost" or normalized_hostname.endswith(".localhost"):
        return True

    try:
        address = ip_address(normalized_hostname)
    except ValueError:
        return False

    if address.is_loopback:
        return True
    mapped_address = getattr(address, "ipv4_mapped", None)
    return mapped_address is not None and mapped_address.is_loopback


class AsyncBaseClient:
    """Base async client providing HTTP wrappers around httpx."""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or get_server_url()
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30.0,
            trust_env=not _is_loopback_url(self.base_url),
        )

    async def get(self, path: str, **kwargs) -> Any:
        try:
            res = await self._client.get(path, **kwargs)
            res.raise_for_status()
            return res.json()
        except httpx.ConnectError:
            raise ClientError("Cannot connect to Suzent server. Is it running?")
        except httpx.HTTPStatusError as e:
            try:
                detail = e.response.json().get("error", str(e))
            except Exception:
                detail = str(e)
            raise ClientError(f"Server error ({e.response.status_code}): {detail}")

    async def post(self, path: str, json: dict | None = None, **kwargs) -> Any:
        try:
            res = await self._client.post(path, json=json or {}, **kwargs)
            res.raise_for_status()
            return res.json()
        except httpx.ConnectError:
            raise ClientError("Cannot connect to Suzent server. Is it running?")
        except httpx.HTTPStatusError as e:
            try:
                detail = e.response.json().get("error", str(e))
            except Exception:
                detail = str(e)
            raise ClientError(f"Server error ({e.response.status_code}): {detail}")

    async def put(self, path: str, json: dict | None = None, **kwargs) -> Any:
        try:
            res = await self._client.put(path, json=json or {}, **kwargs)
            res.raise_for_status()
            return res.json()
        except httpx.ConnectError:
            raise ClientError("Cannot connect to Suzent server. Is it running?")
        except httpx.HTTPStatusError as e:
            try:
                detail = e.response.json().get("error", str(e))
            except Exception:
                detail = str(e)
            raise ClientError(f"Server error ({e.response.status_code}): {detail}")

    async def delete(self, path: str, **kwargs) -> Any:
        try:
            res = await self._client.delete(path, **kwargs)
            res.raise_for_status()
            return res.json()
        except httpx.ConnectError:
            raise ClientError("Cannot connect to Suzent server. Is it running?")
        except httpx.HTTPStatusError as e:
            try:
                detail = e.response.json().get("error", str(e))
            except Exception:
                detail = str(e)
            raise ClientError(f"Server error ({e.response.status_code}): {detail}")

    async def stream_post(self, path: str, json: dict | None = None, **kwargs):
        """Yields chunks of the stream response."""
        timeout = kwargs.pop("timeout", 60.0)
        try:
            async with self._client.stream(
                "POST", path, json=json or {}, timeout=timeout, **kwargs
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    yield chunk
        except httpx.ConnectError:
            raise ClientError("Cannot connect to Suzent server. Is it running?")
        except httpx.HTTPStatusError as e:
            raise ClientError(f"Server streaming error: {e}")
