from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy import text
from sqlmodel import select

from .models import (
    ChatModel,
    ProjectModel,
)


class ProjectOperationsMixin:
    DEFAULT_PROJECT_SLUG = "default"
    DEFAULT_PROJECT_NAME = "Default"
    SOCIAL_PROJECT_SLUG = "social"
    SOCIAL_PROJECT_NAME = "Social"
    SYSTEM_PROJECT_SLUGS = {"default", "social"}

    # Platforms that route a chat into the ``social`` project by default.
    # Internal platforms like ``subagent`` (lives with parent) and ``cron``
    # (scheduled task runner) are deliberately excluded — subagents inherit
    # their parent's project explicitly and cron chats stay in default.
    SOCIAL_PLATFORMS = {"telegram", "slack", "discord", "wechat", "whatsapp"}

    @classmethod
    def _is_social_platform(cls, config: Optional[Dict[str, Any]]) -> bool:
        if not config:
            return False
        platform = config.get("platform")
        if not platform:
            return False
        return platform.lower() in cls.SOCIAL_PLATFORMS

    def _ensure_default_project(self) -> None:
        """Create system projects (default + social) and backfill chats.

        - ``default``: catches chats with no platform set.
        - ``social``: catches chats with ``config.platform`` set (Telegram, etc.).

        Both system projects are created on first launch and any unassigned
        chats are routed to the appropriate one. Existing chats already in
        ``default`` that have a ``config.platform`` set are also moved to
        ``social`` (one-time migration).
        """
        from suzent.logger import logger

        with self._session() as session:
            # System projects
            default = session.exec(
                select(ProjectModel).where(
                    ProjectModel.slug == self.DEFAULT_PROJECT_SLUG
                )
            ).first()
            if not default:
                default = ProjectModel(
                    name=self.DEFAULT_PROJECT_NAME,
                    slug=self.DEFAULT_PROJECT_SLUG,
                )
                session.add(default)
                session.flush()
                logger.info(
                    "Created default project (slug='{}')", self.DEFAULT_PROJECT_SLUG
                )

            social = session.exec(
                select(ProjectModel).where(
                    ProjectModel.slug == self.SOCIAL_PROJECT_SLUG
                )
            ).first()
            if not social:
                social = ProjectModel(
                    name=self.SOCIAL_PROJECT_NAME,
                    slug=self.SOCIAL_PROJECT_SLUG,
                )
                session.add(social)
                session.flush()
                logger.info(
                    "Created social project (slug='{}')", self.SOCIAL_PROJECT_SLUG
                )

            # Backfill unassigned chats: route by config.platform presence
            unassigned = session.exec(
                select(ChatModel).where(ChatModel.project_id == None)  # noqa: E711
            ).all()
            backfilled_default = 0
            backfilled_social = 0
            for chat in unassigned:
                if self._is_social_platform(chat.config):
                    chat.project_id = social.id
                    backfilled_social += 1
                else:
                    chat.project_id = default.id
                    backfilled_default += 1
            if backfilled_default:
                logger.info(
                    "Backfilled {} chat(s) to default project", backfilled_default
                )
            if backfilled_social:
                logger.info(
                    "Backfilled {} chat(s) to social project", backfilled_social
                )

            # One-time migration: chats already in default that have a social
            # platform tag were placed there before the social project existed.
            # Subagent/cron chats are excluded — they stay where they were.
            misplaced = session.exec(
                select(ChatModel).where(ChatModel.project_id == default.id)
            ).all()
            moved_to_social = 0
            for chat in misplaced:
                if self._is_social_platform(chat.config):
                    chat.project_id = social.id
                    moved_to_social += 1

            # One-time rescue: subagent/cron chats that landed in social in a
            # prior migration step need to move out. Subagents follow their
            # parent's project (falling back to default if parent is unknown);
            # cron chats go to default.
            misclassified = session.exec(
                select(ChatModel).where(ChatModel.project_id == social.id)
            ).all()
            rescued_subagent = 0
            rescued_cron = 0
            for chat in misclassified:
                if not chat.config:
                    continue
                platform = (chat.config.get("platform") or "").lower()
                if platform == "subagent":
                    parent_id = chat.config.get("parent_chat_id")
                    target_project_id = default.id
                    if parent_id:
                        parent = session.get(ChatModel, parent_id)
                        if parent and parent.project_id:
                            target_project_id = parent.project_id
                    chat.project_id = target_project_id
                    rescued_subagent += 1
                elif platform == "cron":
                    chat.project_id = default.id
                    rescued_cron += 1
            if rescued_subagent:
                logger.info(
                    "Moved {} subagent chat(s) out of social into parent project",
                    rescued_subagent,
                )
            if rescued_cron:
                logger.info(
                    "Moved {} cron chat(s) out of social into default", rescued_cron
                )
            if moved_to_social:
                logger.info(
                    "Migrated {} platform-tagged chat(s) from default to social",
                    moved_to_social,
                )

            session.commit()

    def create_project(self, name: str, slug: str) -> str:
        """Create a new project and return its id."""
        project = ProjectModel(name=name, slug=slug)
        with self._session() as session:
            session.add(project)
            session.commit()
            session.refresh(project)
            return project.id

    def get_project(self, project_id: str) -> Optional[ProjectModel]:
        """Return a project by id, or None if not found."""
        with self._session() as session:
            return session.get(ProjectModel, project_id)

    def get_project_by_slug(self, slug: str) -> Optional[ProjectModel]:
        """Return a project by slug, or None if not found."""
        with self._session() as session:
            return session.exec(
                select(ProjectModel).where(ProjectModel.slug == slug)
            ).first()

    def list_projects(self, include_archived: bool = False) -> List[ProjectModel]:
        """Return all projects ordered by creation time."""
        with self._session() as session:
            stmt = select(ProjectModel)
            if not include_archived:
                stmt = stmt.where(ProjectModel.archived == False)  # noqa: E712
            stmt = stmt.order_by(ProjectModel.created_at)
            return list(session.exec(stmt).all())

    @staticmethod
    def _is_subagent_child(chat: ChatModel, parent_chat_ids: set[str]) -> bool:
        """Return whether a chat is a direct subagent child of one of the parents."""
        config = chat.config or {}
        return (
            config.get("platform") == "subagent"
            and config.get("parent_chat_id") in parent_chat_ids
        )

    def get_subagent_chat_ids_for_parent_chat(self, chat_id: str) -> List[str]:
        """Return direct subagent chat ids whose parent is the given chat."""
        with self._session() as session:
            rows = session.exec(
                select(ChatModel.id).where(
                    text(
                        "json_extract(config, '$.platform') = 'subagent'"
                        " AND json_extract(config, '$.parent_chat_id') = :parent_id"
                    ).bindparams(parent_id=chat_id)
                )
            ).all()
            return list(rows)

    def list_subagent_task_records(
        self, parent_chat_id: Optional[str] = None
    ) -> List[dict]:
        """Return persisted subagent task records reconstructed from chat rows.

        Subagent runtime tasks are in memory, but their isolated chat rows are
        persisted. This lets the UI show historical subagents after restart and
        when the currently selected chat is the subagent chat itself.
        """
        with self._session() as session:
            chats = session.exec(select(ChatModel)).all()

        records = []
        for chat in chats:
            config = chat.config or {}
            if config.get("platform") != "subagent":
                continue

            task_id = config.get("subagent_task_id")
            if not task_id and chat.id.startswith("subagent-"):
                task_id = chat.id[len("subagent-") :]

            parent_id = config.get("parent_chat_id")

            if parent_chat_id and parent_chat_id not in {parent_id, chat.id}:
                continue

            description = chat.title
            prefix = "Sub-agent:"
            if description.startswith(prefix):
                description = description[len(prefix) :].strip()

            records.append(
                {
                    "task_id": task_id,
                    "parent_chat_id": parent_id or "",
                    "chat_id": chat.id,
                    "description": description,
                    "tools_allowed": config.get("tools") or [],
                    "status": "completed",
                    "result_summary": None,
                    "error": None,
                    "model_override": config.get("model"),
                    "started_at": chat.created_at.isoformat()
                    if chat.created_at
                    else None,
                    "finished_at": chat.last_result_at.isoformat()
                    if chat.last_result_at
                    else chat.updated_at.isoformat()
                    if chat.updated_at
                    else None,
                    "inherit_context": config.get("inherit_context", False),
                    "isolation": config.get("isolation", "none"),
                    "worktree_path": config.get("worktree_path"),
                    "worktree_branch": config.get("worktree_branch"),
                }
            )

        return sorted(
            records,
            key=lambda record: record.get("finished_at")
            or record.get("started_at")
            or "",
            reverse=True,
        )

    def link_chat_to_project(self, chat_id: str, project_id: str) -> bool:
        """Move a chat and its direct subagent chats to a different project."""
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return False
            chats = session.exec(select(ChatModel)).all()
            moved_chats = [
                candidate
                for candidate in chats
                if candidate.id == chat_id
                or self._is_subagent_child(candidate, {chat_id})
            ]
            for moved_chat in moved_chats:
                moved_chat.project_id = project_id
                session.add(moved_chat)
            session.commit()
            return True

    def move_all_chats(self, from_project_id: str, to_project_id: str) -> int:
        """Reassign every chat from one project plus their subagents."""
        with self._session() as session:
            project_chats = session.exec(
                select(ChatModel).where(ChatModel.project_id == from_project_id)
            ).all()
            project_chat_ids = {chat.id for chat in project_chats}
            all_chats = session.exec(select(ChatModel)).all()
            moved_chats = [
                chat
                for chat in all_chats
                if chat.id in project_chat_ids
                or self._is_subagent_child(chat, project_chat_ids)
            ]
            for chat in moved_chats:
                chat.project_id = to_project_id
                session.add(chat)
            session.commit()
            return len(moved_chats)

    def get_chat_ids_in_project(self, project_id: str) -> List[str]:
        """Return chat ids assigned to a project plus direct subagents of those chats."""
        with self._session() as session:
            project_chats = session.exec(
                select(ChatModel).where(ChatModel.project_id == project_id)
            ).all()
            project_chat_ids = {chat.id for chat in project_chats}
            all_chats = session.exec(select(ChatModel)).all()
            return [
                chat.id
                for chat in all_chats
                if chat.id in project_chat_ids
                or self._is_subagent_child(chat, project_chat_ids)
            ]

    def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        archived: Optional[bool] = None,
    ) -> Optional[ProjectModel]:
        """Update a project's name and/or archived flag."""
        with self._session() as session:
            project = session.get(ProjectModel, project_id)
            if not project:
                return None
            if name is not None:
                project.name = name
            if archived is not None:
                project.archived = archived
            session.add(project)
            session.commit()
            session.refresh(project)
            return project

    def delete_project(self, project_id: str) -> tuple[bool, str]:
        """Delete a project. Refuses to delete system projects or non-empty projects.

        Returns ``(success, error_message)``. On success error_message is empty.
        """
        with self._session() as session:
            project = session.get(ProjectModel, project_id)
            if not project:
                return False, "Project not found"
            if project.slug in self.SYSTEM_PROJECT_SLUGS:
                return False, f"Cannot delete system project '{project.slug}'"
            chat_count = session.exec(
                select(func.count())
                .select_from(ChatModel)
                .where(ChatModel.project_id == project_id)
            ).one()
            if chat_count > 0:
                return (
                    False,
                    f"Project has {chat_count} chat(s); move them out first",
                )
            session.delete(project)
            session.commit()
            return True, ""

    def get_chat_project_id(self, chat_id: str) -> Optional[str]:
        """Return the project_id for a chat, or None if not found."""
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            return chat.project_id if chat else None

    def get_chat_project_slug(self, chat_id: str) -> str:
        """Return the project slug for a chat, falling back to the default project slug.

        Used by path resolution to map a chat to its on-disk project directory.
        """
        project_id = self.get_chat_project_id(chat_id)
        if project_id:
            project = self.get_project(project_id)
            if project:
                return project.slug
        return self.DEFAULT_PROJECT_SLUG

    def get_project_dir(self, chat_id: str) -> Path:
        """Host path for the project a chat belongs to.

        This directory is the agent's cwd and contains all project-scoped state:
        heartbeat.md, context.md, plan.md, uploads/, images/, plus any files
        the agent creates. Shared across all chats in the project.
        """
        from suzent.config import CONFIG

        slug = self.get_chat_project_slug(chat_id)
        return Path(CONFIG.sandbox_data_path) / "projects" / slug

    def find_heartbeat_enabled_chat_in_project(
        self,
        project_id: str,
        exclude_chat_id: Optional[str] = None,
        exclude_chat_ids: Optional[set[str]] = None,
    ) -> Optional["ChatModel"]:
        """Return the chat in this project that already has heartbeat enabled.

        Used to enforce one-heartbeat-per-project. Returns None if no other chat
        in the project has heartbeat enabled.
        """
        excluded = set(exclude_chat_ids or set())
        if exclude_chat_id is not None:
            excluded.add(exclude_chat_id)

        with self._session() as session:
            stmt = (
                select(ChatModel)
                .where(ChatModel.project_id == project_id)
                .where(text("json_extract(config, '$.heartbeat_enabled') = 1"))
            )
            if excluded:
                stmt = stmt.where(ChatModel.id.not_in(excluded))
            return session.exec(stmt).first()

    # -------------------------------------------------------------------------
    # Chat Operations
    # -------------------------------------------------------------------------
