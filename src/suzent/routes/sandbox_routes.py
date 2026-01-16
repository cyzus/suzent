"""
Sandbox-related API routes.
"""

from starlette.requests import Request
from starlette.responses import JSONResponse

from pathlib import Path
from suzent.sandbox import SandboxManager
from suzent.logger import get_logger

logger = get_logger(__name__)


def _resolve_host_path(
    chat_id: str, virtual_path: str
) -> tuple[Path | None, dict | None]:
    """
    Resolve a virtual sandbox path to a host filesystem path.
    Returns: (resolved_host_path, mounts_map) or (None, None) if invalid/error.
    """
    try:
        # Instantiate manager to get config/paths resolved
        manager = SandboxManager()
        session = manager.get_session(chat_id)

        # Build Mount Map: Key=VirtualPath, Value=HostPath
        mounts = {}

        # 1. Standard Mounts
        mounts["/persistence"] = session.session_dir.resolve()
        mounts["/shared"] = (Path(manager.data_path) / "shared").resolve()

        # Ensure standard roots exist
        mounts["/persistence"].mkdir(parents=True, exist_ok=True)
        mounts["/shared"].mkdir(parents=True, exist_ok=True)

        # 2. Custom Mounts using SandboxManager logic
        for vol in manager.custom_volumes:
            host_part = None
            container_part = None

            if ":" in vol:
                last_colon = vol.rfind(":")
                if last_colon != -1:
                    host_part = vol[:last_colon]
                    container_part = vol[last_colon + 1 :]

            if host_part and container_part:
                if host_part.startswith("/mnt/"):
                    import re

                    match = re.match(r"^/mnt/([a-zA-Z])/(.*)", host_part)
                    if match:
                        drive = match.group(1).upper()
                        rest = match.group(2)
                        host_part = f"{drive}:/{rest}"

                host_path = Path(host_part).resolve()

                container_path = container_part.strip().replace("\\", "/")
                if not container_path.startswith("/"):
                    container_path = "/" + container_path

                mounts[container_path] = host_path

        # Resolve Path
        request_path = virtual_path.replace("\\", "/")
        if not request_path.startswith("/"):
            request_path = "/" + request_path
        if request_path != "/" and request_path.endswith("/"):
            request_path = request_path[:-1]

        matched_mount_point = None
        matched_mount_len = 0

        for v_path in mounts.keys():
            if request_path == v_path or request_path.startswith(v_path + "/"):
                if len(v_path) > matched_mount_len:
                    matched_mount_point = v_path
                    matched_mount_len = len(v_path)

        return request_path, mounts, matched_mount_point

    except Exception as e:
        logger.error(f"Error resolving path: {e}")
        return None, None, None


