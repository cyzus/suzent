"""
Memory-related API routes.

This module handles all memory endpoints including:
- Getting and updating core memory blocks
- Searching and managing archival memories
- Memory statistics and analytics
"""

import json
from typing import Any, Optional
from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.logger import get_logger
from suzent.config import CONFIG
from suzent.database import get_database
from suzent.memory.lancedb_store import matches_metadata
from suzent.memory.lifecycle import get_memory_manager, init_memory_system

logger = get_logger(__name__)

# Columns the archival list may be ordered by, mirroring LanceDBStore.list_memories.
ARCHIVAL_ORDER_COLUMNS = {
    "created_at",
    "updated_at",
    "accessed_at",
    "importance",
    "access_count",
}
# How deep "load more" may page into a relevance-ranked search.
ARCHIVAL_SEARCH_MAX_DEPTH = 500


def _optional_float(raw: Optional[str]) -> Optional[float]:
    """Parse an optional float query param; blank and missing both mean None."""
    if raw is None or raw == "":
        return None
    return float(raw)


def _csv_list(raw: Optional[str]) -> Optional[list]:
    """Parse a comma-separated filter param. Blank, missing, and all-blank mean None
    (i.e. no filter) rather than "match nothing"."""
    if not raw:
        return None
    values = [v.strip() for v in raw.split(",") if v.strip()]
    return values or None


async def _get_or_initialize_memory_manager() -> Any:
    manager = get_memory_manager()
    if manager is None:
        await init_memory_system()
        manager = get_memory_manager()
    return manager


