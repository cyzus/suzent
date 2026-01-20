"""
Database layer for chat persistence using SQLModel.

Provides a clean, type-safe interface for all database operations.
"""

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import selectinload
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

    plans: List["PlanModel"] = Relationship(
        back_populates="chat",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


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
    command: Optional[str] = None
    args: Optional[list] = Field(default=None, sa_column=Column(JSON))
    env: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    enabled: bool = Field(default=True)
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")


# -----------------------------------------------------------------------------
# Database Management
# -----------------------------------------------------------------------------


class ChatDatabase:
    """Handles database operations for chat persistence using SQLModel."""

    def __init__(self, db_path: str = "chats.db"):
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
    ) -> str:
        """Create a new chat and return its ID."""
        now = datetime.now()
        chat_id = str(uuid.uuid4())
        chat = ChatModel(
            id=chat_id,
            title=title,
            created_at=now,
            updated_at=now,
            config=config,
            messages=messages or [],
            agent_state=agent_state,
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

            if should_update_timestamp:
                chat.updated_at = datetime.now()

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
                # ChatModel.messages is structured JSON (list/dict), searching simple constraints textually
                # might be tricky depending on DB. SQLite JSON is just text usually.
                statement = statement.where(
                    (
                        ChatModel.title.contains(search)
                        # Note: Filtering on JSON column needs cast or specific functions usually,
                        # but pure text search on JSON column works in SQLite if treated as text.
                        # SQLModel usually maps specialized types.
                        # If this fails, we might need func.cast(ChatModel.messages, String).contains(search)
                    )
                )

            statement = statement.offset(offset).limit(limit)
            chats = session.exec(statement).all()

            results = []
            for chat in chats:
                messages = chat.messages or []
                last_message = None
                if messages:
                    last_msg = messages[-1]
                    last_message = last_msg.get("content", "")[:100]
                    if len(last_msg.get("content", "")) > 100:
                        last_message += "..."

                results.append(
                    ChatSummaryModel(
                        id=chat.id,
                        title=chat.title,
                        createdAt=chat.created_at.isoformat(),
                        updatedAt=chat.updated_at.isoformat(),
                        messageCount=len(messages),
                        lastMessage=last_message,
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


# Global database instance
_db_instance = None


def get_database() -> ChatDatabase:
    """Get the global database instance."""
    global _db_instance
    if _db_instance is None:
        db_path = os.getenv("CHATS_DB_PATH", "chats.db")
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
