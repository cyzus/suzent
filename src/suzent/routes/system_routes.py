"""
System-related API routes for host interaction.
"""

import os
import sys
import subprocess
import platform
from pathlib import Path
from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.logger import get_logger
from suzent.tools.path_resolver import PathResolver
from suzent.database import get_database
from suzent.config import get_effective_volumes

logger = get_logger(__name__)


def _get_resolver(chat_id: str) -> PathResolver:
    """Helper to create a PathResolver instance for the request context."""
    custom_volumes = []
    try:
        db = get_database()
        chat = db.get_chat(chat_id)
        if chat and "config" in chat:
            cv = chat["config"].get("sandbox_volumes", [])
            custom_volumes = get_effective_volumes(cv)
        else:
            custom_volumes = get_effective_volumes([])
    except Exception as e:
        logger.warning(f"Failed to fetch chat config for volumes: {e}")
        custom_volumes = get_effective_volumes([])

    return PathResolver(
        chat_id=chat_id, sandbox_enabled=True, custom_volumes=custom_volumes
    )


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


async def open_in_explorer(request: Request) -> JSONResponse:
    """Open a file or directory in the system's file explorer."""
    try:
        data = await request.json()
        path_str = data.get("path", "").strip()
        chat_id = data.get("chat_id")

        if not path_str:
            return JSONResponse({"error": "Path is required"}, status_code=400)

        path = None

        # Try to resolve path if chat_id is provided (supports virtual paths)
        if chat_id:
            try:
                resolver = _get_resolver(chat_id)
                resolved = resolver.resolve(path_str)
                if resolved and resolved.exists():
                    path = resolved
            except Exception as e:
                logger.debug(f"Path resolution failed (falling back to raw path): {e}")

        # Fallback to raw path if resolution failed or no chat_id
        if not path:
            candidate = Path(path_str).resolve()
            if candidate.exists():
                path = candidate

        # Final check
        if not path or not path.exists():
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