async def get_core_memory(request: Request) -> JSONResponse:
    """
    Get all core memory blocks for a user.

    Query params:
        - user_id: User identifier (defaults to CONFIG.user_id)
        - chat_id: Optional chat context

    Returns:
        JSONResponse with core memory blocks
    """
    try:
        user_id = request.query_params.get("user_id", CONFIG.user_id)
        chat_id = request.query_params.get("chat_id")

        manager = await _get_or_initialize_memory_manager()
        if not manager:
            return JSONResponse(
                {"error": "Memory system not initialized"}, status_code=503
            )

        blocks = await manager.get_core_memory(user_id=user_id, chat_id=chat_id)

        return JSONResponse({"blocks": blocks})

    except Exception as e:
        logger.error(f"Error getting core memory: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def update_core_memory_block(request: Request) -> JSONResponse:
    """
    Update a specific core memory block.

    Body:
        - label: Block label (persona, user, facts, context)
        - content: New content for the block
        - user_id: User identifier (defaults to CONFIG.user_id)
        - chat_id: Optional chat context

    Returns:
        JSONResponse with success status
    """
    try:
        data = await request.json()
        label = data.get("label")
        content = data.get("content")
        user_id = data.get("user_id", CONFIG.user_id)
        chat_id = data.get("chat_id")

        if not label:
            return JSONResponse(
                {"error": "Missing required field: label"}, status_code=400
            )

        if content is None:
            return JSONResponse(
                {"error": "Missing required field: content"}, status_code=400
            )

        # Validate label — core blocks only (context is session-scoped; updating
        # it without a chat_id is a no-op handled gracefully by the manager)
        valid_labels = ["persona", "user", "facts", "context"]
        if label not in valid_labels:
            return JSONResponse(
                {"error": f"Invalid label. Must be one of: {', '.join(valid_labels)}"},
                status_code=400,
            )

        manager = await _get_or_initialize_memory_manager()
        if not manager:
            return JSONResponse(
                {"error": "Memory system not initialized"}, status_code=503
            )

        success = await manager.update_memory_block(
            label=label, content=content, user_id=user_id, chat_id=chat_id
        )

        if success:
            return JSONResponse({"success": True})
        else:
            return JSONResponse(
                {"error": "Failed to update memory block"}, status_code=500
            )

    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON in request body"}, status_code=400)
    except Exception as e:
        logger.error(f"Error updating core memory block: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def list_project_contexts(request: Request) -> JSONResponse:
    """List context.md content for every visible Suzent project."""
    try:
        include_archived = (
            request.query_params.get("include_archived", "").lower() == "true"
        )
        database = get_database()
        projects = database.list_projects(include_archived=include_archived)
        manager = await _get_or_initialize_memory_manager()
        if not manager:
            return JSONResponse(
                {"error": "Memory system not initialized"}, status_code=503
            )

        payload = []
        for project in projects:
            context = await manager.markdown_store.read_project_context(project.id)
            payload.append(
                {
                    "projectId": project.id,
                    "projectName": project.name,
                    "projectSlug": project.slug,
                    "archived": project.archived,
                    "chatCount": database.count_chats_in_project(project.id),
                    "content": context or "",
                    "exists": context is not None,
                }
            )
        return JSONResponse({"projects": payload})
    except Exception as e:
        logger.error(f"Error listing project contexts: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def update_project_context(request: Request) -> JSONResponse:
    """Update one project's context.md without requiring a chat."""
    try:
        project_id = str(request.path_params.get("project_id") or "").strip()
        if not project_id:
            return JSONResponse({"error": "Missing project_id"}, status_code=400)

        database = get_database()
        if database.get_project(project_id) is None:
            return JSONResponse({"error": "Project not found"}, status_code=404)

        data = await request.json()
        content = data.get("content")
        if not isinstance(content, str):
            return JSONResponse(
                {"error": "Missing required field: content"}, status_code=400
            )

        manager = await _get_or_initialize_memory_manager()
        if not manager:
            return JSONResponse(
                {"error": "Memory system not initialized"}, status_code=503
            )
        await manager.markdown_store.write_project_context(project_id, content)
        return JSONResponse({"success": True})
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON in request body"}, status_code=400)
    except Exception as e:
        logger.error(f"Error updating project context: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def search_archival_memory(request: Request) -> JSONResponse:
    """
    Search archival memories with semantic search.

    Query params:
        - query: Search query string
        - user_id: User identifier (defaults to CONFIG.user_id)
        - chat_id: Optional chat context
        - limit: Maximum results (default: 20, max: 100)
        - offset: Pagination offset (default: 0)

    Returns:
        JSONResponse with list of matching memories
    """
    try:
        query = request.query_params.get("query", "")
        user_id = request.query_params.get("user_id", CONFIG.user_id)
        # chat_id = request.query_params.get('chat_id')
        limit = min(int(request.query_params.get("limit", "20")), 100)
        offset = int(request.query_params.get("offset", "0"))
        order_by = request.query_params.get("order_by", "created_at")
        order_desc = request.query_params.get("order_desc", "true").lower() != "false"
        min_importance = _optional_float(request.query_params.get("min_importance"))
        max_importance = _optional_float(request.query_params.get("max_importance"))
        source_types = _csv_list(request.query_params.get("source_types"))
        categories = _csv_list(request.query_params.get("categories"))
        tags = _csv_list(request.query_params.get("tags"))
        want_facets = request.query_params.get("facets", "").lower() in ("1", "true")

        if order_by not in ARCHIVAL_ORDER_COLUMNS:
            return JSONResponse(
                {"error": f"Invalid order_by: {order_by}"}, status_code=400
            )

        manager = await _get_or_initialize_memory_manager()
        if not manager:
            return JSONResponse(
                {"error": "Memory system not initialized"}, status_code=503
            )

        total: Optional[int] = None

        if query:
            # Semantic search. The search path ranks by relevance and has no
            # native offset, so page by over-fetching and slicing — that keeps
            # "load more" from re-appending the same top hits.
            fetch_limit = min(offset + limit, ARCHIVAL_SEARCH_MAX_DEPTH)
            memories = await manager.search_memories(
                query=query,
                user_id=user_id,
                chat_id=None,  # Always search user-level
                limit=fetch_limit,
            )
            if min_importance is not None:
                memories = [
                    m
                    for m in memories
                    if float(m.get("importance", 0)) >= min_importance
                ]
            if max_importance is not None:
                memories = [
                    m
                    for m in memories
                    if float(m.get("importance", 0)) < max_importance
                ]
            if source_types or categories or tags:
                memories = [
                    m
                    for m in memories
                    if matches_metadata(
                        m.get("metadata")
                        if isinstance(m.get("metadata"), dict)
                        else {},
                        source_types,
                        categories,
                        tags,
                    )
                ]
            memories = memories[offset : offset + limit]
        else:
            # List all memories (no search). Ordering and the importance band are
            # applied across the whole set before pagination, so the first page is
            # the true first page and not just the first page re-sorted.
            memories = await manager.store.list_memories(
                user_id=user_id,
                chat_id=None,
                limit=limit,
                offset=offset,
                order_by=order_by,
                order_desc=order_desc,
                min_importance=min_importance,
                max_importance=max_importance,
                source_types=source_types,
                categories=categories,
                tags=tags,
            )
            total = await manager.store.get_memory_count(
                user_id=user_id,
                chat_id=None,
                min_importance=min_importance,
                max_importance=max_importance,
                source_types=source_types,
                categories=categories,
                tags=tags,
            )

        # Format memories for frontend
        formatted_memories = []
        for mem in memories:
            # Convert UUID to string
            mem_id = mem.get("id")
            if mem_id is not None:
                mem_id = str(mem_id)

            formatted_memories.append(
                {
                    "id": mem_id,
                    "content": mem.get("content"),
                    "created_at": mem.get("created_at").isoformat()
                    if mem.get("created_at")
                    else None,
                    "importance": float(mem.get("importance", 0.5)),
                    "access_count": int(mem.get("access_count", 0)),
                    "metadata": mem.get("metadata", {})
                    if isinstance(mem.get("metadata"), dict)
                    else {},
                    "similarity": float(
                        mem.get("similarity", mem.get("semantic_score", 0))
                    ),
                }
            )

        payload: dict[str, Any] = {
            "memories": formatted_memories,
            "count": len(formatted_memories),
            "offset": offset,
            "limit": limit,
        }
        # Only the list path knows the size of the matching set; a relevance
        # search has no meaningful total.
        if total is not None:
            payload["total"] = total

        # Facets are what the filter UI is drawn from, so they are only worth the
        # extra scan on the first page — later pages reuse what the client already has.
        if want_facets:
            payload["facets"] = await manager.store.get_memory_facets(
                user_id=user_id,
                chat_id=None,
                min_importance=min_importance,
                max_importance=max_importance,
            )

        return JSONResponse(payload)

    except ValueError as e:
        return JSONResponse({"error": f"Invalid parameter: {e}"}, status_code=400)
    except Exception as e:
        logger.error(f"Error searching archival memory: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def delete_archival_memory(request: Request) -> JSONResponse:
    """
    Delete a specific archival memory by ID.

    Path param:
        - memory_id: Memory identifier

    Returns:
        JSONResponse with success status
    """
    try:
        memory_id = request.path_params.get("memory_id")

        if not memory_id:
            return JSONResponse({"error": "Missing memory_id"}, status_code=400)

        manager = await _get_or_initialize_memory_manager()
        if not manager:
            return JSONResponse(
                {"error": "Memory system not initialized"}, status_code=503
            )

        # Files are the source of truth; LanceDB is derived. Deletion tombstones the
        # fact (so re-indexing can't resurrect it) and reindexes the source file —
        # we don't mutate LanceDB ad hoc (see the mutation invariant in the plan).
        mem = await manager.store.get_memory(memory_id)
        if not mem:
            return JSONResponse({"error": "Memory not found"}, status_code=404)

        md = getattr(manager, "markdown_store", None)
        content = mem.get("content", "")
        user_id = mem.get("user_id") or CONFIG.user_id
        meta = mem.get("metadata", {}) or {}
        source_type = meta.get("source_type")
        source_file = meta.get("source_file")

        if md and content:
            try:
                await md.append_tombstone(content)
            except Exception as e:
                logger.warning(f"Failed to tombstone deleted memory: {e}")

        if md and source_type == "archive_log" and source_file:
            # Diary fact: re-index the day's log; the tombstone makes the indexer skip it.
            await manager._core_indexer.reindex_file_now(
                markdown_store=md,
                lancedb_store=manager.store,
                embedding_gen=manager.embedding_gen,
                user_id=user_id,
                label="archive",
                filename=source_file,
            )
        else:
            # Notebook/core rows: drop the row now; the tombstone appended above makes
            # the indexer skip this chunk on any future rebuild (clear_and_full_reindex
            # included), so {"success": True} is durable — it can't resurrect. (If a later
            # dream *rewords* the fact into a new page paragraph, only the exact prior text
            # is tombstoned; that residue is reconciled by the next dream/lint pass.)
            await manager.store.delete_memory(memory_id)

        return JSONResponse({"success": True})

    except Exception as e:
        logger.error(f"Error deleting archival memory: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_memory_stats(request: Request) -> JSONResponse:
    """
    Get memory statistics for a user.

    Query params:
        - user_id: User identifier (defaults to CONFIG.user_id)

    Returns:
        JSONResponse with statistics
    """
    try:
        user_id = request.query_params.get("user_id", CONFIG.user_id)

        manager = await _get_or_initialize_memory_manager()
        if not manager:
            return JSONResponse(
                {"error": "Memory system not initialized"}, status_code=503
            )

        # Get stats from store
        stats = await manager.store.get_memory_stats(user_id=user_id)

        return JSONResponse(stats)

    except Exception as e:
        logger.error(f"Error getting memory stats: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def consolidate_memory(request: Request) -> JSONResponse:
    """Trigger an on-demand memory ingest consolidation run."""
    try:
        from suzent.core.dream_runner import get_active_dream_runner

        runner = get_active_dream_runner()
        if runner is None:
            return JSONResponse({"error": "Dream runner not active"}, status_code=503)

        result = runner.start_force_run()
        return JSONResponse({"success": True, "result": result})

    except Exception as e:
        logger.error(f"Error during memory consolidation: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def lint_memory(request: Request) -> JSONResponse:
    """Trigger an on-demand memory lint pass."""
    try:
        from suzent.core.dream_runner import get_active_dream_runner

        runner = get_active_dream_runner()
        if runner is None:
            return JSONResponse({"error": "Dream runner not active"}, status_code=503)

        result = runner.start_lint_run()
        return JSONResponse({"success": True, "result": result})

    except Exception as e:
        logger.error(f"Error during memory lint: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_dream_status(request: Request) -> JSONResponse:
    """Return the background memory consolidation status."""
    try:
        from suzent.core.dream_runner import get_active_dream_runner

        runner = get_active_dream_runner()
        if runner is None:
            return JSONResponse(
                {
                    "active": False,
                    "available": False,
                    "enabled": CONFIG.memory_consolidation_enabled,
                    "running": False,
                    "reason": "Dream runner not active",
                }
            )

        return JSONResponse(runner.status())

    except Exception as e:
        logger.error(f"Error getting dream status: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
