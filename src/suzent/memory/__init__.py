"""
Memory system for Suzent - file-centric eventual consistency architecture.

Storage layers:
- Markdown files: shared persona/user/MEMORY.md, project-scoped context.md,
  and append-only archive logs
- LanceDB: Vector search index built asynchronously from markdown files
- Context injection: static (core files) + dynamic RAG (relevant memories)
"""

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
