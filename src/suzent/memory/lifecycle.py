"""
Memory system lifecycle management.

This module handles the initialization, shutdown, and global state
for the memory system. The actual memory implementation (MemoryManager,
LanceDBMemoryStore, tools, models) lives in the other files in this package.
"""

import asyncio
from typing import Any

from suzent.config import CONFIG
from suzent.logger import get_logger

logger = get_logger(__name__)

# --- Memory System State ---
memory_manager = None
memory_store = None
main_event_loop = None  # Store reference to main event loop for async operations

# Background watcher task reference (kept alive)
_watcher_task = None


async def _migrate_blocks_to_files(memory_store, markdown_store, user_id: str) -> None:
    """One-time migration: export LanceDB memory_blocks to markdown files, and
    move any legacy daily-log files from the memory root into archive/.

    Runs at startup. Only writes/moves if the destination does not already
    exist, so re-running is always safe (no data loss, no overwrites).
    """
    import shutil

    migrated = []

    # ------------------------------------------------------------------
    # 1. LanceDB blocks → markdown files
    # ------------------------------------------------------------------
    labels = {"persona": "persona", "user": "user"}
    try:
        blocks = await memory_store.get_all_memory_blocks(user_id=user_id)

        for block_label, file_label in labels.items():
            path = markdown_store._block_path(file_label)
            if (
                not path.exists()
                and block_label in blocks
                and blocks[block_label].strip()
            ):
                await markdown_store.write_block(file_label, blocks[block_label])
                migrated.append(f"{block_label} → {file_label}.md")

        if (
            not markdown_store.memory_file_path.exists()
            and "facts" in blocks
            and blocks["facts"].strip()
        ):
            await markdown_store.write_block("MEMORY", blocks["facts"])
            migrated.append("facts → MEMORY.md")

    except Exception as e:
        logger.warning(f"Block migration skipped (non-fatal): {e}")

    # ------------------------------------------------------------------
    # 2. Legacy daily logs: move YYYY-MM-DD.md from root → archive/
    # ------------------------------------------------------------------
    import re as _re

    _date_re = _re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
    try:
        for old_path in list(markdown_store.base_dir.iterdir()):
            if old_path.is_file() and _date_re.match(old_path.name):
                new_path = markdown_store.archive_dir / old_path.name
                if not new_path.exists():
                    shutil.move(str(old_path), str(new_path))
                    migrated.append(f"{old_path.name} → archive/")
                else:
                    old_path.unlink()  # duplicate — drop it
    except Exception as e:
        logger.warning(f"Daily log migration skipped (non-fatal): {e}")

    if migrated:
        logger.info(f"Memory migration: {', '.join(migrated)}")


async def _memory_rag_hook(chat_id: str, deps: Any, user_message: str) -> str | None:
    """Per-turn system-reminder hook: retrieve archival memories relevant to the
    current user message and return them formatted as a ``<memory>`` block.

    Registered via ``register_per_turn_hook`` after the memory system starts.
    """
    import time

    mm = deps.memory_manager if deps else None
    if not mm:
        return None
    try:
        t0 = time.monotonic()
        result = await mm.retrieve_relevant_memories(
            query=user_message,
            chat_id=chat_id,
            user_id=getattr(deps, "user_id", None),
            use_embedding=False,
        )
        elapsed = time.monotonic() - t0
        logger.debug(
            f"[memory-rag-hook] chat={chat_id} elapsed={elapsed:.3f}s result={'yes' if result else 'empty'}"
        )
        return result
    except Exception as e:
        logger.debug(f"RAG hook failed: {e}")
        return None


async def _core_file_watch_loop(mgr, user_id: str, interval: int = 300) -> None:
    """Background loop: watch core memory files for changes and update LanceDB index.

    Polls every `interval` seconds. Uses mtime comparison so only changed files
    are re-embedded — unchanged files incur zero cost.
    """
    from suzent.memory.indexer import CoreMemoryFileIndexer

    indexer = CoreMemoryFileIndexer()
    logger.info(f"Core file watcher started (interval={interval}s)")

    # Initial indexing pass (catches files written before the loop starts)
    try:
        await indexer.check_and_update(
            markdown_store=mgr.markdown_store,
            lancedb_store=mgr.store,
            embedding_gen=mgr.embedding_gen,
            user_id=user_id,
        )
    except Exception as e:
        logger.warning(f"Initial core file index pass failed: {e}")

    while True:
        await asyncio.sleep(interval)
        try:
            if mgr.markdown_store and mgr.store:
                await indexer.check_and_update(
                    markdown_store=mgr.markdown_store,
                    lancedb_store=mgr.store,
                    embedding_gen=mgr.embedding_gen,
                    user_id=user_id,
                )
        except Exception as e:
            logger.error(f"Core file watcher error: {e}")


