"""Interactive terminal pairing and per-client local credential storage."""

import asyncio
import base64
import contextlib
import hashlib
import json
import os
import secrets
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from suzent.acp.pairing import private_write
from suzent.client.base import AsyncBaseClient, ClientError, _is_loopback_url


def _windows_protect(data: bytes, *, decrypt: bool = False) -> bytes:
    """Bind a credential to the current Windows user using DPAPI."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.c_void_p)]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.c_void_p))
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not function(
        ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)
    ):
        raise OSError("Windows credential protection failed")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


def credential_path(base_url: str, client_name: str) -> Path:
    from suzent.config import USER_CONFIG_DIR

    key = hashlib.sha256(f"{base_url.rstrip('/')}\n{client_name}".encode()).hexdigest()
    return USER_CONFIG_DIR / "acp_credentials" / f"{key}.json"


def save_credential(path: Path, token: str) -> None:
    if os.name == "nt":
        private_write(
            path, {"dpapi": base64.b64encode(_windows_protect(token.encode())).decode()}
        )
    else:
        private_write(path, {"token": token})


def load_credential(base_url: str, client_name: str) -> str:
    try:
        value = json.loads(
            credential_path(base_url, client_name).read_text(encoding="utf-8")
        )
        if os.name == "nt":
            return _windows_protect(
                base64.b64decode(value["dpapi"]), decrypt=True
            ).decode()
        return str(value.get("token") or "")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return ""


async def terminal_login(
    base_url: str | None,
    client_name: str,
    *,
    report: Callable[[str], None],
    timeout: float = 300.0,
) -> int:
    client = AsyncBaseClient(base_url)
    request_id = ""
    completed = False
    secret = secrets.token_urlsafe(32)
    headers = {"Authorization": f"Bearer {secret}"}
    try:
        if not _is_loopback_url(client.base_url):
            report("ACP pairing requires a local Suzent backend.")
            return 1
        if (
            not client_name.strip()
            or len(client_name) > 100
            or any(ord(c) < 32 or ord(c) == 127 for c in client_name)
        ):
            report("Invalid ACP client name.")
            return 1
        pending = await client.post(
            "/acp/auth/pair", json={"client_name": client_name}, headers=headers
        )
        request_id = pending["request_id"]
        report(
            f"Open Suzent → Settings → ACP Agents → Editor connections.\n"
            f"Approve {client_name!r} only if the displayed code matches: {pending['code']}\n"
            "This grants access to conversations created by this authorization and their workspace tools.\n"
            "Waiting for approval; press Ctrl+C to cancel."
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = await client.post(
                f"/acp/auth/requests/{request_id}/collect", headers=headers
            )
            if result["status"] == "approved":
                save_credential(credential_path(client.base_url, client_name), secret)
                completed = True
                report(
                    "Suzent authorization saved. Return to your editor and reconnect."
                )
                return 0
            if result["status"] == "denied":
                report("Authorization was declined in Suzent.")
                return 1
            await asyncio.sleep(1)
        report("Authorization expired. Run login again to request approval.")
        return 1
    except (ClientError, httpx.HTTPError):
        report(
            "Cannot complete pairing. Start Suzent (or run `suzent serve`), open Settings → ACP Agents, and try again."
        )
        return 1
    except (OSError, ValueError, KeyError):
        report("Could not save or validate the ACP authorization. Please try again.")
        return 1
    finally:
        if request_id and not completed:
            with contextlib.suppress(ClientError, httpx.HTTPError):
                await client.post(
                    f"/acp/auth/requests/{request_id}/cancel", headers=headers
                )
        await client.aclose()
