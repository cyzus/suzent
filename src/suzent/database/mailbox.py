"""Persistence operations for Mailbox items and dynamic routing rules."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlmodel import select

from .models import MailboxItemModel, MailboxRuleModel


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
                spooled_at=spooled_at,
                created_at=now,
            )
            session.add(item)
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
    ) -> List[MailboxItemModel]:
        with self._session() as session:
            stmt = select(MailboxItemModel)
            if route_status == "routed":
                stmt = stmt.where(MailboxItemModel.route_status == "routed")
            elif route_status == "unrouted":
                stmt = stmt.where(MailboxItemModel.route_status == "unrouted")
            if source_kind:
                stmt = stmt.where(MailboxItemModel.source_kind == source_kind)
            stmt = stmt.order_by(MailboxItemModel.id.desc()).offset(offset).limit(limit)
            return list(session.exec(stmt).all())

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
        origin: str = "learned",
        reason: Optional[str] = None,
        increment_hit: bool = True,
    ) -> MailboxRuleModel:
        now = datetime.now()
        with self._session() as session:
            stmt = select(MailboxRuleModel).where(
                MailboxRuleModel.signature == signature
            )
            existing = session.exec(stmt).first()
            if existing is not None:
                # Never overwrite a user-pinned rule with an auto-learned one.
                if existing.origin == "pinned" and origin != "pinned":
                    if increment_hit:
                        existing.hit_count = (existing.hit_count or 0) + 1
                        session.add(existing)
                        session.commit()
                        session.refresh(existing)
                    return existing
                existing.name = name or existing.name
                existing.source_kind = source_kind or existing.source_kind
                existing.action = action
                existing.target_chat_id = target_chat_id if action == "route" else None
                existing.target_label = target_label if action == "route" else None
                existing.origin = origin
                if reason is not None:
                    existing.reason = reason
                if increment_hit:
                    existing.hit_count = (existing.hit_count or 0) + 1
                existing.updated_at = now
                session.add(existing)
                session.commit()
                session.refresh(existing)
                return existing

            rule = MailboxRuleModel(
                signature=signature,
                name=name,
                source_kind=source_kind,
                action=action,
                target_chat_id=target_chat_id if action == "route" else None,
                target_label=target_label if action == "route" else None,
                origin=origin,
                reason=reason,
                hit_count=1 if increment_hit else 0,
                created_at=now,
                updated_at=now,
            )
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
        origin: str = "pinned",
        reason: Optional[str] = None,
    ) -> Optional[MailboxRuleModel]:
        with self._session() as session:
            rule = session.get(MailboxRuleModel, rule_id)
            if rule is None:
                return None
            rule.action = action
            rule.target_chat_id = target_chat_id if action == "route" else None
            rule.target_label = target_label if action == "route" else None
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
