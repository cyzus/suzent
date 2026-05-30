"""Database models and query helpers for Suzent persistence."""

import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from pydantic import BaseModel
from sqlalchemy import Text, cast, or_
from sqlmodel import Column, Field, JSON, Relationship, SQLModel


def _json_escape_for_like(s: str) -> str:
    """Return the \\uXXXX form of any non-ASCII chars in s.

    SQLAlchemy's JSON column stores non-ASCII characters as \\uXXXX escape
    sequences (ensure_ascii=True default). A plain LIKE '%中文%' therefore
    never matches; we must search for '\\u4e2d\\u6587' instead.
    ASCII characters are left unchanged so English searches still work.
    """
    result = []
    for ch in s:
        if ord(ch) > 127:
            result.append(f"\\u{ord(ch):04x}")
        else:
            result.append(ch)
    return "".join(result)


def messages_search_filter(search: str) -> Any:
    """Build an OR filter that matches search in the messages JSON column."""
    escaped = _json_escape_for_like(search)
    if escaped == search:
        return cast(ChatModel.messages, Text).contains(search)
    return or_(
        cast(ChatModel.messages, Text).contains(search),
        cast(ChatModel.messages, Text).contains(escaped),
    )


class ChatSummaryModel(BaseModel):
    """Bail-out model for chat listing."""

    id: str
    title: str
    createdAt: str
    updatedAt: str
    messageCount: int
    lastMessage: Optional[str] = None
    platform: Optional[str] = None
    heartbeatEnabled: bool = False
    lastResultAt: Optional[str] = None
    unreadCount: int = 0
    projectId: Optional[str] = None
    projectSlug: Optional[str] = None
    projectName: Optional[str] = None
    parentChatId: Optional[str] = None


