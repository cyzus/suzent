import json
import re
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.config import PROJECT_DIR


_LOCALE_RE = re.compile(r"^[A-Za-z0-9-]{2,32}$")


async def get_language_pack(request: Request) -> JSONResponse:
    locale = request.path_params.get("locale") or ""
    if not isinstance(locale, str) or not _LOCALE_RE.match(locale):
        return JSONResponse({"error": "invalid_locale"}, status_code=400)

    locales_dir = PROJECT_DIR / "locales"
    file_path = (locales_dir / f"{locale}.json").resolve()

    try:
        locales_dir_resolved = locales_dir.resolve()
    except Exception:
        locales_dir_resolved = locales_dir

    try:
        file_path.relative_to(locales_dir_resolved)
    except Exception:
        return JSONResponse({"error": "invalid_path"}, status_code=400)

    if not file_path.exists() or not file_path.is_file():
        return JSONResponse({"error": "not_found"}, status_code=404)

    try:
        raw = file_path.read_text(encoding="utf-8")
    except Exception:
        return JSONResponse({"error": "read_failed"}, status_code=500)

    if len(raw) > 1024 * 1024:
        return JSONResponse({"error": "too_large"}, status_code=413)

    try:
        data = json.loads(raw)
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    if not isinstance(data, dict):
        return JSONResponse({"error": "invalid_format"}, status_code=400)

    return JSONResponse(data)
