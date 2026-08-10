"""Persistence operations for durable cross-session agent messages."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, or_, text
from sqlmodel import select

from .models import AgentInboxMessageModel, ChatModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _message_record(message: AgentInboxMessageModel) -> dict[str, Any]:
    return {
        "message_id": message.message_id,
        "transport": message.transport,
        "destination_peer_id": message.destination_peer_id,
        "sender_chat_id": message.sender_chat_id,
        "target_chat_id": message.target_chat_id,
        "kind": message.kind,
        "content": message.content,
        "payload": dict(message.payload or {}),
        "status": message.status,
        "attempts": message.attempts,
        "max_attempts": message.max_attempts,
        "available_at": message.available_at.isoformat(),
        "lease_owner": message.lease_owner,
        "lease_until": message.lease_until.isoformat() if message.lease_until else None,
        "created_at": message.created_at.isoformat(),
        "updated_at": message.updated_at.isoformat(),
        "delivered_at": message.delivered_at.isoformat()
        if message.delivered_at
        else None,
        "last_error": message.last_error,
    }


class AgentInboxOperationsMixin:
    def enqueue_agent_message(
        self,
        *,
        message_id: str,
        target_chat_id: str,
        content: str,
        sender_chat_id: Optional[str] = None,
        transport: str = "local",
        destination_peer_id: Optional[str] = None,
        kind: str = "agent_message",
        payload: Optional[dict[str, Any]] = None,
        max_attempts: int = 5,
    ) -> tuple[dict[str, Any], bool]:
        """Insert one message idempotently and return ``(record, created)``."""
        if not message_id.strip():
            raise ValueError("message_id is required")
        if not content.strip():
            raise ValueError("message content is required")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if transport not in {"local", "suzent_peer"}:
            raise ValueError(f"Unsupported agent message transport '{transport}'")
        if transport == "suzent_peer" and not destination_peer_id:
            raise ValueError("destination_peer_id is required for peer delivery")

        now = _utcnow()
        with self._session() as session:
            if transport == "local" and session.get(ChatModel, target_chat_id) is None:
                raise ValueError(f"Target agent '{target_chat_id}' does not exist")

            existing = session.get(AgentInboxMessageModel, message_id)
            if existing is not None:
                if (
                    existing.target_chat_id != target_chat_id
                    or existing.sender_chat_id != sender_chat_id
                    or existing.content != content
                    or existing.transport != transport
                    or existing.destination_peer_id != destination_peer_id
                    or existing.kind != kind
                    or dict(existing.payload or {}) != dict(payload or {})
                ):
                    raise ValueError(
                        f"Inbox message ID '{message_id}' is already used by another payload"
                    )
                return _message_record(existing), False

            message = AgentInboxMessageModel(
                message_id=message_id,
                transport=transport,
                destination_peer_id=destination_peer_id,
                sender_chat_id=sender_chat_id,
                target_chat_id=target_chat_id,
                kind=kind,
                content=content,
                payload=dict(payload or {}),
                status="pending",
                max_attempts=max_attempts,
                available_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(message)
            session.commit()
            session.refresh(message)
            return _message_record(message), True

    def claim_next_agent_message(
        self, *, worker_id: str, lease_seconds: int = 180
    ) -> Optional[dict[str, Any]]:
        """Atomically lease the oldest eligible message for one worker."""
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be at least 1")

        now = _utcnow()
        with self._session() as session:
            # SQLite has no SKIP LOCKED. BEGIN IMMEDIATE serializes the short
            # select-and-update claim section across server processes.
            session.exec(text("BEGIN IMMEDIATE"))

            exhausted = session.exec(
                select(AgentInboxMessageModel).where(
                    AgentInboxMessageModel.status == "processing",
                    AgentInboxMessageModel.lease_until <= now,
                    AgentInboxMessageModel.attempts
                    >= AgentInboxMessageModel.max_attempts,
                )
            ).all()
            for message in exhausted:
                message.status = "failed"
                message.lease_owner = None
                message.lease_until = None
                message.last_error = message.last_error or "Delivery lease expired"
                message.updated_at = now
                session.add(message)

            eligible = or_(
                and_(
                    AgentInboxMessageModel.status == "pending",
                    AgentInboxMessageModel.available_at <= now,
                ),
                and_(
                    AgentInboxMessageModel.status == "processing",
                    AgentInboxMessageModel.lease_until <= now,
                ),
            )
            active_targets = session.exec(
                select(AgentInboxMessageModel.target_chat_id).where(
                    AgentInboxMessageModel.status == "processing",
                    AgentInboxMessageModel.lease_until > now,
                )
            ).all()
            message = session.exec(
                select(AgentInboxMessageModel)
                .where(
                    eligible,
                    AgentInboxMessageModel.attempts
                    < AgentInboxMessageModel.max_attempts,
                    AgentInboxMessageModel.target_chat_id.notin_(active_targets),
                )
                .order_by(AgentInboxMessageModel.created_at.asc())
                .limit(1)
            ).first()
            if message is None:
                session.commit()
                return None

            message.status = "processing"
            message.attempts += 1
            message.lease_owner = worker_id
            message.lease_until = now + timedelta(seconds=lease_seconds)
            message.updated_at = now
            session.add(message)
            session.commit()
            session.refresh(message)
            return _message_record(message)

    def acknowledge_agent_message(self, message_id: str, *, worker_id: str) -> bool:
        """Mark a message delivered when the caller owns its current lease."""
        now = _utcnow()
        with self._session() as session:
            message = session.get(AgentInboxMessageModel, message_id)
            if (
                message is None
                or message.status != "processing"
                or message.lease_owner != worker_id
            ):
                return False
            message.status = "delivered"
            message.delivered_at = now
            message.updated_at = now
            message.lease_owner = None
            message.lease_until = None
            message.last_error = None
            session.add(message)
            session.commit()
            return True

    def retry_agent_message(
        self,
        message_id: str,
        *,
        worker_id: str,
        error: str,
        retry_delay_seconds: int,
    ) -> bool:
        """Release a failed lease for retry or mark it permanently failed."""
        now = _utcnow()
        with self._session() as session:
            message = session.get(AgentInboxMessageModel, message_id)
            if (
                message is None
                or message.status != "processing"
                or message.lease_owner != worker_id
            ):
                return False

            message.status = (
                "failed" if message.attempts >= message.max_attempts else "pending"
            )
            message.available_at = now + timedelta(seconds=max(0, retry_delay_seconds))
            message.updated_at = now
            message.lease_owner = None
            message.lease_until = None
            message.last_error = error[:2000]
            session.add(message)
            session.commit()
            return True

    def list_agent_messages(
        self,
        *,
        target_chat_id: Optional[str] = None,
        transport: Optional[str] = None,
        destination_peer_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return a bounded newest-first inbox audit view."""
        statement = select(AgentInboxMessageModel)
        if target_chat_id:
            statement = statement.where(
                AgentInboxMessageModel.target_chat_id == target_chat_id
            )
        if transport:
            statement = statement.where(AgentInboxMessageModel.transport == transport)
        if destination_peer_id:
            statement = statement.where(
                AgentInboxMessageModel.destination_peer_id == destination_peer_id
            )
        if status:
            statement = statement.where(AgentInboxMessageModel.status == status)
        statement = statement.order_by(AgentInboxMessageModel.created_at.desc()).limit(
            min(max(limit, 1), 200)
        )
        with self._session() as session:
            return [
                _message_record(message) for message in session.exec(statement).all()
            ]
