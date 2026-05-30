"""Public database facade assembled from focused persistence mixins."""

from .base import ChatDatabaseBase
from .chats import ChatOperationsMixin
from .cron import CronOperationsMixin
from .migrations import DatabaseMigrationMixin
from .plans import PlanOperationsMixin
from .postprocess import PostprocessOperationsMixin
from .projects import ProjectOperationsMixin
from .settings import SettingsOperationsMixin


class ChatDatabase(
    DatabaseMigrationMixin,
    ProjectOperationsMixin,
    ChatOperationsMixin,
    PostprocessOperationsMixin,
    PlanOperationsMixin,
    SettingsOperationsMixin,
    CronOperationsMixin,
    ChatDatabaseBase,
):
    """Handles database operations for chat persistence using SQLModel."""
