"""Public database facade assembled from focused persistence mixins."""

from .base import ChatDatabaseBase
from .chat_status import ChatStatusOperationsMixin
from .chats import ChatOperationsMixin
from .cron import CronOperationsMixin
from .goals import GoalOperationsMixin
from .inbox import AgentInboxOperationsMixin
from .memory_recalls import MemoryRecallOperationsMixin
from .migrations import DatabaseMigrationMixin
from .notifications import BackgroundNotificationOperationsMixin
from .postprocess import PostprocessOperationsMixin
from .projects import ProjectOperationsMixin
from .search import ChatSearchMixin
from .settings import SettingsOperationsMixin
from .suggestions import InputSuggestionOperationsMixin
from .tasks import TaskOperationsMixin


class ChatDatabase(
    DatabaseMigrationMixin,
    AgentInboxOperationsMixin,
    ProjectOperationsMixin,
    GoalOperationsMixin,
    TaskOperationsMixin,
    ChatOperationsMixin,
    ChatSearchMixin,
    PostprocessOperationsMixin,
    SettingsOperationsMixin,
    InputSuggestionOperationsMixin,
    ChatStatusOperationsMixin,
    MemoryRecallOperationsMixin,
    BackgroundNotificationOperationsMixin,
    CronOperationsMixin,
    ChatDatabaseBase,
):
    """Handles database operations for chat persistence using SQLModel."""
