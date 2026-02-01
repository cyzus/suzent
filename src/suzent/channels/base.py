"""
Base classes and data models for social messaging channels.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import time
from pathlib import Path
import asyncio


@dataclass
class UnifiedMessage:
    """
    A standardized message format for all social platforms.
    """

    id: str
    content: str
    sender_id: str
    sender_name: str
    platform: str
    timestamp: float = field(default_factory=time.time)
    thread_id: Optional[str] = None
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def get_chat_id(self) -> str:
        """
        Generate a unique chat ID for Suzent based on platform and sender.
        Format: "platform:sender_id"
        """
        return f"{self.platform}:{self.sender_id}"


class SocialChannel(ABC):
    """
    Abstract Base Class for social platform drivers.
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.on_message: Optional[Callable[[UnifiedMessage], Any]] = None

    @abstractmethod
    async def connect(self):
        """authenticate and establish connection/polling."""
        pass

    @abstractmethod
    async def disconnect(self):
        """Clean shutdown."""
        pass

    @abstractmethod
    async def send_message(self, target_id: str, content: str, **kwargs) -> bool:
        """Send text message."""
        pass

    @abstractmethod
    async def send_file(
        self, target_id: str, file_path: str, caption: str = None, **kwargs
    ) -> bool:
        """Send a file."""
        pass

    async def _invoke_callback(self, message: UnifiedMessage):
        """Helper to safely invoke the registered callback (sync or async)."""
        if self.on_message:
            if asyncio.iscoroutinefunction(self.on_message):
                await self.on_message(message)
            else:
                self.on_message(message)

    def _get_upload_path(self, filename: str) -> Path:
        """Get a standardized temp path for uploads."""
        tmp_dir = Path(tempfile.gettempdir()) / "suzent_uploads"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        return tmp_dir / filename

    def set_callback(self, func: Callable[[UnifiedMessage], Any]):
        """Register the listener for incoming messages."""
        self.on_message = func
