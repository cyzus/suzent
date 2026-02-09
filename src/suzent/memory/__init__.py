"""
Memory system for Suzent - provides long-term memory with automatic extraction.

Three storage layers:
- Markdown files (/shared/memory/): Human-readable source of truth
- LanceDB: Vector search index over memory content
- Core memory blocks: Always-visible working memory injected into agent context
"""

from .manager import MemoryManager
from .lancedb_store import LanceDBMemoryStore
from .markdown_store import MarkdownMemoryStore
from .indexer import MarkdownIndexer, TranscriptIndexer
from .tools import MemorySearchTool, MemoryBlockUpdateTool
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
    "LanceDBMemoryStore",
    "MarkdownMemoryStore",
    "MarkdownIndexer",
    "TranscriptIndexer",
    "MemorySearchTool",
    "MemoryBlockUpdateTool",
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
