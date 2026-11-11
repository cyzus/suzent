"""
System-related API routes for host interaction.
"""

import os
import sys
import subprocess
import platform
import time
from pathlib import Path
from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.logger import get_logger

# Re-exported: `suzent.version` is the light home for build identity, but
# `service.state` and `server` reach for it here.
from suzent.version import get_backend_commit as get_backend_commit
from suzent.version import get_backend_version as get_backend_version
from suzent.version import get_backend_source_root as get_backend_source_root
from suzent.version import get_build_source as get_build_source
from suzent.version import get_runtime_kind as get_runtime_kind

logger = get_logger(__name__)

API_VERSION = 1


def _installation_id() -> str:
    # Lazy: node_identity pulls user-config paths; keep version responses cheap
    # for callers that only need the package/commit fields.
    from suzent.nodes.node_identity import get_node_identity

    return get_node_identity()


def get_system_identity() -> dict[str, str | int | bool | None]:
    from suzent.config import get_data_dir

    source_root = get_backend_source_root()
    return {
        "backend_version": get_backend_version(),
        "api_version": API_VERSION,
        "build_commit": get_backend_commit(),
        "development_mode": os.getenv("SUZENT_DEV_MODE") == "1",
        "build_source": get_build_source(),
        "runtime": get_runtime_kind(),
        "installation_id": _installation_id(),
        "data_dir": str(get_data_dir()),
        "source_root": str(source_root) if source_root else None,
    }


async def get_system_version(_request: Request) -> JSONResponse:
    """Return version information for the running backend."""

    return JSONResponse(get_system_identity())


async def get_system_idle(_request: Request) -> JSONResponse:
    """Report whether no agent work has run recently, so the desktop app can
    restart into a staged update without interrupting anyone."""
    from suzent.service.auto_update import agents_idle

    return JSONResponse({"idle": agents_idle(time.time())})


async def list_host_files(request: Request) -> JSONResponse:
    """List files on the host system."""
    raw_path = request.query_params.get("path", "").strip()

    try:
        if not raw_path:
            # List drives on Windows
            if sys.platform == "win32":
                import string

                drives = []
                for letter in string.ascii_uppercase:
                    if os.path.exists(f"{letter}:\\"):
                        drives.append(f"{letter}:\\")

                items = [
                    {"name": d, "is_dir": True, "size": 0, "mtime": 0} for d in drives
                ]
                return JSONResponse({"path": "", "items": items})

            # Root for Linux/Mac
            raw_path = "/"

        path = Path(raw_path).resolve()

        if not path.exists():
            return JSONResponse({"error": "Path does not exist"}, status_code=404)

        if not path.is_dir():
            return JSONResponse({"error": "Not a directory"}, status_code=400)

        items = []
        try:
            for entry in path.iterdir():
                try:
                    # Skip hidden/system files if needed, but for now show all
                    stat = entry.stat()
                    items.append(
                        {
                            "name": entry.name,
                            "is_dir": entry.is_dir(),
                            "size": stat.st_size,
                            "mtime": stat.st_mtime,
                        }
                    )
                except Exception:
                    continue
        except PermissionError:
            return JSONResponse({"error": "Permission denied"}, status_code=403)

        # Sort: directories first, then files
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

        return JSONResponse({"path": str(path), "items": items})

    except Exception as e:
        logger.error(f"Error listing host files: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


def _resolve_existing_path(path_str: str, chat_id: str | None) -> Path | None:
    """Resolve a virtual or host path the chat may read to an existing host path.

    Uses the same resolver as the file preview, so project folders and the
    chat's working directory resolve here too.
    """
    if chat_id:
        from suzent.routes.sandbox_routes import _get_resolver_for_request

        try:
            resolved = _get_resolver_for_request(chat_id).resolve(path_str)
            if resolved and resolved.exists():
                return resolved
        except Exception as e:
            logger.debug(f"Path resolution failed (falling back to raw path): {e}")
    candidate = Path(path_str).resolve()
    return candidate if candidate.exists() else None


async def host_path(request: Request) -> JSONResponse:
    """Return where a file the chat can see lives on this computer."""
    try:
        data = await request.json()
    except ValueError:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    path_str = str(data.get("path", "")).strip()
    if not path_str:
        return JSONResponse({"error": "Path is required"}, status_code=400)
    path = _resolve_existing_path(path_str, data.get("chat_id"))
    if path is None:
        return JSONResponse({"error": "Path does not exist"}, status_code=404)
    return JSONResponse({"path": str(path)})


async def open_in_explorer(request: Request) -> JSONResponse:
    """Open a file or directory in the system's file explorer."""
    try:
        data = await request.json()
        path_str = data.get("path", "").strip()
        chat_id = data.get("chat_id")

        if not path_str:
            return JSONResponse({"error": "Path is required"}, status_code=400)

        path = _resolve_existing_path(path_str, chat_id)
        if path is None:
            logger.warning(f"Path not found: {path_str}")
            return JSONResponse({"error": "Path does not exist"}, status_code=404)

        logger.info(f"Opening in explorer: {path}")

        system = platform.system()

        if system == "Windows":
            # Windows: explorer /select, path handles both files (selects them) and dirs (opens them)
            # Note: The comma is important after /select
            subprocess.run(["explorer", "/select,", str(path)], check=False)
        elif system == "Darwin":
            # macOS: open -R path reveals in Finder
            subprocess.run(["open", "-R", str(path)], check=False)
        else:
            # Linux: xdg-open usually just opens. To reveal, we usually open the parent dir.
            # There isn't a standard "reveal" across all Linux DEs.
            target = path if path.is_dir() else path.parent
            subprocess.run(["xdg-open", str(target)], check=False)

        return JSONResponse({"status": "success"})

    except Exception as e:
        logger.error(f"Error opening in explorer: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
