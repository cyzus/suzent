"""Persistence operations for Mailbox items and dynamic routing rules."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from sqlmodel import Session, and_, col, delete, func, or_, select

from .models import AgentInboxMessageModel, MailboxItemModel, MailboxRuleModel


# How long the Mailbox keeps events. Unread notifications and events still
# waiting for their digest are kept until they are read or sent.
MAILBOX_RETENTION_DAYS = 30


def _prune_old_items(session: Session, now: datetime) -> None:
    session.exec(
        delete(MailboxItemModel).where(
            MailboxItemModel.created_at < now - timedelta(days=MAILBOX_RETENTION_DAYS),
            MailboxItemModel.route_status != "queued",
            or_(
                MailboxItemModel.route_status != "notified",
                col(MailboxItemModel.read_at).is_not(None),
            ),
        )
    )


class MailboxOperationsMixin:
    def create_mailbox_item(
        self,
        *,
        source_kind: str = "webhook",
        source_name: str = "webhook",
        event_type: str = "event",
        signature: str,
        summary: str,
        headers_json: str = "{}",
        payload: str = "",
        route_status: str = "routed",
        target_chat_id: Optional[str] = None,
        target_label: Optional[str] = None,
        rule_origin: str = "learned",
        reason: Optional[str] = None,
        inbox_message_id: Optional[str] = None,
        rule_id: Optional[int] = None,
        spooled_at: Optional[str] = None,
    ) -> MailboxItemModel:
        now = datetime.now()
        with self._session() as session:
            item = MailboxItemModel(
                source_kind=source_kind,
                source_name=source_name,
                event_type=event_type,
                signature=signature,
                summary=summary,
                headers_json=headers_json,
                payload=payload,
                route_status=route_status,
                target_chat_id=target_chat_id,
                target_label=target_label,
                rule_origin=rule_origin,
                reason=reason,
                inbox_message_id=inbox_message_id,
                rule_id=rule_id,
                spooled_at=spooled_at,
                created_at=now,
            )
            session.add(item)
            _prune_old_items(session, now)
            session.commit()
            session.refresh(item)
            return item

    def list_mailbox_items(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        route_status: Optional[str] = None,
        source_kind: Optional[str] = None,
        unread_only: bool = False,
    ) -> List[MailboxItemModel]:
        """Items newest first.

        A routed item whose agent delivery has since failed counts as an
        ``error``, as the Mailbox shows it; ``unread_only`` keeps the
        notifications the user hasn't seen.
        """
        with self._session() as session:
            stmt = select(MailboxItemModel)
            failed = select(AgentInboxMessageModel.message_id).where(
                AgentInboxMessageModel.status == "failed"
            )
            delivery_failed = and_(
                MailboxItemModel.route_status == "routed",
                col(MailboxItemModel.inbox_message_id).in_(failed),
            )
            if route_status == "error":
                stmt = stmt.where(
                    or_(MailboxItemModel.route_status == "error", delivery_failed)
                )
            elif route_status == "routed":
                stmt = stmt.where(
                    MailboxItemModel.route_status == "routed",
                    or_(
                        col(MailboxItemModel.inbox_message_id).is_(None),
                        col(MailboxItemModel.inbox_message_id).not_in(failed),
                    ),
                )
            elif route_status:
                stmt = stmt.where(MailboxItemModel.route_status == route_status)
            if unread_only:
                stmt = stmt.where(
                    MailboxItemModel.route_status == "notified",
                    col(MailboxItemModel.read_at).is_(None),
                )
            if source_kind:
                stmt = stmt.where(MailboxItemModel.source_kind == source_kind)
            stmt = stmt.order_by(MailboxItemModel.id.desc()).offset(offset).limit(limit)
            return list(session.exec(stmt).all())

    def count_mailbox_items(self) -> dict[str, int]:
        """Item counts per route status."""
        with self._session() as session:
            rows = session.exec(
                select(MailboxItemModel.route_status, func.count()).group_by(
                    MailboxItemModel.route_status
                )
            ).all()
            return {status: count for status, count in rows}

    def count_unread_mailbox_notifications(self) -> int:
        """Notifications the user has not seen yet."""
        with self._session() as session:
            return session.exec(
                select(func.count()).where(
                    MailboxItemModel.route_status == "notified",
                    MailboxItemModel.read_at.is_(None),
                )
            ).one()

    def mark_mailbox_notifications_read(
        self, item_ids: Optional[List[int]] = None
    ) -> int:
        """Mark the given notifications read, or all of them; returns how many changed."""
        with self._session() as session:
            stmt = select(MailboxItemModel).where(
                MailboxItemModel.route_status == "notified",
                MailboxItemModel.read_at.is_(None),
            )
            if item_ids is not None:
                stmt = stmt.where(MailboxItemModel.id.in_(item_ids))
            items = session.exec(stmt).all()
            now = datetime.now()
            for item in items:
                item.read_at = now
                session.add(item)
            session.commit()
            return len(items)

    def get_mailbox_item(self, item_id: int) -> Optional[MailboxItemModel]:
        with self._session() as session:
            return session.get(MailboxItemModel, item_id)

    def update_mailbox_item(self, item_id: int, **kwargs) -> Optional[MailboxItemModel]:
        with self._session() as session:
            item = session.get(MailboxItemModel, item_id)
            if item is None:
                return None
            for k, v in kwargs.items():
                if hasattr(item, k):
                    setattr(item, k, v)
            session.add(item)
            session.commit()
            session.refresh(item)
            return item

    def delete_mailbox_item(self, item_id: int) -> bool:
        with self._session() as session:
            item = session.get(MailboxItemModel, item_id)
            if item is None:
                return False
            session.delete(item)
            session.commit()
            return True

    def list_mailbox_rules(self) -> List[MailboxRuleModel]:
        with self._session() as session:
            stmt = select(MailboxRuleModel).order_by(
                MailboxRuleModel.origin.desc(), MailboxRuleModel.updated_at.desc()
            )
            return list(session.exec(stmt).all())

    def get_mailbox_rule(self, rule_id: int) -> Optional[MailboxRuleModel]:
        with self._session() as session:
            return session.get(MailboxRuleModel, rule_id)

    def get_mailbox_rule_by_signature(
        self, signature: str
    ) -> Optional[MailboxRuleModel]:
        with self._session() as session:
            stmt = select(MailboxRuleModel).where(
                MailboxRuleModel.signature == signature
            )
            return session.exec(stmt).first()

    def record_mailbox_rule_hit(self, rule_id: int) -> None:
        with self._session() as session:
            rule = session.get(MailboxRuleModel, rule_id)
            if rule is not None:
                rule.hit_count = (rule.hit_count or 0) + 1
                rule.updated_at = datetime.now()
                session.add(rule)
                session.commit()

    def upsert_mailbox_rule(
        self,
        *,
        signature: str,
        name: str,
        source_kind: str = "webhook",
        action: str = "route",
        target_chat_id: Optional[str] = "focal-suzent",
        target_label: Optional[str] = "Regent",
        target_project_id: Optional[str] = None,
        destination: str = "regent",
        delivery: str = "now",
        digest_minutes: int = 60,
        prompt: Optional[str] = None,
        origin: str = "learned",
        reason: Optional[str] = None,
        increment_hit: bool = True,
    ) -> MailboxRuleModel:
        now = datetime.now()
        with self._session() as session:
            stmt = select(MailboxRuleModel).where(
                MailboxRuleModel.signature == signature
            )
            rule = session.exec(stmt).first()
            if rule is not None and rule.origin == "pinned" and origin != "pinned":
                # Never overwrite a user-pinned rule with an auto-learned one.
                if increment_hit:
                    rule.hit_count = (rule.hit_count or 0) + 1
                    session.add(rule)
                    session.commit()
                    session.refresh(rule)
                return rule
            if rule is None:
                rule = MailboxRuleModel(
                    signature=signature, name=name, created_at=now, hit_count=0
                )
            rule.name = name or rule.name
            rule.source_kind = source_kind or rule.source_kind
            _apply_routing(
                rule,
                action=action,
                target_chat_id=target_chat_id,
                target_label=target_label,
                target_project_id=target_project_id,
                destination=destination,
                delivery=delivery,
                digest_minutes=digest_minutes,
                prompt=prompt,
            )
            rule.origin = origin
            if reason is not None:
                rule.reason = reason
            if increment_hit:
                rule.hit_count = (rule.hit_count or 0) + 1
            rule.updated_at = now
            session.add(rule)
            session.commit()
            session.refresh(rule)
            return rule

    def update_mailbox_rule(
        self,
        rule_id: int,
        *,
        action: str,
        target_chat_id: Optional[str] = None,
        target_label: Optional[str] = None,
        target_project_id: Optional[str] = None,
        destination: str = "regent",
        delivery: str = "now",
        digest_minutes: int = 60,
        prompt: Optional[str] = None,
        origin: str = "pinned",
        reason: Optional[str] = None,
    ) -> Optional[MailboxRuleModel]:
        with self._session() as session:
            rule = session.get(MailboxRuleModel, rule_id)
            if rule is None:
                return None
            _apply_routing(
                rule,
                action=action,
                target_chat_id=target_chat_id,
                target_label=target_label,
                target_project_id=target_project_id,
                destination=destination,
                delivery=delivery,
                digest_minutes=digest_minutes,
                prompt=prompt,
            )
            rule.origin = origin
            if reason is not None:
                rule.reason = reason
            rule.updated_at = datetime.now()
            session.add(rule)
            session.commit()
            session.refresh(rule)
            return rule

    def delete_mailbox_rule(self, rule_id: int) -> bool:
        with self._session() as session:
            rule = session.get(MailboxRuleModel, rule_id)
            if rule is None:
                return False
            session.delete(rule)
            session.commit()
            return True


def _apply_routing(
    rule: MailboxRuleModel,
    *,
    action: str,
    destination: str,
    target_chat_id: Optional[str],
    target_label: Optional[str],
    target_project_id: Optional[str],
    delivery: str,
    digest_minutes: int,
    prompt: Optional[str],
) -> None:
    """Set where a rule sends events and when, keeping only the target fields its destination uses."""
    if action == "none":
        destination = "none"
    rule.destination = destination
    rule.action = "none" if destination == "none" else "route"
    rule.target_project_id = target_project_id if destination == "project" else None
    rule.target_chat_id = (
        target_chat_id if destination in ("regent", "session") else None
    )
    rule.target_label = target_label if destination != "none" else None
    rule.delivery = delivery if delivery in ("now", "digest") else "now"
    rule.digest_minutes = max(1, digest_minutes)
    rule.prompt = (prompt or "").strip() or None
