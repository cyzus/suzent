"""Locale routes for serving language pack JSON files."""

import json
import re
from pathlib import Path

import asyncio

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.config import PROJECT_DIR


_LOCALE_RE = re.compile(r"^[A-Za-z0-9-]{2,32}$")

_MAX_FILE_SIZE = 1024 * 1024  # 1 MB


def _read_locale_file(file_path: Path) -> str:
    """Read locale file synchronously (called via asyncio.to_thread)."""
    return file_path.read_text(encoding="utf-8")


async def get_language_pack(request: Request) -> JSONResponse:
    """Serve a locale JSON file as a language pack.

    Expects ``{meta: {...}, strings: {...}}`` shape but will serve
    any valid JSON dict, letting the frontend decide how to interpret it.
    """
    locale = request.path_params.get("locale") or ""
    if not isinstance(locale, str) or not _LOCALE_RE.match(locale):
        return JSONResponse({"error": "invalid_locale"}, status_code=400)

    locales_dir = PROJECT_DIR / "locales"
    file_path = (locales_dir / f"{locale}.json").resolve()

    try:
        locales_dir_resolved = locales_dir.resolve()
    except Exception:
        locales_dir_resolved = locales_dir

    # Prevent path traversal
    try:
        file_path.relative_to(locales_dir_resolved)
    except Exception:
        return JSONResponse({"error": "invalid_path"}, status_code=400)

    if not file_path.exists() or not file_path.is_file():
        return JSONResponse({"error": "not_found"}, status_code=404)

    # Use async file read to avoid blocking the event loop
    try:
        raw = await asyncio.to_thread(_read_locale_file, file_path)
    except Exception:
        return JSONResponse({"error": "read_failed"}, status_code=500)

    if len(raw) > _MAX_FILE_SIZE:
        return JSONResponse({"error": "too_large"}, status_code=413)

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"error": "invalid_json"}, status_code=500)

    if not isinstance(data, dict):
        return JSONResponse({"error": "invalid_format"}, status_code=500)

    return JSONResponse(data)
