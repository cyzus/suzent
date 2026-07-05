"""Peer-retrievable file artifact registry."""

from __future__ import annotations

import mimetypes
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from suzent.logger import get_logger

logger = get_logger(__name__)

DEFAULT_PEER_FILE_TTL_SECONDS = 3600


class PeerFileArtifact(BaseModel):
    file_id: str
    path: Path
    name: str
    media_type: str
    size: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    producer: str = "unknown"

    def to_reference(self) -> dict:
        return {
            "id": self.file_id,
            "url": f"/nodes/peer-files/{self.file_id}",
            "name": self.name,
            "media_type": self.media_type,
            "size": self.size,
            "expires_at": self.expires_at.isoformat().replace("+00:00", "Z"),
        }


class PeerFileRegistry:
    """Short-lived in-memory registry of files intentionally exposed to peers."""

    def __init__(self) -> None:
        self._artifacts: dict[str, PeerFileArtifact] = {}

    def register(
        self,
        path: str | Path,
        *,
        producer: str = "unknown",
        name: str | None = None,
        media_type: str | None = None,
        ttl_seconds: int = DEFAULT_PEER_FILE_TTL_SECONDS,
    ) -> PeerFileArtifact:
        resolved = Path(path).expanduser().resolve(strict=True)
        if not resolved.is_file():
            raise ValueError("Peer artifact path is not a file")

        self.prune_expired()
        file_id = self._new_file_id()
        guessed_type = mimetypes.guess_type(resolved.name)[0]
        artifact = PeerFileArtifact(
            file_id=file_id,
            path=resolved,
            name=name or resolved.name,
            media_type=media_type or guessed_type or "application/octet-stream",
            size=resolved.stat().st_size,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
            producer=producer,
        )
        self._artifacts[file_id] = artifact
        logger.debug("Registered peer file artifact {}", file_id)
        return artifact

    def get(self, file_id: str) -> PeerFileArtifact | None:
        artifact = self._artifacts.get(file_id)
        if artifact is None:
            return None
        if artifact.expires_at <= datetime.now(timezone.utc):
            self._artifacts.pop(file_id, None)
            return None
        if not artifact.path.exists() or not artifact.path.is_file():
            self._artifacts.pop(file_id, None)
            return None
        return artifact

    def prune_expired(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [
            file_id
            for file_id, artifact in self._artifacts.items()
            if artifact.expires_at <= now
        ]
        for file_id in expired:
            self._artifacts.pop(file_id, None)

    def _new_file_id(self) -> str:
        while True:
            file_id = f"pf_{secrets.token_urlsafe(24)}"
            if file_id not in self._artifacts:
                return file_id
