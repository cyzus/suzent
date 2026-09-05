import asyncio
import io
import re
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.websockets import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from suzent.auth_boundary import is_loopback
from suzent.browser_extension.bridge import bridge, ExtensionMessage, ExtensionHello
from suzent.browser_extension.session import session
from suzent.browser_extension.install import install_native_host
from suzent.logger import get_logger

logger = get_logger(__name__)


def local_setup_request(request: Request) -> bool:
    if not request.client or not is_loopback(request.client.host):
        return False
    origin = request.headers.get("origin")
    if not origin:
        return True
    if origin in {
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    }:
        return True
    try:
        parsed = urlsplit(origin)
        return (
            parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "localhost"}
            and parsed.port in {18080, 8000, request.url.port}
        )
    except ValueError:
        return False


async def extension_settings(request: Request) -> Response:
    if not local_setup_request(request):
        return JSONResponse(
            {"error": "Browser setup requires the local Suzent app"}, status_code=403
        )
    if request.method in {"POST", "DELETE"}:
        if request.headers.get("x-suzent-browser-setup") != "1":
            return JSONResponse({"error": "Invalid setup request"}, status_code=403)
        async with bridge.pairing_lock:
            await bridge.revoke()
            await session.close()
            if request.method == "POST":
                token = bridge.create_pairing()
                return JSONResponse(
                    {
                        "url": f"http://127.0.0.1:{request.url.port or 80}/browser/extension/connect#{token}"
                    },
                    headers={"Cache-Control": "no-store"},
                )
    return JSONResponse(
        {"connected": bridge.socket is not None}, headers={"Cache-Control": "no-store"}
    )


async def extension_connect_page(request: Request) -> Response:
    return HTMLResponse(
        '<!doctype html><meta charset="utf-8"><title>Suzent</title>'
        "<h1>Suzent browser connection</h1>"
        "<p>If the extension is installed in this browser, pairing will start automatically. "
        "Return to Settings → Browser to check the connection. Otherwise install the extension, then click Pair browser again.</p>"
        "<p>如果已安装扩展，将自动开始配对。请返回设置 → 浏览器检查连接；否则请先安装扩展，再点击配对浏览器。</p>",
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
        },
    )


async def extension_download(request: Request) -> Response:
    if not local_setup_request(request):
        return Response(status_code=403)

    def archive() -> bytes:
        buffer = io.BytesIO()
        root = Path(__file__).parent / "assets"
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as output:
            for path in root.rglob("*"):
                if path.is_file():
                    output.write(path, path.relative_to(root).as_posix())
        return buffer.getvalue()

    return Response(
        await asyncio.to_thread(archive),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="suzent-browser-extension.zip"'
        },
    )


async def extension_websocket(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin", "")
    if (
        not websocket.client
        or not is_loopback(websocket.client.host)
        or not re.fullmatch(r"chrome-extension://[a-p]{32}", origin)
    ):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        hello = ExtensionHello.model_validate(
            await asyncio.wait_for(websocket.receive_json(), timeout=5)
        )
        async with bridge.pairing_lock:
            if not bridge.authenticate(hello.token, origin):
                await websocket.close(code=1008)
                return
            try:
                await asyncio.to_thread(install_native_host, origin)
            except OSError:
                logger.warning(
                    "Could not install browser endpoint discovery; re-pair if the backend port changes"
                )
            if bridge.socket:
                await bridge.socket.close(code=1000)
            bridge.disconnected()
            bridge.socket = websocket
            await websocket.send_json({"type": "ready"})
        while True:
            raw = await websocket.receive_text()
            if len(raw) > 8_000_000:
                await websocket.close(code=1009)
                return
            message = ExtensionMessage.model_validate_json(raw)
            if message.type == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await bridge.receive(message)
    except (WebSocketDisconnect, TimeoutError, ValidationError, ValueError, OSError):
        try:
            await websocket.close(code=1008)
        except RuntimeError:
            pass
    finally:
        if bridge.socket is websocket:
            bridge.disconnected()
            session.selected = None
            session.streaming = False
            session.invalidate()
            for client in list(session.clients):
                try:
                    await client.send_json({"type": "reset"})
                except Exception:
                    pass