async def list_sandbox_files(request: Request) -> JSONResponse:
    """List files in sandbox directory."""
    chat_id = request.query_params.get("chat_id")
    raw_path = request.query_params.get("path", "/").strip()

    if not chat_id:
        return JSONResponse({"error": "chat_id is required"}, status_code=400)

    try:
        request_path, mounts, matched_mount_point = _resolve_host_path(
            chat_id, raw_path
        )

        if request_path is None:
            return JSONResponse({"error": "Failed to resolve path"}, status_code=500)

        items = []
        virtual_children = set()

        # 1. Virtual directory listing logic (parents of mounts)
        for v_path in mounts.keys():
            parent_check_path = (
                request_path if request_path == "/" else request_path + "/"
            )
            if v_path.startswith(parent_check_path):
                suffix = v_path[len(parent_check_path) :]
                child = suffix.split("/")[0]
                if child:
                    virtual_children.add(child)

        for child in virtual_children:
            items.append({"name": child, "is_dir": True, "size": 0, "mtime": 0})

        # 2. Actual file listing
        if matched_mount_point:
            host_root = mounts[matched_mount_point]
            if request_path == matched_mount_point:
                target_host_path = host_root
            else:
                rel_path = request_path[len(matched_mount_point) :].lstrip("/")
                target_host_path = (host_root / rel_path).resolve()

            # Security Check
            try:
                target_host_path.relative_to(host_root)
            except ValueError:
                return JSONResponse(
                    {"error": "Access denied: Path traversal detected"}, status_code=403
                )

            if target_host_path.exists() and target_host_path.is_dir():
                for entry in target_host_path.iterdir():
                    try:
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

        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return JSONResponse({"path": request_path, "items": items})

    except Exception as e:
        logger.error(f"Error listing files: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def read_sandbox_file(request: Request) -> JSONResponse:
    """Read file content from sandbox."""
    chat_id = request.query_params.get("chat_id")
    raw_path = request.query_params.get("path", "").strip()

    if not chat_id:
        return JSONResponse({"error": "chat_id is required"}, status_code=400)
    if not raw_path:
        return JSONResponse({"error": "path is required"}, status_code=400)

    try:
        request_path, mounts, matched_mount_point = _resolve_host_path(
            chat_id, raw_path
        )

        if not matched_mount_point:
            return JSONResponse(
                {"error": "File not found (not in any mount)"}, status_code=404
            )

        host_root = mounts[matched_mount_point]
        rel_path = request_path[len(matched_mount_point) :].lstrip("/")
        target_host_path = (host_root / rel_path).resolve()

        # Security Check
        try:
            target_host_path.relative_to(host_root)
        except ValueError:
            return JSONResponse({"error": "Access denied"}, status_code=403)

        if not target_host_path.exists():
            return JSONResponse({"error": "File not found"}, status_code=404)

        if not target_host_path.is_file():
            return JSONResponse({"error": "Not a file"}, status_code=400)

        # Read content (text only for now)
        try:
            content = target_host_path.read_text(encoding="utf-8")
            return JSONResponse({"path": request_path, "content": content})
        except UnicodeDecodeError:
            return JSONResponse(
                {"error": "Binary file not supported for preview"}, status_code=400
            )
        except Exception as e:
            return JSONResponse({"error": f"Failed to read file: {e}"}, status_code=500)

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

        request_path, mounts, matched_mount_point = _resolve_host_path(
            chat_id, raw_path
        )

        if not matched_mount_point:
            return JSONResponse(
                {"error": "Invalid path (not in any mount)"}, status_code=400
            )

        host_root = mounts[matched_mount_point]
        rel_path = request_path[len(matched_mount_point) :].lstrip("/")
        target_host_path = (host_root / rel_path).resolve()

        # Security Check
        try:
            target_host_path.relative_to(host_root)
        except ValueError:
            return JSONResponse(
                {"error": "Access denied: Path traversal detected"}, status_code=403
            )

        # Ensure parent directory exists
        target_host_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        target_host_path.write_text(content, encoding="utf-8")

        size = len(content)
        return JSONResponse({"path": request_path, "size": size, "status": "written"})

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

    try:
        request_path, mounts, matched_mount_point = _resolve_host_path(
            chat_id, raw_path
        )

        if not matched_mount_point:
            return JSONResponse(
                {"error": "File not found (not in any mount)"}, status_code=404
            )

        host_root = mounts[matched_mount_point]
        rel_path = request_path[len(matched_mount_point) :].lstrip("/")
        target_host_path = (host_root / rel_path).resolve()

        # Security Check
        try:
            target_host_path.relative_to(host_root)
        except ValueError:
            return JSONResponse({"error": "Access denied"}, status_code=403)

        if not target_host_path.exists():
            return JSONResponse({"error": "File not found"}, status_code=404)

        if target_host_path.is_dir():
            # Only allow deleting empty directories for now, or use shutil.rmtree for recursive
            # Let's use rmtree for convenience but be careful
            import shutil

            shutil.rmtree(target_host_path)
            return JSONResponse({"path": request_path, "status": "directory deleted"})
        else:
            target_host_path.unlink()
            return JSONResponse({"path": request_path, "status": "file deleted"})

    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
