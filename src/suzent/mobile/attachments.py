"""Uploads a paired device may reference when it sends a message.

A device names its attachments by the ids this registry issued, never by path:
a project's uploads directory is shared by every chat in the project, and a
device scoped to one of them must not be able to point the agent at a file
another chat put there.
"""

from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass

ATTACHMENT_TTL_SECONDS = 6 * 60 * 60
MAX_ISSUED_ATTACHMENTS = 1000


@dataclass(frozen=True)
class IssuedAttachment:
    device_id: str
    chat_id: str
    metadata: dict
    issued_at: float


class AttachmentRegistry:
    def __init__(self, ttl: float = ATTACHMENT_TTL_SECONDS) -> None:
        self._ttl = ttl
        self._issued: OrderedDict[str, IssuedAttachment] = OrderedDict()

    def issue(self, device_id: str, chat_id: str, metadata: dict) -> str:
        self._expire()
        attachment_id = uuid.uuid4().hex
        self._issued[attachment_id] = IssuedAttachment(
            device_id, chat_id, metadata, time.monotonic()
        )
        while len(self._issued) > MAX_ISSUED_ATTACHMENTS:
            self._issued.popitem(last=False)
        return attachment_id

    def resolve(
        self, device_id: str, chat_id: str, attachment_ids: list[str]
    ) -> list[dict] | None:
        """The issued metadata, or None when any id is unknown to this device and chat."""
        self._expire()
        resolved: list[dict] = []
        for attachment_id in attachment_ids:
            issued = self._issued.get(attachment_id)
            if issued is None or (issued.device_id, issued.chat_id) != (
                device_id,
                chat_id,
            ):
                return None
            resolved.append(issued.metadata)
        return resolved

    def _expire(self) -> None:
        cutoff = time.monotonic() - self._ttl
        while self._issued:
            oldest = next(iter(self._issued.values()))
            if oldest.issued_at >= cutoff:
                return
            self._issued.popitem(last=False)


attachment_registry = AttachmentRegistry()
