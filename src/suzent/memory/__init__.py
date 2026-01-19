"""
Memory system for Suzent - provides long-term memory with automatic extraction.
"""

from .manager import MemoryManager
from .lancedb_store import LanceDBMemoryStore
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

__all__ = [
    "MemoryManager",
    "LanceDBMemoryStore",
    "MemorySearchTool",
    "MemoryBlockUpdateTool",
    "memory_context",
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
