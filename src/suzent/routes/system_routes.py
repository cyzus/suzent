"""
System-related API routes for host interaction.
"""

import os
import sys
import subprocess
import platform
import tomllib
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.logger import get_logger
from suzent.tools.filesystem.path_resolver import PathResolver
from suzent.database import get_database
from suzent.config import get_effective_volumes

logger = get_logger(__name__)

API_VERSION = 1


def _get_source_version(start: Path | None = None) -> str | None:
    """Find the nearest Suzent pyproject version for a source checkout."""

    source_file = (start or Path(__file__)).resolve()
    for parent in source_file.parents:
        pyproject = parent / "pyproject.toml"
        if not pyproject.is_file():
            continue
        try:
            project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get(
                "project", {}
            )
        except (OSError, tomllib.TOMLDecodeError):
            continue
        if project.get("name") == "suzent" and isinstance(project.get("version"), str):
            return project["version"]
    return None


def get_backend_version() -> str:
    """Return the running backend package version."""

    source_version = _get_source_version()
    if source_version:
        return source_version
    try:
        return package_version("suzent")
    except PackageNotFoundError:
        return "unknown"


def _git_directory(marker: Path) -> Path | None:
    if marker.is_dir():
        return marker
    try:
        prefix, value = marker.read_text(encoding="utf-8").strip().split(":", 1)
    except (OSError, ValueError):
        return None
    if prefix.lower() != "gitdir":
        return None
    path = Path(value.strip())
    return path if path.is_absolute() else (marker.parent / path).resolve()


def _common_git_directory(git_dir: Path) -> Path:
    try:
        value = (git_dir / "commondir").read_text(encoding="utf-8").strip()
    except OSError:
        return git_dir
    path = Path(value)
    return path if path.is_absolute() else (git_dir / path).resolve()


def _valid_commit(value: str) -> str | None:
    commit = value.strip().lower()
    if len(commit) in (40, 64) and all(char in "0123456789abcdef" for char in commit):
        return commit
    return None


def _read_git_ref(git_dir: Path, ref: str) -> str | None:
    common_dir = _common_git_directory(git_dir)
    for root in (git_dir, common_dir):
        try:
            commit = _valid_commit((root / ref).read_text(encoding="utf-8"))
        except OSError:
            continue
        if commit:
            return commit

    try:
        packed_refs = (common_dir / "packed-refs").read_text(encoding="utf-8")
    except OSError:
        return None
    for line in packed_refs.splitlines():
        if not line or line.startswith(("#", "^")):
            continue
        try:
            commit, packed_ref = line.split(" ", 1)
        except ValueError:
            continue
        if packed_ref.strip() == ref:
            return _valid_commit(commit)
    return None


@lru_cache(maxsize=8)
def _read_source_commit(source_file: Path) -> str:
    for parent in source_file.resolve().parents:
        marker = parent / ".git"
        if not marker.exists():
            continue
        git_dir = _git_directory(marker)
        if git_dir is None:
            return "unknown"
        try:
            head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        except OSError:
            return "unknown"
        if direct_commit := _valid_commit(head):
            return direct_commit
        if not head.startswith("ref:"):
            return "unknown"
        return _read_git_ref(git_dir, head.removeprefix("ref:").strip()) or "unknown"
    return "unknown"


def get_backend_commit(start: Path | None = None) -> str:
    """Return the backend commit without spawning a process in the request path."""

    configured = os.getenv("SUZENT_BUILD_COMMIT", "").strip()
    if configured:
        return configured
    return _read_source_commit(start or Path(__file__))


def get_system_identity() -> dict[str, str | int | bool]:
    return {
        "backend_version": get_backend_version(),
        "api_version": API_VERSION,
        "build_commit": get_backend_commit(),
        "development_mode": os.getenv("SUZENT_DEV_MODE") == "1",
    }


async def get_system_version(_request: Request) -> JSONResponse:
    """Return version information for the running backend."""

    return JSONResponse(get_system_identity())


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
