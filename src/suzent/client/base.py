import os
from pathlib import Path
from typing import Any

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
            from suzent.config import DATA_DIR

            port_file = DATA_DIR / "server.port"
            if port_file.exists():
                port = port_file.read_text(encoding="utf-8").strip()

            if not port:
                import platform

                system = platform.system()
                prod_dir = None

                if system == "Windows":
                    roaming = os.getenv("APPDATA")
                    if roaming:
                        prod_dir = Path(roaming) / "com.suzent.app"
                elif system == "Darwin":
                    prod_dir = (
                        Path.home() / "Library/Application Support/com.suzent.app"
                    )
                else:  # Linux
                    xdg = os.getenv("XDG_DATA_HOME")
                    if xdg:
                        prod_dir = Path(xdg) / "com.suzent.app"
                    else:
                        prod_dir = Path.home() / ".local/share/com.suzent.app"

                if prod_dir:
                    prod_port_file = prod_dir / "server.port"

                    if prod_port_file.exists():
                        port = prod_port_file.read_text(encoding="utf-8").strip()
                    else:
                        nested = prod_dir / ".suzent" / "server.port"
                        if nested.exists():
                            port = nested.read_text(encoding="utf-8").strip()

        except Exception:
            pass

    # 3. Default
    if not port:
        port = "25314"

    host = os.getenv("SUZENT_HOST", "localhost")
    return os.getenv("SUZENT_SERVER_URL", f"http://{host}:{port}")


class AsyncBaseClient:
    """Base async client providing HTTP wrappers around httpx."""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or get_server_url()
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

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
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=60.0
            ) as client:
                async with client.stream(
                    "POST", path, json=json or {}, **kwargs
                ) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.aiter_bytes():
                        yield chunk
        except httpx.ConnectError:
            raise ClientError("Cannot connect to Suzent server. Is it running?")
        except httpx.HTTPStatusError as e:
            raise ClientError(f"Server streaming error: {e}")
