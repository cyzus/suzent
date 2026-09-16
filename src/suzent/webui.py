"""Serve the built frontend from the backend itself.

The desktop shell ships the same bundle inside Tauri, where the frontend and
the backend are separate processes glued by a port handshake. In web mode there
is no shell: the backend is the only process, so it also has to hand the browser
the SPA. Serving from one origin is what keeps ``getApiBase()`` empty on the
frontend side, which in turn makes the deployment work unchanged behind a
reverse proxy or a tunnel.

The bundle lives at ``suzent/webui/`` as package data. It is absent in a source
checkout that has not run ``npm run build`` and copied ``frontend/dist`` here,
so every route below degrades to "not built" rather than to a crash.
"""

from __future__ import annotations

import os
from pathlib import Path

from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

WEBUI_DIR = Path(__file__).parent / "webui"
INDEX_FILE = WEBUI_DIR / "index.html"


def webui_available() -> bool:
    """Whether a built SPA is present to serve."""
    return INDEX_FILE.is_file()


def webui_enabled() -> bool:
    """Whether this process should serve the SPA at all.

    ``SUZENT_SERVE_HEADLESS=1`` turns the backend into a pure API server — the
    right mode for a node that only ever talks to the desktop app or to peers,
    and for anyone fronting the SPA with their own static host.
    """
    if os.getenv("SUZENT_SERVE_HEADLESS", "").strip().lower() in {"1", "true", "yes"}:
        return False
    return webui_available()


def _bundled_file(relative: str) -> Path | None:
    """Resolve a request path to a file inside the bundle, or None.

    Anything that escapes the bundle — via "..", a symlink, or a path this
    filesystem rejects outright — resolves to None rather than to a file.
    """
    try:
        candidate = (WEBUI_DIR / relative).resolve()
        if candidate.is_file() and candidate.is_relative_to(WEBUI_DIR.resolve()):
            return candidate
    except OSError:
        pass
    return None


def _no_store(response: Response) -> Response:
    # index.html names hashed asset files; caching it would pin a browser to the
    # previous build after an upgrade. The hashed assets themselves are immutable.
    response.headers["Cache-Control"] = "no-store"
    return response


async def _serve_index(request) -> Response:
    if not webui_available():
        return JSONResponse(
            {"error": "web UI is not built into this install"}, status_code=404
        )
    return _no_store(FileResponse(INDEX_FILE))


async def _spa_fallback(request) -> Response:
    """Catch-all for client-side routes.

    Every API route is registered ahead of this one, so anything arriving here
    is either a static file of the bundle or a path the router owns. A request
    that does not want HTML (an API call to a route that does not exist, a probe)
    gets an honest 404 instead of a page.
    """
    path = request.path_params.get("path", "")
    if path and _bundled_file(path) is not None:
        return FileResponse(_bundled_file(path))

    if "text/html" not in request.headers.get("accept", ""):
        return JSONResponse({"error": "not found"}, status_code=404)
    return await _serve_index(request)


def webui_routes() -> list:
    """Routes that serve the SPA, or an empty list when it is not served."""
    if not webui_enabled():
        return []

    routes: list = [Route("/", _serve_index, methods=["GET"])]
    assets = WEBUI_DIR / "assets"
    if assets.is_dir():
        routes.append(Mount("/assets", StaticFiles(directory=assets)))
    routes.append(Route("/{path:path}", _spa_fallback, methods=["GET"]))
    return routes


def is_public_asset(path: str) -> bool:
    """Whether a path is part of the served SPA shell.

    The shell has to be fetchable before the browser holds anything, exactly as
    the ``/node`` pairing page is: it is the same public bundle the desktop app
    ships, and it carries no secrets. Every API call it then makes still passes
    through the normal auth boundary.

    Membership is decided by "does this resolve to a file inside the bundle",
    so the exemption cannot widen past the files actually shipped.
    """
    if not webui_enabled():
        return False
    if path in ("/", "/index.html"):
        return True
    return _bundled_file(path.lstrip("/")) is not None
