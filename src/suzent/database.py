"""
Database layer for chat persistence using SQLModel.

Provides a clean, type-safe interface for all database operations.
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import selectinload
from sqlalchemy import text, inspect
from sqlmodel import (
    Column,
    Field,
    JSON,
    Relationship,
    Session,
    SQLModel,
    create_engine,
    select,
)


# -----------------------------------------------------------------------------
# SQLModel Table Definitions
# -----------------------------------------------------------------------------


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


class ChatModel(SQLModel, table=True):
    """Chat session with messages and configuration."""

    __tablename__ = "chats"

    id: str = Field(primary_key=True)
    title: str
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")
    config: dict = Field(default_factory=dict, sa_column=Column(JSON))
    messages: list = Field(default_factory=list, sa_column=Column(JSON))
    agent_state: Optional[bytes] = None

    # Session lifecycle fields
    last_active_at: Optional[datetime] = None
    turn_count: int = Field(default=0)

    # Two-phase post-process state tracking
    state_revision: int = Field(default=0)
    finalized_revision: int = Field(default=0)
    state_stage: Optional[str] = None  # snapshot | finalized
    state_updated_at: Optional[datetime] = None

    # Background execution tracking — written only by background executors
    last_result_at: Optional[datetime] = None

    # Working directory binding (S2O Phase 1)
    working_directory: Optional[str] = None

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


class UserPreferencesModel(SQLModel, table=True):
    """Singleton table for global user preferences."""

    __tablename__ = "user_preferences"

    id: int = Field(default=1, primary_key=True)
    model: Optional[str] = None
    agent: Optional[str] = None
    tools: Optional[list] = Field(default=None, sa_column=Column(JSON))
    memory_enabled: bool = Field(default=False)
    sandbox_enabled: bool = Field(default=True)
    sandbox_volumes: Optional[list] = Field(default=None, sa_column=Column(JSON))
    updated_at: datetime = Field(serialization_alias="updatedAt")


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


class ApiKeyModel(SQLModel, table=True):
    """Secure storage for API keys."""

    __tablename__ = "api_keys"

    key: str = Field(primary_key=True)
    value: str
    updated_at: datetime = Field(serialization_alias="updatedAt")


class MemoryConfigModel(SQLModel, table=True):
    """Singleton table for memory system configuration."""

    __tablename__ = "memory_config"

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


# PostProcess Step Constants
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


# Post Process Status Constants
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


# Step Status Constants per Step
class StepStatus:
    """Constant definitions for individual step status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


# Metrics counters (in-memory for now, can be persisted later)
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


# Global metrics instance
_postprocess_metrics = PostProcessMetrics()


# -----------------------------------------------------------------------------
# Database Management
# -----------------------------------------------------------------------------


