"""
Memory system for Suzent - file-centric eventual consistency architecture.

Storage layers:
- Markdown files (/shared/memory/): Single Source of Truth — persona.md, user.md,
  MEMORY.md, sessions/{chat_id}/context.md, YYYY-MM-DD.md daily logs
- LanceDB: Vector search index built asynchronously from markdown files
- Context injection: static (core files) + dynamic RAG (relevant memories)
"""

from .manager import MemoryManager
from .wiki_manager import WikiManager
from .lancedb_store import LanceDBMemoryStore
from .markdown_store import MarkdownMemoryStore
from .indexer import MarkdownIndexer, TranscriptIndexer
from suzent.tools.memory_tools import MemorySearchTool
from . import memory_context
from .models import (
    Message,
    AgentAction,
    AgentStepsSummary,
    ConversationTurn,
    ConversationContext,
    ExtractedFact,
    MemoryExtractionResult,
    FactExtractionResponse,
)
from .lifecycle import (
    init_memory_system,
    shutdown_memory_system,
    get_memory_manager,
    get_main_event_loop,
    create_memory_tools,
)

__all__ = [
    "MemoryManager",
    "WikiManager",
    "LanceDBMemoryStore",
    "MarkdownMemoryStore",
    "MarkdownIndexer",
    "TranscriptIndexer",
    "MemorySearchTool",
    "memory_context",
    # Lifecycle management
    "init_memory_system",
    "shutdown_memory_system",
    "get_memory_manager",
    "get_main_event_loop",
    "create_memory_tools",
    # Pydantic models
    "Message",
    "AgentAction",
    "AgentStepsSummary",
    "ConversationTurn",
    "ConversationContext",
    "ExtractedFact",
    "MemoryExtractionResult",
    "FactExtractionResponse",
]
