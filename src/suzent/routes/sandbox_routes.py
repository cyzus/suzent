"""
Sandbox-related API routes.
"""

import re
import json
import shutil
import mimetypes
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone
from starlette.requests import Request
from starlette.responses import JSONResponse, FileResponse


from suzent.logger import get_logger
from suzent.config import get_effective_volumes, CONFIG
from suzent.tools.path_resolver import PathResolver
from suzent.database import get_database

logger = get_logger(__name__)


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Comprehensive filename sanitization to prevent security issues.

    Args:
        filename: The original filename
        max_length: Maximum allowed filename length (default 255 for most filesystems)

    Returns:
        Sanitized filename safe for filesystem operations
    """
    if not filename:
        return "unnamed_file"

    # Remove null bytes (critical security issue)
    filename = filename.replace("\x00", "")

    # Get just the filename (no path components)

    filename = Path(filename).name

    # Remove or replace problematic characters
    # Keep: letters, numbers, dots, hyphens, underscores, spaces
    # Replace others with underscore
    filename = re.sub(r"[^\w\s.\-]", "_", filename)

    # Remove leading/trailing dots and spaces (can cause issues on Windows)
    filename = filename.strip(". ")

    # Prevent reserved names on Windows (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    reserved_names = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
    name_without_ext = filename.rsplit(".", 1)[0].upper()
    if name_without_ext in reserved_names:
        filename = f"_{filename}"

    # Enforce maximum length (leave room for extensions and timestamps)
    if len(filename) > max_length:
        # Try to preserve extension
        if "." in filename:
            name, ext = filename.rsplit(".", 1)
            max_name_length = max_length - len(ext) - 1
            filename = name[:max_name_length] + "." + ext
        else:
            filename = filename[:max_length]

    # Final check - if filename became empty, provide default
    if not filename or filename == ".":
        return "unnamed_file"

    return filename


def _get_resolver_for_request(
    chat_id: str, override_volumes: list[str] | None = None
) -> PathResolver:
    """Helper to create a PathResolver instance for the request context."""
    custom_volumes = []

    if override_volumes is not None:
        # trust the client provided volumes (e.g. from frontend state)
        # but still apply global defaults/skills via get_effective_volumes
        custom_volumes = get_effective_volumes(override_volumes)
    else:
        try:
            db = get_database()
            chat = db.get_chat(chat_id)
            if chat and "config" in chat:
                # Get raw volumes from chat config
                cv = chat["config"].get("sandbox_volumes", [])
                # Calculate effective volumes (merges global + chat + defaults like skills)
                custom_volumes = get_effective_volumes(cv)
                sandbox_enabled = chat["config"].get(
                    "sandbox_enabled", CONFIG.sandbox_enabled
                )
            else:
                # Even if no chat specific config, we want global defaults (like skills)
                custom_volumes = get_effective_volumes([])
                sandbox_enabled = CONFIG.sandbox_enabled
        except Exception as e:
            logger.warning(f"Failed to fetch chat config for volumes: {e}")
            # Fallback to defaults
            custom_volumes = get_effective_volumes([])
            sandbox_enabled = CONFIG.sandbox_enabled

    if override_volumes is not None and "sandbox_enabled" not in locals():
        sandbox_enabled = CONFIG.sandbox_enabled

    # Create resolver (sandbox_enabled=True implies sandbox paths /persistence etc)
    return PathResolver(
        chat_id=chat_id, sandbox_enabled=sandbox_enabled, custom_volumes=custom_volumes
    )


async def list_sandbox_files(request: Request) -> JSONResponse:
    """List files in sandbox directory."""
    chat_id = request.query_params.get("chat_id")
    raw_path = request.query_params.get("path", "/").strip()
    volumes_json = request.query_params.get("volumes")

    override_volumes = None
    if volumes_json:
        try:
            override_volumes = json.loads(volumes_json)
        except Exception:
            pass

    if not chat_id:
        return JSONResponse({"error": "chat_id is required"}, status_code=400)

    try:
        resolver = _get_resolver_for_request(chat_id, override_volumes=override_volumes)

        # Normalize request path
        request_path = raw_path.replace("\\", "/")
        if not request_path.startswith("/"):
            request_path = "/" + request_path
        if request_path != "/" and request_path.endswith("/"):
            request_path = request_path[:-1]

        items = []
        virtual_children = set()

        # 1. Virtual directory listing logic (parents of mounts)
        # SandboxFileView expects us to list "mnt" if we have "/mnt/data" and we are at "/"

        # Get all virtual roots
        roots = resolver.get_virtual_roots()  # List[Tuple[virtual_path, host_path]]

        # Collect virtual directories that are children of current path
        # e.g. if path="/", and we have "/mnt/data", we need to list "mnt"
        # e.g. if path="/mnt", and we have "/mnt/data", we need to list "data"

        parent_check_path = request_path if request_path == "/" else request_path + "/"

        for v_path, _ in roots:
            if v_path.startswith(parent_check_path):
                # It is a child (or grandchild) of current view
                suffix = v_path[len(parent_check_path) :]
                if "/" in suffix:
                    child = suffix.split("/")[0]
                else:
                    child = suffix

                if child:
                    virtual_children.add(child)

        for child in virtual_children:
            items.append({"name": child, "is_dir": True, "size": 0, "mtime": 0})

        # 2. Actual file listing
        # Try to resolve to a real path.
        # Note: If we are at "/" or "/mnt" which are purely virtual (no mapped host path yet),
        # resolver.resolve() might fail or default to persistence.
        # We only want to list REAL files if the path corresponds to a valid mount or inside one.

        try:
            # We use a slightly different check here.
            # We want to know if there is a real directory backing this path.
            # resolver.resolve() raises ValueError if path is invalid/traversal
            # It maps "/" to /persistence usually, or custom logic.

            # Let's see if we are inside a mount.
            # PathResolver.resolve maps unknown paths relative to session_dir.
            # But if request_path is just a virtual parent (like "/mnt"), it shouldn't map to persistence!

            # Check if this path IS a mount point or INSIDE one
            best_match = None
            best_match_len = 0
            selected_host_root = None

            # Re-implementing simplified logic from SandboxRoutes because PathResolver
            # doesn't expose "is this a purely virtual directory?" directly yet,
            # though get_virtual_roots gives us the map.

            for v_path, h_path in roots:
                if request_path == v_path or request_path.startswith(v_path + "/"):
                    if len(v_path) > best_match_len:
                        best_match = v_path
                        best_match_len = len(v_path)
                        selected_host_root = h_path

            if selected_host_root:
                # We are inside a mount
                if request_path == best_match:
                    target_host_path = selected_host_root
                else:
                    rel_path = request_path[len(best_match) :].lstrip("/")
                    target_host_path = (selected_host_root / rel_path).resolve()

                if target_host_path.exists() and target_host_path.is_dir():
                    for entry in target_host_path.iterdir():
                        try:
                            # Don't duplicate if it's already listed as a virtual child (unlikely but possible)
                            if entry.name not in virtual_children:
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
                            pass
            else:
                # If we are NOT in a mount (e.g. "/mnt" where only "/mnt/data" exists),
                # then we only show virtual children (which we already did).
                # Unless... "/" defaults to persistence?
                # PathResolver defaults "/" to persistence.
                # But if we treat "/" as purely virtual root for mounts, we might hide persistence if not explicit?
                # Actually, get_virtual_roots includes /persistence.
                # So if we are at "/", /persistence is a child.

                # Wait, PathResolver says:
                # roots.append(("/persistence", ...))
                # roots.append(("/shared", ...))

                # So if I am at "/", "persistence" and "shared" will be in virtual_children.
                # Accessing "/" directly doesn't list contents of persistence unless mapped to "/".
                # The current frontend expects "persistence" folder to show up?
                # Or does it expect "/" to SHOW the contents of persistence?

                # SandboxFiles.tsx default path is "/".
                # Old logic:
                # mounts["/persistence"] = ...
                # if request_path == "/": virtual_children adds "persistence", "shared".

                # So yes, at "/" we just show the folders "persistence", "shared", "mnt" etc.
                # We do NOT list files inside persistence at root.
                pass

        except Exception:
            # If resolution fails, we just return what we have (virtual items)
            pass

        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return JSONResponse({"path": request_path, "items": items})

    except Exception as e:
        logger.error(f"Error listing files: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def read_sandbox_file(request: Request) -> JSONResponse:
    """Read file content from sandbox."""
    chat_id = request.query_params.get("chat_id")
    raw_path = request.query_params.get("path", "").strip()
    volumes_json = request.query_params.get("volumes")

    override_volumes = None
    if volumes_json:
        try:
            override_volumes = json.loads(volumes_json)
        except Exception:
            pass

    if not chat_id:
        return JSONResponse({"error": "chat_id is required"}, status_code=400)
    if not raw_path:
        return JSONResponse({"error": "path is required"}, status_code=400)

    try:
        resolver = _get_resolver_for_request(chat_id, override_volumes=override_volumes)
        target_host_path = resolver.resolve(raw_path)

        if not target_host_path.exists():
            return JSONResponse({"error": "File not found"}, status_code=404)

        if not target_host_path.is_file():
            return JSONResponse({"error": "Not a file"}, status_code=400)

        # Read content (text or base64)
        try:
            content = target_host_path.read_text(encoding="utf-8")
            return JSONResponse(
                {"path": raw_path, "content": content, "is_binary": False}
            )
        except UnicodeDecodeError:
            import base64

            binary_content = target_host_path.read_bytes()
            encoded_content = base64.b64encode(binary_content).decode("ascii")
            return JSONResponse(
                {"path": raw_path, "content": encoded_content, "is_binary": True}
            )
        except Exception as e:
            return JSONResponse({"error": f"Failed to read file: {e}"}, status_code=500)

    except ValueError as ve:
        return JSONResponse({"error": str(ve)}, status_code=403)
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def write_sandbox_file(request: Request) -> JSONResponse:
    """Write content to a sandbox file."""
    try:
        body = await request.json()
        chat_id = request.query_params.get("chat_id")
        raw_path = body.get("path", "").strip()
        content = body.get("content", "")

        if not chat_id:
            return JSONResponse({"error": "chat_id is required"}, status_code=400)
        if not raw_path:
            return JSONResponse({"error": "path is required"}, status_code=400)

        volumes_json = request.query_params.get("volumes")
        override_volumes = None
        if volumes_json:
            try:
                override_volumes = json.loads(volumes_json)
            except Exception:
                pass

        resolver = _get_resolver_for_request(chat_id, override_volumes=override_volumes)
        try:
            target_host_path = resolver.resolve(raw_path)
        except ValueError as ve:
            return JSONResponse({"error": str(ve)}, status_code=403)

        # Ensure parent directory exists
        target_host_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        target_host_path.write_text(content, encoding="utf-8")

        size = len(content)
        return JSONResponse({"path": raw_path, "size": size, "status": "written"})

    except Exception as e:
        logger.error(f"Error writing file: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def delete_sandbox_file(request: Request) -> JSONResponse:
    """Delete a file or directory in sandbox."""
    chat_id = request.query_params.get("chat_id")
    raw_path = request.query_params.get("path", "").strip()

    if not chat_id:
        return JSONResponse({"error": "chat_id is required"}, status_code=400)
    if not raw_path:
        return JSONResponse({"error": "path is required"}, status_code=400)

    volumes_json = request.query_params.get("volumes")
    override_volumes = None
    if volumes_json:
        try:
            override_volumes = json.loads(volumes_json)
        except Exception:
            pass

    try:
        resolver = _get_resolver_for_request(chat_id, override_volumes=override_volumes)
        target_host_path = resolver.resolve(raw_path)

        if not target_host_path.exists():
            return JSONResponse({"error": "File not found"}, status_code=404)

        if target_host_path.is_dir():
            # Only allow deleting empty directories for now, or use shutil.rmtree for recursive
            # Let's use rmtree for convenience but be careful

            shutil.rmtree(target_host_path)
            return JSONResponse({"path": raw_path, "status": "directory deleted"})
        else:
            target_host_path.unlink()
            return JSONResponse({"path": raw_path, "status": "file deleted"})

    except ValueError as ve:
        return JSONResponse({"error": str(ve)}, status_code=403)
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def serve_sandbox_file(request: Request):
    """Serve a file raw from sandbox (for browser rendering of html, pdf, etc)."""

    chat_id = request.query_params.get("chat_id")
    raw_path = request.query_params.get("path", "").strip()

    if not chat_id:
        return JSONResponse({"error": "chat_id is required"}, status_code=400)
    if not raw_path:
        return JSONResponse({"error": "path is required"}, status_code=400)

    volumes_json = request.query_params.get("volumes")
    override_volumes = None
    if volumes_json:
        try:
            override_volumes = json.loads(volumes_json)
        except Exception:
            pass

    try:
        resolver = _get_resolver_for_request(chat_id, override_volumes=override_volumes)
        target_host_path = resolver.resolve(raw_path)

        if not target_host_path.exists():
            return JSONResponse({"error": "File not found"}, status_code=404)

        if not target_host_path.is_file():
            return JSONResponse({"error": "Not a file"}, status_code=400)

        return FileResponse(target_host_path)

    except ValueError as ve:
        return JSONResponse({"error": str(ve)}, status_code=403)
    except Exception as e:
        logger.error(f"Error serving file: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def serve_sandbox_file_wildcard(request: Request):
    """
    Serve a file from sandbox using path parameters.
    Route: /sandbox/serve/{chat_id}/{file_path:path}
    This allows relative links (e.g. <img src="image.png">) in HTML files to work correctly.
    """

    chat_id = request.path_params.get("chat_id")
    # 'file_path' captures the rest of the URL, including slashes
    raw_path = request.path_params.get("file_path", "").strip()

    if not chat_id:
        return JSONResponse({"error": "chat_id is required"}, status_code=400)
    if not raw_path:
        return JSONResponse({"error": "path is required"}, status_code=400)

    # volumes from query param (even for wildcard route)
    volumes_json = request.query_params.get("volumes")
    override_volumes = None
    if volumes_json:
        try:
            override_volumes = json.loads(volumes_json)
        except Exception:
            pass

    try:
        resolver = _get_resolver_for_request(chat_id, override_volumes=override_volumes)

        # FIX: Ensure path is treated as absolute virtual path (relative to sandbox root)
        # The frontend strips the leading slash to avoid double-slashes in the URL,
        # but the resolver needs it to differentiate "/persistence" (virtual root) from "persistence" (folder in session).
        if not raw_path.startswith("/"):
            raw_path = "/" + raw_path

        target_host_path = resolver.resolve(raw_path)

        if not target_host_path.exists():
            return JSONResponse(
                {"error": f"File not found: {raw_path}"}, status_code=404
            )

        if not target_host_path.is_file():
            return JSONResponse({"error": "Not a file"}, status_code=400)

        return FileResponse(target_host_path)

    except ValueError as ve:
        return JSONResponse({"error": str(ve)}, status_code=403)
    except Exception as e:
        logger.error(f"Error serving file wildcard: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def upload_files(request: Request) -> JSONResponse:
    """
    Upload files to sandbox /persistence/uploads/ directory.
    Route: POST /api/sandbox/upload?chat_id={chat_id}

    Accepts multipart form-data with 'files' field (multiple files).
    Returns array of file metadata for frontend to include in messages.
    """

    chat_id = request.query_params.get("chat_id")

    if not chat_id:
        return JSONResponse({"error": "chat_id is required"}, status_code=400)

    try:
        # Parse multipart form data
        form = await request.form()
        uploaded_files = form.getlist("files")

        if not uploaded_files:
            return JSONResponse({"error": "No files provided"}, status_code=400)

        # Create resolver for this chat session
        resolver = _get_resolver_for_request(chat_id)

        # Resolve /persistence/uploads/ to host path
        uploads_virtual_path = "/persistence/uploads"
        uploads_host_path = resolver.resolve(uploads_virtual_path)

        # Create uploads directory if it doesn't exist
        uploads_host_path.mkdir(parents=True, exist_ok=True)

        result_files = []

        for upload_file in uploaded_files:
            if not upload_file.filename:
                continue

            # Comprehensive filename sanitization
            safe_filename = sanitize_filename(upload_file.filename)

            # Handle filename conflicts by appending timestamp
            target_path = uploads_host_path / safe_filename
            if target_path.exists():
                # Append timestamp before extension
                stem = target_path.stem
                suffix = target_path.suffix
                timestamp = int(time.time() * 1000)  # milliseconds
                safe_filename = f"{stem}_{timestamp}{suffix}"
                target_path = uploads_host_path / safe_filename

            # Write file to disk
            content = await upload_file.read()
            target_path.write_bytes(content)

            # Get file metadata
            stat = target_path.stat()
            mime_type = (
                mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
            )

            # Virtual path for agent to use
            virtual_path = f"{uploads_virtual_path}/{safe_filename}"

            # Build metadata for frontend

            file_metadata = {
                "id": str(uuid.uuid4()),
                "filename": safe_filename,
                "path": virtual_path,
                "size": stat.st_size,
                "mime_type": mime_type,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }

            result_files.append(file_metadata)
            logger.info(
                f"Uploaded file: {safe_filename} ({stat.st_size} bytes) to {virtual_path}"
            )

        return JSONResponse({"files": result_files})

    except Exception as e:
        logger.error(f"Error uploading files: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
