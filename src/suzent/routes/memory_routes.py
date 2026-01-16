"""
Memory-related API routes.

This module handles all memory endpoints including:
- Getting and updating core memory blocks
- Searching and managing archival memories
- Memory statistics and analytics
"""

import json
from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.logger import get_logger
from suzent.config import CONFIG
from suzent.agent_manager import get_memory_manager

logger = get_logger(__name__)


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
        user_id = request.query_params.get('user_id', CONFIG.user_id)
        chat_id = request.query_params.get('chat_id')

        manager = get_memory_manager()
        if not manager:
            return JSONResponse(
                {'error': 'Memory system not initialized'},
                status_code=503
            )

        blocks = await manager.get_core_memory(
            user_id=user_id,
            chat_id=chat_id
        )

        return JSONResponse({'blocks': blocks})

    except Exception as e:
        logger.error(f"Error getting core memory: {e}")
        return JSONResponse(
            {'error': str(e)},
            status_code=500
        )


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
        label = data.get('label')
        content = data.get('content')
        user_id = data.get('user_id', CONFIG.user_id)
        chat_id = data.get('chat_id')

        if not label:
            return JSONResponse(
                {'error': 'Missing required field: label'},
                status_code=400
            )

        if content is None:
            return JSONResponse(
                {'error': 'Missing required field: content'},
                status_code=400
            )

        # Validate label
        valid_labels = ['persona', 'user', 'facts', 'context']
        if label not in valid_labels:
            return JSONResponse(
                {'error': f'Invalid label. Must be one of: {", ".join(valid_labels)}'},
                status_code=400
            )

        manager = get_memory_manager()
        if not manager:
            return JSONResponse(
                {'error': 'Memory system not initialized'},
                status_code=503
            )

        success = await manager.update_memory_block(
            label=label,
            content=content,
            user_id=user_id,
            chat_id=chat_id
        )

        if success:
            return JSONResponse({'success': True})
        else:
            return JSONResponse(
                {'error': 'Failed to update memory block'},
                status_code=500
            )

    except json.JSONDecodeError:
        return JSONResponse(
            {'error': 'Invalid JSON in request body'},
            status_code=400
        )
    except Exception as e:
        logger.error(f"Error updating core memory block: {e}")
        return JSONResponse(
            {'error': str(e)},
            status_code=500
        )


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
        query = request.query_params.get('query', '')
        user_id = request.query_params.get('user_id', CONFIG.user_id)
        # chat_id = request.query_params.get('chat_id')
        limit = min(int(request.query_params.get('limit', '20')), 100)
        offset = int(request.query_params.get('offset', '0'))

        manager = get_memory_manager()
        if not manager:
            return JSONResponse(
                {'error': 'Memory system not initialized'},
                status_code=503
            )

        if query:
            # Semantic search
            memories = await manager.search_memories(
                query=query,
                user_id=user_id,
                chat_id=None,  # Always search user-level
                limit=limit
            )
        else:
            # List all memories (no search)
            memories = await manager.store.list_memories(
                user_id=user_id,
                chat_id=None,
                limit=limit,
                offset=offset
            )

        # Format memories for frontend
        formatted_memories = []
        for mem in memories:
            # Convert UUID to string
            mem_id = mem.get('id')
            if mem_id is not None:
                mem_id = str(mem_id)

            formatted_memories.append({
                'id': mem_id,
                'content': mem.get('content'),
                'created_at': mem.get('created_at').isoformat() if mem.get('created_at') else None,
                'importance': float(mem.get('importance', 0.5)),
                'access_count': int(mem.get('access_count', 0)),
                'metadata': mem.get('metadata', {}) if isinstance(mem.get('metadata'), dict) else {},
                'similarity': float(mem.get('similarity', mem.get('semantic_score', 0)))
            })

        return JSONResponse({
            'memories': formatted_memories,
            'count': len(formatted_memories),
            'offset': offset,
            'limit': limit
        })

    except ValueError as e:
        return JSONResponse(
            {'error': f'Invalid parameter: {e}'},
            status_code=400
        )
    except Exception as e:
        logger.error(f"Error searching archival memory: {e}")
        return JSONResponse(
            {'error': str(e)},
            status_code=500
        )


async def delete_archival_memory(request: Request) -> JSONResponse:
    """
    Delete a specific archival memory by ID.

    Path param:
        - memory_id: Memory identifier

    Returns:
        JSONResponse with success status
    """
    try:
        memory_id = request.path_params.get('memory_id')

        if not memory_id:
            return JSONResponse(
                {'error': 'Missing memory_id'},
                status_code=400
            )

        manager = get_memory_manager()
        if not manager:
            return JSONResponse(
                {'error': 'Memory system not initialized'},
                status_code=503
            )

        # Delete from store
        await manager.store.delete_memory(memory_id)

        return JSONResponse({'success': True})

    except Exception as e:
        logger.error(f"Error deleting archival memory: {e}")
        return JSONResponse(
            {'error': str(e)},
            status_code=500
        )


async def get_memory_stats(request: Request) -> JSONResponse:
    """
    Get memory statistics for a user.

    Query params:
        - user_id: User identifier (defaults to CONFIG.user_id)

    Returns:
        JSONResponse with statistics
    """
    try:
        user_id = request.query_params.get('user_id', CONFIG.user_id)

        manager = get_memory_manager()
        if not manager:
            return JSONResponse(
                {'error': 'Memory system not initialized'},
                status_code=503
            )

        # Get stats from store
        stats = await manager.store.get_memory_stats(user_id=user_id)

        return JSONResponse(stats)

    except Exception as e:
        logger.error(f"Error getting memory stats: {e}")
        return JSONResponse(
            {'error': str(e)},
            status_code=500
        )
