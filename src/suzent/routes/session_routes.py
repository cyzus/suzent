"""
Session & memory inspection API routes (Phase 5).

Endpoints for accessing transcripts, agent state snapshots, and daily memory logs.
These provide visibility into the unified memory-session architecture.
"""

from datetime import datetime
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.config import CONFIG
from suzent.logger import get_logger
from suzent.session.transcript import TranscriptManager
from suzent.session.state_mirror import StateMirror

logger = get_logger(__name__)

# Shared instances (lazily created)
_transcript_mgr: TranscriptManager = None
_state_mirror: StateMirror = None


def _get_transcript_mgr() -> TranscriptManager:
    global _transcript_mgr
    if _transcript_mgr is None:
        _transcript_mgr = TranscriptManager()
    return _transcript_mgr


def _get_state_mirror() -> StateMirror:
    global _state_mirror
    if _state_mirror is None:
        _state_mirror = StateMirror()
    return _state_mirror


async def get_session_transcript(request: Request) -> JSONResponse:
    """
    Get JSONL transcript content for a session.

    Path params:
        - session_id: Chat/session ID

    Query params:
        - last_n: Return only last N entries (optional)

    Returns:
        JSONResponse with transcript entries
    """
    try:
        session_id = request.path_params.get("session_id")
        if not session_id:
            return JSONResponse({"error": "Missing session_id"}, status_code=400)

        last_n_str = request.query_params.get("last_n")
        last_n = int(last_n_str) if last_n_str else None

        mgr = _get_transcript_mgr()

        if not mgr.transcript_exists(session_id):
            return JSONResponse(
                {"error": f"No transcript found for session {session_id}"},
                status_code=404,
            )

        entries = await mgr.read_transcript(session_id, last_n=last_n)

        return JSONResponse(
            {
                "session_id": session_id,
                "entries": entries,
                "count": len(entries),
            }
        )

    except ValueError as e:
        return JSONResponse({"error": f"Invalid parameter: {e}"}, status_code=400)
    except Exception as e:
        logger.error(f"Error reading transcript for session: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_session_state(request: Request) -> JSONResponse:
    """
    Get mirrored agent state JSON for a session.

    Path params:
        - session_id: Chat/session ID

    Returns:
        JSONResponse with agent state snapshot
    """
    try:
        session_id = request.path_params.get("session_id")
        if not session_id:
            return JSONResponse({"error": "Missing session_id"}, status_code=400)

        mirror = _get_state_mirror()
        state = mirror.read_state(session_id)

        if state is None:
            return JSONResponse(
                {"error": f"No state snapshot found for session {session_id}"},
                status_code=404,
            )

        return JSONResponse(
            {
                "session_id": session_id,
                "state": state,
            }
        )

    except Exception as e:
        logger.error(f"Error reading state for session: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_memory_daily_log(request: Request) -> JSONResponse:
    """
    Get a daily memory log by date.

    Path params:
        - date: Date string in YYYY-MM-DD format

    Returns:
        JSONResponse with the daily log content and metadata
    """
    try:
        date_str = request.path_params.get("date")
        if not date_str:
            return JSONResponse({"error": "Missing date parameter"}, status_code=400)

        # Validate date format
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return JSONResponse(
                {"error": "Invalid date format. Use YYYY-MM-DD."},
                status_code=400,
            )

        # Read from shared memory directory
        shared_memory_dir = Path(CONFIG.sandbox_data_path) / "shared" / "memory"
        log_path = shared_memory_dir / f"{date_str}.md"

        if not log_path.exists():
            return JSONResponse(
                {"error": f"No daily log found for {date_str}"},
                status_code=404,
            )

        content = log_path.read_text(encoding="utf-8")

        return JSONResponse(
            {
                "date": date_str,
                "content": content,
                "size_bytes": len(content.encode("utf-8")),
            }
        )

    except Exception as e:
        logger.error(f"Error reading daily memory log: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def list_memory_daily_logs(request: Request) -> JSONResponse:
    """
    List all available daily memory log dates.

    Returns:
        JSONResponse with list of dates that have daily logs
    """
    try:
        shared_memory_dir = Path(CONFIG.sandbox_data_path) / "shared" / "memory"

        if not shared_memory_dir.exists():
            return JSONResponse({"dates": [], "count": 0})

        dates = sorted(
            [p.stem for p in shared_memory_dir.glob("????-??-??.md") if p.is_file()],
            reverse=True,
        )

        return JSONResponse(
            {
                "dates": dates,
                "count": len(dates),
            }
        )

    except Exception as e:
        logger.error(f"Error listing daily logs: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_memory_file(request: Request) -> JSONResponse:
    """
    Get the curated MEMORY.md content.

    Returns:
        JSONResponse with MEMORY.md content
    """
    try:
        shared_memory_dir = Path(CONFIG.sandbox_data_path) / "shared" / "memory"
        memory_path = shared_memory_dir / "MEMORY.md"

        if not memory_path.exists():
            return JSONResponse({"error": "MEMORY.md not found"}, status_code=404)

        content = memory_path.read_text(encoding="utf-8")

        return JSONResponse(
            {
                "content": content,
                "size_bytes": len(content.encode("utf-8")),
            }
        )

    except Exception as e:
        logger.error(f"Error reading MEMORY.md: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def reindex_memories(request: Request) -> JSONResponse:
    """
    Trigger a re-index of markdown memories into LanceDB.

    Body (optional):
        - clear_existing: bool - Whether to clear existing memories first (default: false)

    Returns:
        JSONResponse with reindex statistics
    """
    try:
        from suzent.memory.lifecycle import get_memory_manager
        from suzent.memory import MarkdownIndexer

        manager = get_memory_manager()
        if not manager:
            return JSONResponse(
                {"error": "Memory system not initialized"}, status_code=503
            )

        body = {}
        try:
            body = await request.json()
        except Exception:
            pass  # No body is fine

        clear_existing = body.get("clear_existing", False)

        indexer = MarkdownIndexer()
        stats = await indexer.reindex_from_markdown(
            markdown_store=manager.markdown_store,
            lancedb_store=manager.store,
            embedding_gen=manager.embedding_gen,
            user_id=CONFIG.user_id,
            clear_existing=clear_existing,
        )

        return JSONResponse(
            {
                "success": True,
                "stats": stats,
            }
        )

    except Exception as e:
        logger.error(f"Error during memory reindex: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