class ProjectModel(SQLModel, table=True):
    """Project groups multiple chat sessions and owns a shared plan."""

    __tablename__ = "projects"

    id: str = Field(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
    name: str
    slug: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    archived: bool = Field(default=False)

    chats: List["ChatModel"] = Relationship(back_populates="project")


class ChatModel(SQLModel, table=True):
    """Chat session with messages and configuration."""

    __tablename__ = "chats"

    id: str = Field(primary_key=True)
    title: str
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")
    config: dict = Field(default_factory=dict, sa_column=Column(JSON))
    messages: list = Field(default_factory=list, sa_column=Column(JSON))
    context_usage: dict = Field(default_factory=dict, sa_column=Column(JSON))
    agent_state: Optional[bytes] = None

    # Session lifecycle fields
    last_active_at: Optional[datetime] = None
    turn_count: int = Field(default=0)

    # Two-phase post-process state tracking
    state_revision: int = Field(default=0)
    finalized_revision: int = Field(default=0)
    state_stage: Optional[str] = None  # snapshot | finalized
    state_updated_at: Optional[datetime] = None

    # Background execution tracking - written only by background executors
    last_result_at: Optional[datetime] = None

    # Working directory binding (S2O Phase 1)
    working_directory: Optional[str] = None

    # Project association
    project_id: Optional[str] = Field(
        default=None, foreign_key="projects.id", index=True
    )
    project: Optional[ProjectModel] = Relationship(back_populates="chats")

    plans: List["PlanModel"] = Relationship(
        back_populates="chat",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class RetryCheckpointModel(SQLModel, table=True):
    """Stores the last retry checkpoint for a chat session (one row per chat)."""

    __tablename__ = "retry_checkpoints"

    chat_id: str = Field(primary_key=True)
    agent_state_before: Optional[bytes] = None
    messages_before: list = Field(default_factory=list, sa_column=Column(JSON))
    user_message: str = Field(default="")
    user_files: list = Field(default_factory=list, sa_column=Column(JSON))
    config_snapshot: dict = Field(default_factory=dict, sa_column=Column(JSON))
    has_file_snapshot: bool = Field(default=False)
    # Serialised FileTracker snapshot: list of {path, backup_name, version, backup_time}
    file_snapshot: list = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PlanModel(SQLModel, table=True):
    """Execution plan associated with a chat session."""

    __tablename__ = "plans"

    id: Optional[int] = Field(default=None, primary_key=True)
    chat_id: str = Field(foreign_key="chats.id", index=True)
    objective: str
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")

    chat: Optional[ChatModel] = Relationship(back_populates="plans")
    tasks: List["TaskModel"] = Relationship(
        back_populates="plan",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class TaskModel(SQLModel, table=True):
    """Individual task within a plan."""

    __tablename__ = "tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="plans.id", index=True)
    number: int = Field(index=True)
    description: str
    status: str = Field(default="pending")
    note: Optional[str] = None
    capabilities: Optional[str] = None
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")

    plan: Optional[PlanModel] = Relationship(back_populates="tasks")


class UserPreferencesModel(SQLModel):
    """Singleton table for global user preferences."""

    id: int = Field(default=1, primary_key=True)
    model: Optional[str] = None
    agent: Optional[str] = None
    tools: Optional[list] = Field(default=None, sa_column=Column(JSON))
    memory_enabled: bool = Field(default=False)
    sandbox_enabled: bool = Field(default=True)
    sandbox_volumes: Optional[list] = Field(default=None, sa_column=Column(JSON))
    updated_at: datetime = Field(serialization_alias="updatedAt")


class VolumeMetadataModel(SQLModel, table=True):
    """Cached metadata for configured custom volumes."""

    __tablename__ = "volume_metadata"

    volume: str = Field(primary_key=True)
    host_path: str
    mount_point: str
    kind: str = Field(default="generic")
    exists: bool = Field(default=False)
    is_git_repo: Optional[bool] = None
    git_root: Optional[str] = None
    status: str = Field(default="unknown")
    error: Optional[str] = None
    checked_at: datetime = Field(serialization_alias="checkedAt")


class MCPServerModel(SQLModel, table=True):
    """MCP server configuration."""

    __tablename__ = "mcp_servers"

    name: str = Field(primary_key=True)
    type: str  # "url" or "stdio"
    url: Optional[str] = None
    headers: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    command: Optional[str] = None
    args: Optional[list] = Field(default=None, sa_column=Column(JSON))
    env: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    enabled: bool = Field(default=True)
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")


class ApiKeyModel(SQLModel):
    """Compatibility model for API key-shaped config values."""

    key: str = Field(primary_key=True)
    value: str
    updated_at: datetime = Field(serialization_alias="updatedAt")


class CostLedgerModel(SQLModel, table=True):
    """Global cost ledger - every LLM call is recorded here.

    Entries survive chat deletion so lifetime spend is always accurate.
    """

    __tablename__ = "cost_ledger"

    id: Optional[int] = Field(default=None, primary_key=True)
    chat_id: Optional[str] = None
    model: str
    role: str = "primary"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatCostSummaryModel(SQLModel, table=True):
    """Per-chat cost summary - denormalized for fast per-chat queries.

    Can be rebuilt from ``cost_ledger`` if needed.
    """

    __tablename__ = "chat_cost_summary"

    chat_id: str = Field(primary_key=True)
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_write_tokens: int = 0
    total_cache_read_tokens: int = 0
    last_updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class MemoryConfigModel(SQLModel):
    """Singleton table for memory system configuration."""

    id: int = Field(default=1, primary_key=True)
    embedding_model: Optional[str] = None
    extraction_model: Optional[str] = None
    updated_at: datetime = Field(serialization_alias="updatedAt")


class CronJobModel(SQLModel, table=True):
    """Scheduled cron job for automated task execution."""

    __tablename__ = "cron_jobs"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    cron_expr: str
    prompt: str
    active: bool = Field(default=True)
    delivery_mode: str = Field(default="announce")  # "announce" | "none"
    model_override: Optional[str] = None
    retry_count: int = Field(default=0)
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    last_result: Optional[str] = None
    last_error: Optional[str] = None
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")


class CronRunModel(SQLModel, table=True):
    """History record for a single cron job execution."""

    __tablename__ = "cron_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(index=True)
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str = Field(default="running")  # "running" | "success" | "error"
    result: Optional[str] = None
    error: Optional[str] = None


class PostprocessJobModel(SQLModel, table=True):
    """Postprocess job tracking for chat turn completion.

    Tracks the full lifecycle of a postprocess job from snapshot through finalize,
    including per-step status (B1..B7) and retry attempts.
    """

    __tablename__ = "postprocess_jobs"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(index=True, unique=True)  # UUID-based unique ID
    chat_id: str = Field(foreign_key="chats.id", index=True)
    assigned_revision: int  # Revision from A phase snapshot
    current_revision: Optional[int] = None  # Latest revision (for guard check)
    status: str = Field(
        default="pending"
    )  # pending | running | success | failed | skipped_stale
    outcome: Optional[str] = None  # success | failed | skipped_stale
    attempt: int = Field(default=1)
    max_attempts: int = Field(default=3)

    # Step status tracking (B1..B7)
    step_status_json: Optional[str] = (
        None  # JSON dict of {step: {status, error, duration_ms}}
    )

    # Timing
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None

    # Error tracking
    error_class: Optional[str] = None
    error_message: Optional[str] = None

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    updated_at: datetime = Field(default_factory=lambda: datetime.now())


class PostProcessStep:
    """Constant definitions for postprocess steps B1..B7."""

    TRANSCRIPT = "B1_transcript"
    MEMORY = "B2_memory"
    COMPRESS = "B3_compress"
    DISPLAY = "B4_display"
    PERSIST = "B5_persist"
    LIFECYCLE = "B6_lifecycle"
    MIRROR = "B7_mirror"

    ALL = [TRANSCRIPT, MEMORY, COMPRESS, DISPLAY, PERSIST, LIFECYCLE, MIRROR]


class PostProcessStatus:
    """Constant definitions for postprocess job statuses."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED_STALE = "skipped_stale"


class PostProcessOutcome:
    """Constant definitions for postprocess job outcomes."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED_STALE = "skipped_stale"


class StepStatus:
    """Constant definitions for individual step status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class PostProcessMetrics:
    """Container for postprocess metrics."""

    def __init__(self):
        self.snapshot_committed = 0
        self.snapshot_failed = 0
        self.job_started = 0
        self.job_success = 0
        self.job_failed = 0
        self.job_skipped_stale = 0
        self.total_duration_ms = 0


_postprocess_metrics = PostProcessMetrics()
