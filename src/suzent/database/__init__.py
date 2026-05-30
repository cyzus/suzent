"""Database package public API."""

import os

from .facade import ChatDatabase
from .models import (
    ApiKeyModel,
    ChatCostSummaryModel,
    ChatModel,
    ChatSummaryModel,
    CostLedgerModel,
    CronJobModel,
    CronRunModel,
    MCPServerModel,
    MemoryConfigModel,
    PlanModel,
    PostprocessJobModel,
    PostProcessMetrics,
    PostProcessOutcome,
    PostProcessStatus,
    PostProcessStep,
    ProjectModel,
    RetryCheckpointModel,
    StepStatus,
    TaskModel,
    UserPreferencesModel,
    VolumeMetadataModel,
)

__all__ = [
    "ApiKeyModel",
    "ChatCostSummaryModel",
    "ChatDatabase",
    "ChatModel",
    "ChatSummaryModel",
    "CostLedgerModel",
    "CronJobModel",
    "CronRunModel",
    "MCPServerModel",
    "MemoryConfigModel",
    "PlanModel",
    "PostProcessMetrics",
    "PostProcessOutcome",
    "PostProcessStatus",
    "PostProcessStep",
    "PostprocessJobModel",
    "ProjectModel",
    "RetryCheckpointModel",
    "StepStatus",
    "TaskModel",
    "UserPreferencesModel",
    "VolumeMetadataModel",
    "generate_chat_title",
    "get_database",
]

_db_instance: ChatDatabase | None = None


def get_database() -> ChatDatabase:
    """Get the global database instance."""
    global _db_instance
    if _db_instance is None:
        db_path = os.getenv("CHATS_DB_PATH", None)
        _db_instance = ChatDatabase(db_path)
    return _db_instance


def generate_chat_title(first_message: str, max_length: int = 50) -> str:
    """Generate a chat title from the first user message."""
    if not first_message.strip():
        return "New Chat"

    title = first_message.strip()
    title = " ".join(title.split())

    if len(title) > max_length:
        title = title[: max_length - 3] + "..."

    return title
