"""
System-related API routes for host interaction.
"""

import os
import sys
from pathlib import Path
from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.logger import get_logger

logger = get_logger(__name__)


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
                
                items = [{"name": d, "is_dir": True, "size": 0, "mtime": 0} for d in drives]
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
                    items.append({
                        "name": entry.name,
                        "is_dir": entry.is_dir(),
                        "size": stat.st_size,
                        "mtime": stat.st_mtime
                    })
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