async def init_memory_system() -> bool:
    """
    Initialize the memory system if enabled in configuration.

    Returns:
        True if memory system initialized successfully, False otherwise.
    """
    global memory_manager, memory_store, main_event_loop, _watcher_task

    # Store reference to main event loop
    main_event_loop = asyncio.get_running_loop()

    if not CONFIG.memory_enabled:
        logger.info("Memory system disabled in configuration")
        return False

    try:
        # Import memory modules (local imports to avoid circular deps)
        from suzent.memory import MemoryManager, LanceDBMemoryStore
        from suzent.memory.markdown_store import MarkdownMemoryStore

        # Initialize LanceDB store (search index)
        memory_store = LanceDBMemoryStore(
            CONFIG.lancedb_uri, embedding_dim=CONFIG.embedding_dimension
        )
        await memory_store.connect()

        # Initialize markdown store (human-readable source of truth)
        # Lives in /shared/memory/ so the agent can directly read/write via file tools
        markdown_store = None
        if getattr(CONFIG, "markdown_memory_enabled", True):
            from pathlib import Path

            shared_memory_dir = Path(CONFIG.sandbox_data_path) / "shared" / "memory"
            markdown_store = MarkdownMemoryStore(str(shared_memory_dir))
            logger.info(f"Markdown memory store initialized at {shared_memory_dir}")

        # Initialize memory manager
        memory_manager = MemoryManager(
            store=memory_store,
            embedding_model=CONFIG.embedding_model,
            embedding_dimension=CONFIG.embedding_dimension,
            llm_for_extraction=CONFIG.extraction_model,
            markdown_store=markdown_store,
        )

        notebook_host_path = None
        from suzent.tools.filesystem.path_resolver import PathResolver

        for vol in CONFIG.sandbox_volumes or []:
            parsed = PathResolver.parse_volume_string(vol)
            if parsed and parsed[1] == "/mnt/notebook":
                notebook_host_path = parsed[0]
                break

        if notebook_host_path:
            from suzent.memory.wiki_manager import WikiManager
            from pathlib import Path

            resolved_notebook = str(Path(notebook_host_path).resolve())
            memory_manager.wiki_manager = WikiManager(notebook_path=resolved_notebook)
            logger.info(f"WikiManager initialized at {resolved_notebook}")

        logger.info(
            f"Memory system initialized successfully "
            f"(extraction: {'LLM' if CONFIG.extraction_model else 'heuristic'}, "
            f"markdown: {'enabled' if markdown_store else 'disabled'})"
        )

        # One-time migration: move any existing LanceDB blocks to markdown files
        if markdown_store:
            await _migrate_blocks_to_files(memory_store, markdown_store, CONFIG.user_id)

        # Add memory tools to CONFIG.tool_options so they appear in frontend
        if "MemorySearchTool" not in CONFIG.tool_options:
            CONFIG.tool_options.append("MemorySearchTool")
            logger.info("Added MemorySearchTool to config")

        # Start background core-file watcher (Phase 2)
        if markdown_store and CONFIG.embedding_model:
            _watcher_task = asyncio.create_task(
                _core_file_watch_loop(memory_manager, CONFIG.user_id),
                name="core_memory_file_watcher",
            )

        # Register dynamic RAG as a per-turn system-reminder hook (Phase 3)
        from suzent.core.system_reminder import register_per_turn_hook

        register_per_turn_hook(_memory_rag_hook)
        logger.info("Registered memory RAG as per-turn system reminder hook")

        return True

    except Exception as e:
        logger.error(f"Failed to initialize memory system: {e}")
        memory_manager = None
        memory_store = None
        return False


async def shutdown_memory_system():
    """Shutdown memory system and close connections."""
    global memory_store, _watcher_task

    if _watcher_task and not _watcher_task.done():
        _watcher_task.cancel()
        try:
            await _watcher_task
        except asyncio.CancelledError:
            pass

    if memory_store:
        try:
            await memory_store.close()
            logger.info("Memory system shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down memory system: {e}")


def get_memory_manager():
    """
    Get the global memory manager instance.

    Returns:
        MemoryManager instance or None if not initialized.
    """
    return memory_manager


def get_main_event_loop():
    """
    Get the main event loop reference.

    Returns:
        The main event loop or None if not initialized.
    """
    return main_event_loop


def create_memory_tools() -> list:
    """
    Create memory tool instances.

    Returns:
        List of memory tool instances, or empty list if memory not initialized.
    """
    if memory_manager is None:
        logger.warning("Memory system not initialized, skipping memory tools")
        return []

    try:
        from suzent.memory import MemorySearchTool

        search_tool = MemorySearchTool(memory_manager)
        search_tool._main_loop = main_event_loop

        logger.info("MemorySearchTool equipped")
        return [search_tool]

    except Exception as e:
        logger.error(f"Failed to create memory tools: {e}")
        return []