class ChatDatabase:
    """Handles database operations for chat persistence using SQLModel."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            # Use data directory from config if available, otherwise relative to project
            try:
                from suzent.config import DATA_DIR

                self.db_path = DATA_DIR / "chats.db"
            except ImportError:
                self.db_path = Path(".suzent/chats.db")
        else:
            self.db_path = Path(db_path)

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # If db_path is a directory (Docker mount issue), remove it and create file
        if self.db_path.is_dir():
            import shutil

            shutil.rmtree(self.db_path)

        # Create engine with SQLite
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )

        # Create all tables
        SQLModel.metadata.create_all(self.engine)

        # Run migrations for new columns
        self._run_migrations()

    def _run_migrations(self):
        """Run database migrations for new columns."""
        inspector = inspect(self.engine)

        # Migration: Add 'headers' column to 'mcp_servers' table
        if "mcp_servers" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("mcp_servers")]
            if "headers" not in columns:
                with self.engine.connect() as conn:
                    conn.execute(
                        text("ALTER TABLE mcp_servers ADD COLUMN headers TEXT")
                    )
                    conn.commit()

        # Migration: Add retry_count and drop legacy is_heartbeat from cron_jobs
        if "cron_jobs" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("cron_jobs")]
            with self.engine.connect() as conn:
                if "retry_count" not in columns:
                    conn.execute(
                        text(
                            "ALTER TABLE cron_jobs ADD COLUMN retry_count INTEGER DEFAULT 0"
                        )
                    )
                if "is_heartbeat" in columns:
                    conn.execute(text("ALTER TABLE cron_jobs DROP COLUMN is_heartbeat"))
                conn.commit()

        # Migration: Add session lifecycle columns to 'chats' table
        if "chats" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("chats")]
            with self.engine.connect() as conn:
                if "last_active_at" not in columns:
                    conn.execute(
                        text("ALTER TABLE chats ADD COLUMN last_active_at DATETIME")
                    )
                if "turn_count" not in columns:
                    conn.execute(
                        text(
                            "ALTER TABLE chats ADD COLUMN turn_count INTEGER DEFAULT 0"
                        )
                    )
                if "last_result_at" not in columns:
                    conn.execute(
                        text("ALTER TABLE chats ADD COLUMN last_result_at DATETIME")
                    )
                if "working_directory" not in columns:
                    conn.execute(
                        text("ALTER TABLE chats ADD COLUMN working_directory TEXT")
                    )
                if "state_revision" not in columns:
                    conn.execute(
                        text(
                            "ALTER TABLE chats ADD COLUMN state_revision INTEGER DEFAULT 0"
                        )
                    )
                if "finalized_revision" not in columns:
                    conn.execute(
                        text(
                            "ALTER TABLE chats ADD COLUMN finalized_revision INTEGER DEFAULT 0"
                        )
                    )
                if "state_stage" not in columns:
                    conn.execute(text("ALTER TABLE chats ADD COLUMN state_stage TEXT"))
                if "state_updated_at" not in columns:
                    conn.execute(
                        text("ALTER TABLE chats ADD COLUMN state_updated_at DATETIME")
                    )
                conn.commit()

        # Migration: Ensure postprocess_jobs table exists (auto-created by SQLModel)
        # Verify it exists after create_all() runs
        if "postprocess_jobs" not in inspector.get_table_names():
            # This should not happen as SQLModel.metadata.create_all() already ran
            # but adding for safety
            with self.engine.connect() as conn:
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS postprocess_jobs (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            job_id TEXT NOT NULL UNIQUE,
                            chat_id TEXT NOT NULL,
                            assigned_revision INTEGER NOT NULL,
                            current_revision INTEGER,
                            status TEXT DEFAULT 'pending',
                            outcome TEXT,
                            attempt INTEGER DEFAULT 1,
                            max_attempts INTEGER DEFAULT 3,
                            step_status_json TEXT,
                            started_at DATETIME,
                            finished_at DATETIME,
                            duration_ms INTEGER,
                            error_class TEXT,
                            error_message TEXT,
                            created_at DATETIME,
                            updated_at DATETIME,
                            FOREIGN KEY(chat_id) REFERENCES chats(id)
                        )
                        """
                    )
                )
                # Create indexes for query performance
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_postprocess_jobs_chat_id ON postprocess_jobs(chat_id)"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_postprocess_jobs_status ON postprocess_jobs(status)"
                    )
                )
                conn.commit()

    def _session(self) -> Session:
        """Create a new database session."""
        return Session(self.engine)

    # -------------------------------------------------------------------------
    # Chat Operations
    # -------------------------------------------------------------------------

    def create_chat(
        self,
        title: str,
        config: Dict[str, Any],
        messages: List[Dict[str, Any]] = None,
        agent_state: bytes = None,
        chat_id: str = None,
        working_directory: str = None,
    ) -> str:
        """Create a new chat and return its ID."""
        now = datetime.now()
        chat_id = chat_id or str(uuid.uuid4())
        chat = ChatModel(
            id=chat_id,
            title=title,
            created_at=now,
            updated_at=now,
            config=config,
            messages=messages or [],
            agent_state=agent_state,
            working_directory=working_directory,
        )

        with self._session() as session:
            session.add(chat)
            session.commit()

        return chat_id

    def get_chat(self, chat_id: str) -> Optional[ChatModel]:
        """Get a specific chat by ID."""
        with self._session() as session:
            return session.get(ChatModel, chat_id)

    def update_chat(
        self,
        chat_id: str,
        title: str = None,
        config: Dict[str, Any] = None,
        messages: List[Dict[str, Any]] = None,
        agent_state: bytes = None,
        working_directory: str = None,
    ) -> bool:
        """Update an existing chat."""
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return False

            should_update_timestamp = False

            if title is not None and title != chat.title:
                chat.title = title
                should_update_timestamp = True

            if config is not None:
                chat.config = config

            if messages is not None:
                chat.messages = messages
                should_update_timestamp = True

            if agent_state is not None:
                chat.agent_state = agent_state
                should_update_timestamp = True

            if working_directory is not None:
                chat.working_directory = working_directory

            if should_update_timestamp:
                chat.updated_at = datetime.now()

            session.add(chat)
            session.commit()
            return True

    def commit_snapshot_state(self, chat_id: str, agent_state: bytes) -> Optional[int]:
        """Commit fast snapshot state and increment revision atomically.

        Returns:
            The new state revision if the chat exists, otherwise None.
        """
        now = datetime.now()
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if not chat:
                _postprocess_metrics.snapshot_failed += 1
                return None

            next_revision = (chat.state_revision or 0) + 1
            chat.agent_state = agent_state
            chat.state_revision = next_revision
            chat.state_stage = "snapshot"
            chat.state_updated_at = now
            chat.updated_at = now

            session.add(chat)
            session.commit()

        _postprocess_metrics.snapshot_committed += 1
        return next_revision

    def finalize_state_if_revision_matches(
        self,
        chat_id: str,
        expected_revision: int,
        agent_state: bytes,
        messages: Optional[List[Dict[str, Any]]] = None,
        update_lifecycle: bool = True,
    ) -> bool:
        """Finalize chat state only when revision matches expected value.

        Returns:
            True when finalized commit succeeds, False when stale/not found.
        """
        now = datetime.now()
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return False

            current_revision = chat.state_revision or 0
            if current_revision != expected_revision:
                return False

            chat.agent_state = agent_state
            if messages is not None:
                chat.messages = messages
            chat.finalized_revision = expected_revision
            chat.state_stage = "finalized"
            chat.state_updated_at = now
            chat.updated_at = now

            if update_lifecycle:
                chat.last_active_at = now
                chat.turn_count = (chat.turn_count or 0) + 1

            session.add(chat)
            session.commit()
            return True

    def delete_chat(self, chat_id: str) -> bool:
        """Delete a chat by ID."""
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return False

            session.delete(chat)
            session.commit()
            return True

    def set_last_result_at(self, chat_id: str) -> None:
        """Mark that a background executor just completed a turn for this chat."""
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if chat:
                chat.last_result_at = datetime.now(timezone.utc)
                session.add(chat)
                session.commit()

    def list_chats(
        self,
        limit: int = 50,
        offset: int = 0,
        search: str = None,
    ) -> List[ChatSummaryModel]:
        """List chat summaries ordered by last updated."""
        with self._session() as session:
            statement = select(ChatModel).order_by(ChatModel.updated_at.desc())

            if search:
                statement = statement.where(ChatModel.title.contains(search))

            statement = statement.offset(offset).limit(limit)
            chats = session.exec(statement).all()

            results = []
            import re

            for chat in chats:
                messages = chat.messages or []
                last_message = None
                if messages:
                    last_msg = messages[-1]
                    if isinstance(last_msg, dict):
                        content = last_msg.get("content") or ""
                    else:
                        content = str(last_msg)

                    if isinstance(content, list):
                        # Extract text from list of dicts (e.g. OpenAI vision)
                        text_parts = []
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                text_parts.append(part.get("text", ""))
                            elif isinstance(part, str):
                                text_parts.append(part)
                        content = " ".join(text_parts)
                    elif not isinstance(content, str):
                        content = str(content)

                    # 1. completely eradicate any <details> tool blocks (including inner text)
                    clean_content = re.sub(
                        r"<details\b[^>]*>.*?</details>", "", content, flags=re.DOTALL
                    )
                    # 2. Strip remaining raw HTML tags
                    clean_content = re.sub(r"<[^>]+>", "", clean_content).strip()

                    last_message = clean_content[:100]
                    if len(clean_content) > 100:
                        last_message += "..."

                config = chat.config or {}
                # Count only assistant messages for unread badge purposes.
                # User messages are already known to the sender; tool-result
                # messages (role="tool") are collapsed into the preceding
                # assistant bubble in the UI.
                visible_count = sum(
                    1
                    for m in messages
                    if isinstance(m, dict) and m.get("role") == "assistant"
                )
                results.append(
                    ChatSummaryModel(
                        id=chat.id,
                        title=chat.title,
                        createdAt=chat.created_at.isoformat(),
                        updatedAt=chat.updated_at.isoformat(),
                        messageCount=visible_count,
                        lastMessage=last_message,
                        platform=config.get("platform"),
                        heartbeatEnabled=config.get("heartbeat_enabled", False),
                        lastResultAt=chat.last_result_at.isoformat()
                        if chat.last_result_at
                        else None,
                    )
                )

            return results

    def get_chat_count(self, search: str = None) -> int:
        """Get total number of chats."""
        with self._session() as session:
            statement = select(ChatModel)
            if search:
                # Simplified search logic matching list_chats
                statement = statement.where(ChatModel.title.contains(search))
            return len(session.exec(statement).all())

    def reassign_plan_chat(self, old_chat_id: str, new_chat_id: str) -> int:
        """Reassign all plans from one chat_id to another."""
        if old_chat_id == new_chat_id:
            return 0

        with self._session() as session:
            statement = select(PlanModel).where(PlanModel.chat_id == old_chat_id)
            plans = session.exec(statement).all()

            for plan in plans:
                plan.chat_id = new_chat_id
                plan.updated_at = datetime.now()
                session.add(plan)

            session.commit()
            return len(plans)

    def get_active_heartbeats(self) -> List[ChatModel]:
        """Get all chats that have heartbeat enabled in their config."""
        with self._session() as session:
            statement = select(ChatModel)
            chats = session.exec(statement).all()
            return [c for c in chats if c.config.get("heartbeat_enabled") is True]

    # -------------------------------------------------------------------------
    # PostProcess Job Operations
    # -------------------------------------------------------------------------

    def create_postprocess_job(
        self,
        job_id: str,
        chat_id: str,
        assigned_revision: int,
        max_attempts: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """Create a new postprocess job record.

        Args:
            job_id: UUID-based unique job identifier
            chat_id: Chat ID for this job
            assigned_revision: Revision from Phase A snapshot
            max_attempts: Max retry attempts (default: 3)

        Returns:
            Dict with job data if successful, None otherwise.
        """
        now = datetime.now()
        with self._session() as session:
            # Verify chat exists
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return None

            job = PostprocessJobModel(
                job_id=job_id,
                chat_id=chat_id,
                assigned_revision=assigned_revision,
                status=PostProcessStatus.PENDING,
                attempt=1,
                max_attempts=max_attempts,
                created_at=now,
                updated_at=now,
            )
            session.add(job)
            session.commit()

            # Increment metrics
            _postprocess_metrics.job_started += 1

            # Return dict representation while still in session context
            return {
                "id": job.id,
                "job_id": job.job_id,
                "chat_id": job.chat_id,
                "assigned_revision": job.assigned_revision,
                "status": job.status,
                "attempt": job.attempt,
                "max_attempts": job.max_attempts,
            }

    def start_postprocess_job(self, job_id: str) -> bool:
        """Mark a postprocess job as running."""
        now = datetime.now()
        with self._session() as session:
            statement = select(PostprocessJobModel).where(
                PostprocessJobModel.job_id == job_id
            )
            job = session.exec(statement).first()
            if not job:
                return False

            job.status = PostProcessStatus.RUNNING
            job.started_at = now
            job.updated_at = now
            session.add(job)
            session.commit()
            return True

    def update_job_step_status(
        self,
        job_id: str,
        step: str,
        status: str,
        error: str = None,
        duration_ms: int = None,
    ) -> bool:
        """Update status of a specific step within a postprocess job.

        Args:
            job_id: Job identifier
            step: Step name (B1_transcript, B2_memory, etc.)
            status: Step status (pending, running, success, failed)
            error: Error message if failed
            duration_ms: Duration of the step in milliseconds

        Returns:
            True if updated successfully, False if job not found.
        """
        now = datetime.now()
        with self._session() as session:
            statement = select(PostprocessJobModel).where(
                PostprocessJobModel.job_id == job_id
            )
            job = session.exec(statement).first()
            if not job:
                return False

            # Parse or initialize step_status_json
            try:
                step_status = json.loads(job.step_status_json or "{}")
            except (json.JSONDecodeError, TypeError):
                step_status = {}

            # Update step status
            step_status[step] = {
                "status": status,
                "error": error,
                "duration_ms": duration_ms,
                "updated_at": now.isoformat(),
            }

            job.step_status_json = json.dumps(step_status)
            job.updated_at = now
            session.add(job)
            session.commit()
            return True

    def finalize_postprocess_job(
        self,
        job_id: str,
        outcome: str,
        error_class: str = None,
        error_message: str = None,
    ) -> bool:
        """Mark a postprocess job as complete.

        Args:
            job_id: Job identifier
            outcome: Outcome code (success, failed, skipped_stale)
            error_class: Exception class name if failed
            error_message: Error details if failed

        Returns:
            True if finalized successfully, False if job not found.
        """
        now = datetime.now()
        with self._session() as session:
            statement = select(PostprocessJobModel).where(
                PostprocessJobModel.job_id == job_id
            )
            job = session.exec(statement).first()
            if not job:
                return False

            job.status = (
                PostProcessStatus.SUCCESS
                if outcome == PostProcessOutcome.SUCCESS
                else PostProcessStatus.FAILED
            )
            job.outcome = outcome
            job.finished_at = now
            job.error_class = error_class
            job.error_message = error_message

            if job.started_at:
                job.duration_ms = int((now - job.started_at).total_seconds() * 1000)

            job.updated_at = now
            session.add(job)
            session.commit()

            # Update metrics
            if outcome == PostProcessOutcome.SUCCESS:
                _postprocess_metrics.job_success += 1
                _postprocess_metrics.total_duration_ms += job.duration_ms or 0
            elif outcome == PostProcessOutcome.SKIPPED_STALE:
                _postprocess_metrics.job_skipped_stale += 1
            else:
                _postprocess_metrics.job_failed += 1

            return True

    def get_postprocess_job(self, job_id: str) -> Optional[PostprocessJobModel]:
        """Retrieve a postprocess job by ID."""
        with self._session() as session:
            statement = select(PostprocessJobModel).where(
                PostprocessJobModel.job_id == job_id
            )
            return session.exec(statement).first()

    def list_postprocess_jobs(
        self, chat_id: str, limit: int = 50
    ) -> List[PostprocessJobModel]:
        """List postprocess jobs for a specific chat."""
        with self._session() as session:
            statement = (
                select(PostprocessJobModel)
                .where(PostprocessJobModel.chat_id == chat_id)
                .order_by(PostprocessJobModel.created_at.desc())
                .limit(limit)
            )
            return session.exec(statement).all()

    def get_postprocess_metrics(self) -> Dict[str, Any]:
        """Get current postprocess metrics."""
        return {
            "snapshot_committed": _postprocess_metrics.snapshot_committed,
            "snapshot_failed": _postprocess_metrics.snapshot_failed,
            "job_started": _postprocess_metrics.job_started,
            "job_success": _postprocess_metrics.job_success,
            "job_failed": _postprocess_metrics.job_failed,
            "job_skipped_stale": _postprocess_metrics.job_skipped_stale,
            "total_duration_ms": _postprocess_metrics.total_duration_ms,
        }

    def get_retriable_postprocess_jobs(
        self, max_age_seconds: int = 3600
    ) -> List[PostprocessJobModel]:
        """Get postprocess jobs eligible for retry.

        Criteria:
        - Status is 'failed' (not 'skipped_stale')
        - attempt < max_attempts
        - Not recently attempted (to avoid retry storms)

        Args:
            max_age_seconds: Only retry jobs older than this (default: 1 hour)

        Returns:
            List of PostprocessJobModel objects eligible for retry.
        """
        cutoff = datetime.now() - timedelta(seconds=max_age_seconds)

        with self._session() as session:
            statement = (
                select(PostprocessJobModel)
                .where(PostprocessJobModel.outcome == PostProcessOutcome.FAILED)
                .where(PostprocessJobModel.attempt < PostprocessJobModel.max_attempts)
                .where(PostprocessJobModel.updated_at < cutoff)
                .order_by(PostprocessJobModel.updated_at.asc())
                .limit(10)
            )
            return session.exec(statement).all()

    def prepare_job_for_retry(self, job_id: str) -> bool:
        """Prepare a job for retry by incrementing attempt count and resetting status.

        Args:
            job_id: Job identifier

        Returns:
            True if prepared successfully, False if job not found or not eligible.
        """
        now = datetime.now()
        with self._session() as session:
            statement = select(PostprocessJobModel).where(
                PostprocessJobModel.job_id == job_id
            )
            job = session.exec(statement).first()
            if not job:
                return False

            # Only reset if currently failed or needs retry
            if job.outcome != PostProcessOutcome.FAILED:
                return False

            if job.attempt >= job.max_attempts:
                return False

            job.attempt += 1
            job.status = PostProcessStatus.PENDING
            job.outcome = None
            job.started_at = None
            job.finished_at = None
            job.duration_ms = None
            job.error_class = None
            job.error_message = None
            job.step_status_json = None
            job.updated_at = now

            session.add(job)
            session.commit()
            return True

    # -------------------------------------------------------------------------
    # Plan Operations
    # -------------------------------------------------------------------------

    def create_plan(
        self,
        chat_id: str,
        objective: str,
        tasks: List[Dict[str, Any]] = None,
    ) -> int:
        """Create or update the single plan for a chat and return its ID."""
        now = datetime.now()
        tasks = tasks or []

        with self._session() as session:
            # Check for existing plan
            statement = select(PlanModel).where(PlanModel.chat_id == chat_id).limit(1)
            existing_plan = session.exec(statement).first()

            if existing_plan:
                plan_id = existing_plan.id
                existing_plan.objective = objective
                existing_plan.updated_at = now
                session.add(existing_plan)

                # Delete existing tasks
                task_stmt = select(TaskModel).where(TaskModel.plan_id == plan_id)
                for task in session.exec(task_stmt).all():
                    session.delete(task)
            else:
                # Create new plan
                new_plan = PlanModel(
                    chat_id=chat_id,
                    objective=objective,
                    created_at=now,
                    updated_at=now,
                )
                session.add(new_plan)
                session.commit()
                session.refresh(new_plan)
                plan_id = new_plan.id

            # Create tasks
            for task_data in tasks:
                task = TaskModel(
                    plan_id=plan_id,
                    number=task_data.get("number"),
                    description=task_data.get("description"),
                    status=task_data.get("status", "pending"),
                    note=task_data.get("note"),
                    capabilities=task_data.get("capabilities"),
                    created_at=now,
                    updated_at=now,
                )
                session.add(task)

            session.commit()
            return plan_id

    def get_plan(self, chat_id: str) -> Optional[PlanModel]:
        """Get the latest plan for a specific chat."""
        with self._session() as session:
            statement = (
                select(PlanModel)
                .where(PlanModel.chat_id == chat_id)
                .order_by(PlanModel.created_at.desc())
                .options(selectinload(PlanModel.tasks))
                .limit(1)
            )
            plan = session.exec(statement).first()
            if not plan:
                return None

            # Ensure tasks are sorted (SQLModel might not guarantee order in relationship list)
            plan.tasks.sort(key=lambda t: t.number)
            return plan

    def get_plan_by_id(self, plan_id: int) -> Optional[PlanModel]:
        """Fetch a plan and its tasks by plan ID."""
        with self._session() as session:
            statement = (
                select(PlanModel)
                .where(PlanModel.id == plan_id)
                .options(selectinload(PlanModel.tasks))
            )
            plan = session.exec(statement).first()
            if not plan:
                return None

            plan.tasks.sort(key=lambda t: t.number)
            return plan

    def list_plans(
        self,
        chat_id: str,
        limit: Optional[int] = None,
    ) -> List[PlanModel]:
        """Return all plans for a chat ordered by newest first."""
        with self._session() as session:
            statement = (
                select(PlanModel)
                .where(PlanModel.chat_id == chat_id)
                .order_by(PlanModel.created_at.desc())
                .options(selectinload(PlanModel.tasks))
            )
            if limit is not None:
                statement = statement.limit(limit)

            plans = session.exec(statement).all()
            for plan in plans:
                plan.tasks.sort(key=lambda t: t.number)
            return plans

    def update_plan_objective(self, plan_id: int, objective: str) -> bool:
        """Update the objective of a plan."""
        with self._session() as session:
            plan = session.get(PlanModel, plan_id)
            if not plan:
                return False

            plan.objective = objective
            plan.updated_at = datetime.now()
            session.add(plan)
            session.commit()
            return True

    def create_task(self, plan_id: int, description: str, number: int) -> Optional[int]:
        """Add a new task to a plan."""
        now = datetime.now()
        with self._session() as session:
            plan = session.get(PlanModel, plan_id)
            if not plan:
                return None

            task = TaskModel(
                plan_id=plan_id,
                description=description,
                number=number,
                created_at=now,
                updated_at=now,
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            return task.id

    def update_task_status(
        self,
        chat_id: str,
        task_number: int,
        status: str,
        note: str = None,
        plan_id: Optional[int] = None,
    ) -> bool:
        """Update the status and optionally note of a specific task."""
        now = datetime.now()

        with self._session() as session:
            # Find the plan
            if plan_id is not None:
                plan = session.get(PlanModel, plan_id)
                if plan and plan.chat_id != chat_id:
                    plan = None
            else:
                statement = (
                    select(PlanModel)
                    .where(PlanModel.chat_id == chat_id)
                    .order_by(PlanModel.created_at.desc())
                    .limit(1)
                )
                plan = session.exec(statement).first()

            if not plan:
                return False

            # Find and update the task
            task_stmt = select(TaskModel).where(
                (TaskModel.plan_id == plan.id) & (TaskModel.number == task_number)
            )
            task = session.exec(task_stmt).first()

            if not task:
                return False

            task.status = status
            task.updated_at = now
            if note is not None:
                task.note = note

            session.add(task)
            session.commit()
            return True

    def update_task(
        self,
        task_id: int,
        status: str = None,
        description: str = None,
        note: str = None,
        capabilities: str = None,
    ) -> bool:
        """Update a task's details."""
        with self._session() as session:
            task = session.get(TaskModel, task_id)
            if not task:
                return False

            if status:
                task.status = status
            if description:
                task.description = description
            if note:
                task.note = note
            if capabilities:
                task.capabilities = capabilities

            task.updated_at = datetime.now()
            session.add(task)
            session.commit()
            return True

    def delete_task(self, task_id: int) -> bool:
        """Delete a task."""
        with self._session() as session:
            task = session.get(TaskModel, task_id)
            if not task:
                return False
            session.delete(task)
            session.commit()
            return True

    def delete_plan(self, chat_id: str) -> bool:
        """Delete the plan for a specific chat."""
        with self._session() as session:
            statement = select(PlanModel).where(PlanModel.chat_id == chat_id)
            plans = session.exec(statement).all()

            if not plans:
                return False

            for plan in plans:
                session.delete(plan)

            session.commit()
            return True

    # -------------------------------------------------------------------------
    # User Preferences Operations
    # -------------------------------------------------------------------------

    def get_user_preferences(self) -> Optional[UserPreferencesModel]:
        """Get user preferences from the database."""
        with self._session() as session:
            prefs = session.get(UserPreferencesModel, 1)
            # Handle missing preferences by returning None or empty model?
            # Consumers expect object or None.
            return prefs

    def save_user_preferences(
        self,
        model: str = None,
        agent: str = None,
        tools: List[str] = None,
        memory_enabled: bool = None,
        sandbox_enabled: bool = None,
        sandbox_volumes: List[str] = None,
    ) -> bool:
        """Save user preferences to the database."""
        now = datetime.now()

        with self._session() as session:
            prefs = session.get(UserPreferencesModel, 1)

            if prefs:
                # Update existing
                if model is not None:
                    prefs.model = model
                if agent is not None:
                    prefs.agent = agent
                if tools is not None:
                    prefs.tools = tools
                if memory_enabled is not None:
                    prefs.memory_enabled = memory_enabled
                if sandbox_enabled is not None:
                    prefs.sandbox_enabled = sandbox_enabled
                if sandbox_volumes is not None:
                    prefs.sandbox_volumes = sandbox_volumes
                prefs.updated_at = now
            else:
                # Create new
                prefs = UserPreferencesModel(
                    id=1,
                    model=model,
                    agent=agent,
                    tools=tools,
                    memory_enabled=memory_enabled
                    if memory_enabled is not None
                    else False,
                    sandbox_enabled=sandbox_enabled
                    if sandbox_enabled is not None
                    else True,
                    sandbox_volumes=sandbox_volumes,
                    updated_at=now,
                )

            session.add(prefs)
            session.commit()
            return True

    # -------------------------------------------------------------------------
    # Memory Configuration Operations
    # -------------------------------------------------------------------------

    def get_memory_config(self) -> Optional[MemoryConfigModel]:
        """Get memory system configuration from the database."""
        with self._session() as session:
            return session.get(MemoryConfigModel, 1)

    def save_memory_config(
        self,
        embedding_model: str = None,
        extraction_model: str = None,
    ) -> bool:
        """Save memory system configuration to the database."""
        now = datetime.now()

        with self._session() as session:
            config = session.get(MemoryConfigModel, 1)

            if config:
                # Update existing
                if embedding_model is not None:
                    config.embedding_model = embedding_model
                if extraction_model is not None:
                    config.extraction_model = extraction_model
                config.updated_at = now
            else:
                # Create new
                config = MemoryConfigModel(
                    id=1,
                    embedding_model=embedding_model,
                    extraction_model=extraction_model,
                    updated_at=now,
                )

            session.add(config)
            session.commit()
            return True

    # -------------------------------------------------------------------------
    # MCP Server Operations
    # -------------------------------------------------------------------------

    def get_mcp_servers(self) -> List[MCPServerModel]:
        """Get all MCP servers from the database."""
        with self._session() as session:
            statement = select(MCPServerModel)
            servers = session.exec(statement).all()
            return servers

    def add_mcp_server(
        self,
        name: str,
        config: Dict[str, Any],
        enabled: bool = True,
    ) -> bool:
        """Add a new MCP server configuration."""
        now = datetime.now()
        with self._session() as session:
            if session.get(MCPServerModel, name):
                return False

            server = MCPServerModel(
                name=name,
                type=config.get("type", "stdio"),
                url=config.get("url"),
                headers=config.get("headers"),
                command=config.get("command"),
                args=config.get("args"),
                env=config.get("env"),
                enabled=enabled,
                created_at=now,
                updated_at=now,
            )
            session.add(server)
            session.commit()
            return True

    def update_mcp_server(
        self, name: str, config: Dict[str, Any] = None, enabled: bool = None
    ) -> bool:
        """Update an existing MCP server configuration."""
        with self._session() as session:
            server = session.get(MCPServerModel, name)
            if not server:
                return False

            if config:
                if "type" in config:
                    server.type = config["type"]
                if "url" in config:
                    server.url = config["url"]
                if "headers" in config:
                    server.headers = config["headers"]
                if "command" in config:
                    server.command = config["command"]
                if "args" in config:
                    server.args = config["args"]
                if "env" in config:
                    server.env = config["env"]

            if enabled is not None:
                server.enabled = enabled

            server.updated_at = datetime.now()
            session.add(server)
            session.commit()
            return True

    def remove_mcp_server(self, name: str) -> bool:
        """Remove an MCP server configuration."""
        with self._session() as session:
            server = session.get(MCPServerModel, name)
            if not server:
                return False
            session.delete(server)
            session.commit()
            return True

    def set_mcp_server_enabled(self, name: str, enabled: bool) -> bool:
        """Enable or disable an MCP server."""
        with self._session() as session:
            server = session.get(MCPServerModel, name)
            if not server:
                return False

            server.enabled = enabled
            server.updated_at = datetime.now()
            session.add(server)
            session.commit()
            return True

    # -------------------------------------------------------------------------
    # Cron Job Operations
    # -------------------------------------------------------------------------

    def list_cron_jobs(self, active_only: bool = False) -> List[CronJobModel]:
        """List all cron jobs, optionally filtered to active only."""
        with self._session() as session:
            statement = select(CronJobModel).order_by(CronJobModel.created_at.desc())
            if active_only:
                statement = statement.where(CronJobModel.active.is_(True))  # noqa: E712
            return session.exec(statement).all()

    def get_cron_job(self, job_id: int) -> Optional[CronJobModel]:
        """Get a cron job by ID."""
        with self._session() as session:
            return session.get(CronJobModel, job_id)

    def create_cron_job(
        self,
        name: str,
        cron_expr: str,
        prompt: str,
        active: bool = True,
        delivery_mode: str = "announce",
        model_override: Optional[str] = None,
    ) -> int:
        """Create a new cron job and return its ID."""
        now = datetime.now()
        job = CronJobModel(
            name=name,
            cron_expr=cron_expr,
            prompt=prompt,
            active=active,
            delivery_mode=delivery_mode,
            model_override=model_override,
            created_at=now,
            updated_at=now,
        )
        with self._session() as session:
            session.add(job)
            session.commit()
            session.refresh(job)
            return job.id

    def update_cron_job(self, job_id: int, **kwargs) -> bool:
        """Update a cron job's configuration fields."""
        with self._session() as session:
            job = session.get(CronJobModel, job_id)
            if not job:
                return False
            for key, value in kwargs.items():
                if hasattr(job, key) and key not in ("id", "created_at"):
                    setattr(job, key, value)
            job.updated_at = datetime.now()
            session.add(job)
            session.commit()
            return True

    def delete_cron_job(self, job_id: int) -> bool:
        """Delete a cron job by ID."""
        with self._session() as session:
            job = session.get(CronJobModel, job_id)
            if not job:
                return False
            session.delete(job)
            session.commit()
            return True

    def update_cron_job_run_state(
        self,
        job_id: int,
        last_run_at: Optional[datetime] = None,
        next_run_at: Optional[datetime] = None,
        last_result: Optional[str] = None,
        last_error: Optional[str] = None,
        retry_count: Optional[int] = None,
    ) -> bool:
        """Update cron job run metadata (used by scheduler)."""
        with self._session() as session:
            job = session.get(CronJobModel, job_id)
            if not job:
                return False
            if last_run_at is not None:
                job.last_run_at = last_run_at
            if next_run_at is not None:
                job.next_run_at = next_run_at
            if last_result is not None:
                job.last_result = last_result[:2000]
            if last_error is not None:
                job.last_error = last_error[:1000]
            if retry_count is not None:
                job.retry_count = retry_count
            job.updated_at = datetime.now()
            session.add(job)
            session.commit()
            return True

    # -------------------------------------------------------------------------
    # Cron Run History
    # -------------------------------------------------------------------------

    def create_cron_run(self, job_id: int, started_at: datetime) -> int:
        """Create a run history record, return its ID."""
        run = CronRunModel(job_id=job_id, started_at=started_at)
        with self._session() as session:
            session.add(run)
            session.commit()
            session.refresh(run)
            return run.id

    def finish_cron_run(
        self,
        run_id: int,
        status: str,
        result: Optional[str] = None,
        error: Optional[str] = None,
    ):
        """Mark a run as finished."""
        with self._session() as session:
            run = session.get(CronRunModel, run_id)
            if not run:
                return
            run.finished_at = datetime.now()
            run.status = status
            if result is not None:
                run.result = result[:2000]
            if error is not None:
                run.error = error[:1000]
            session.add(run)
            session.commit()

    def list_cron_runs(self, job_id: int, limit: int = 20) -> List[CronRunModel]:
        """List recent runs for a job."""
        with self._session() as session:
            statement = (
                select(CronRunModel)
                .where(CronRunModel.job_id == job_id)
                .order_by(CronRunModel.started_at.desc())
                .limit(limit)
            )
            return session.exec(statement).all()

    # -------------------------------------------------------------------------
    # API Key Operations
    # -------------------------------------------------------------------------

    def get_api_keys(self) -> Dict[str, str]:
        """Get all API keys as a dictionary {KEY: value}."""
        with self._session() as session:
            statement = select(ApiKeyModel)
            results = session.exec(statement).all()
            return {item.key: item.value for item in results}

    def save_api_key(self, key: str, value: str) -> bool:
        """Save or update an API key."""
        now = datetime.now()
        with self._session() as session:
            item = session.get(ApiKeyModel, key)
            if item:
                item.value = value
                item.updated_at = now
            else:
                item = ApiKeyModel(key=key, value=value, updated_at=now)
            session.add(item)
            session.commit()
            return True

    def delete_api_key(self, key: str) -> bool:
        """Delete an API key."""
        with self._session() as session:
            item = session.get(ApiKeyModel, key)
            if not item:
                return False
            session.delete(item)
            session.commit()
            return True


# Global database instance
_db_instance = None


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
