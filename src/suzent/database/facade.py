"""Public database facade assembled from focused persistence mixins."""

from .base import ChatDatabaseBase
from .chats import ChatOperationsMixin
from .cron import CronOperationsMixin
from .goals import GoalOperationsMixin
from .migrations import DatabaseMigrationMixin
from .postprocess import PostprocessOperationsMixin
from .projects import ProjectOperationsMixin
from .settings import SettingsOperationsMixin
from .tasks import TaskOperationsMixin


class ChatDatabase(
    DatabaseMigrationMixin,
    ProjectOperationsMixin,
    GoalOperationsMixin,
    TaskOperationsMixin,
    ChatOperationsMixin,
    PostprocessOperationsMixin,
    SettingsOperationsMixin,
    CronOperationsMixin,
    ChatDatabaseBase,
):
    """Handles database operations for chat persistence using SQLModel."""
