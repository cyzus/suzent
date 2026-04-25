"""
Unified cost tracking for all LLM calls.

Records every model invocation in a global ``cost_ledger`` table (survives
chat deletion) and maintains a denormalized ``chat_cost_summary`` for fast
per-chat queries.

Usage::

    tracker = get_cost_tracker()
    await tracker.log_cost(
        chat_id="abc-123",
        model="openai/gpt-4.1",
        role="primary",
        input_tokens=1500,
        output_tokens=800,
    )
    global_cost = await tracker.get_global_cost(days=30)
    chat_cost = await tracker.get_chat_cost("abc-123")
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from suzent.core.model_registry import get_model_registry
from suzent.logger import get_logger

logger = get_logger(__name__)


class CostTracker:
    """Unified cost tracker — writes to SQLite via ChatDatabase."""

    async def log_cost(
        self,
        chat_id: Optional[str],
        model: str,
        role: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: Optional[float] = None,
    ) -> None:
        """Record a single LLM call's cost.

        If ``cost_usd`` is None, it is estimated from the model registry.
        """
        if cost_usd is None:
            registry = get_model_registry()
            cost_usd = registry.estimate_cost(model, input_tokens, output_tokens)

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                self._write_cost,
                chat_id,
                model,
                role,
                input_tokens,
                output_tokens,
                cost_usd,
            )
        except Exception as e:
            logger.warning("Failed to log cost: {}", e)

    def _write_cost(
        self,
        chat_id: Optional[str],
        model: str,
        role: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> None:
        """Synchronous write — runs in executor."""
        from suzent.database import (
            get_database,
            CostLedgerModel,
            ChatCostSummaryModel,
        )
        from sqlmodel import Session

        db = get_database()
        now = datetime.now(timezone.utc)

        with Session(db.engine) as session:
            # 1. Insert ledger entry
            entry = CostLedgerModel(
                chat_id=chat_id,
                model=model,
                role=role,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                created_at=now,
            )
            session.add(entry)

            # 2. Upsert chat cost summary (if chat_id is not None)
            if chat_id:
                summary = session.get(ChatCostSummaryModel, chat_id)
                if summary:
                    summary.total_cost_usd += cost_usd
                    summary.total_input_tokens += input_tokens
                    summary.total_output_tokens += output_tokens
                    summary.last_updated_at = now
                else:
                    summary = ChatCostSummaryModel(
                        chat_id=chat_id,
                        total_cost_usd=cost_usd,
                        total_input_tokens=input_tokens,
                        total_output_tokens=output_tokens,
                        last_updated_at=now,
                    )
                session.add(summary)

            session.commit()

    async def get_global_cost(self, days: int = 30) -> Dict[str, Any]:
        """Get global cost summary for the last N days."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._read_global_cost, days)

    def _read_global_cost(self, days: int) -> Dict[str, Any]:
        from suzent.database import get_database, CostLedgerModel
        from sqlmodel import Session, select, func

        db = get_database()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        with Session(db.engine) as session:
            stmt = select(
                func.sum(CostLedgerModel.cost_usd),
                func.sum(CostLedgerModel.input_tokens),
                func.sum(CostLedgerModel.output_tokens),
                func.count(CostLedgerModel.id),
            ).where(CostLedgerModel.created_at >= cutoff)

            row = session.exec(stmt).one()
            return {
                "total_cost_usd": row[0] or 0.0,
                "total_input_tokens": row[1] or 0,
                "total_output_tokens": row[2] or 0,
                "total_calls": row[3] or 0,
                "days": days,
            }

    async def get_chat_cost(self, chat_id: str) -> Dict[str, Any]:
        """Get cost summary for a single chat."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._read_chat_cost, chat_id)

    def _read_chat_cost(self, chat_id: str) -> Dict[str, Any]:
        from suzent.database import get_database, ChatCostSummaryModel
        from sqlmodel import Session

        db = get_database()
        with Session(db.engine) as session:
            summary = session.get(ChatCostSummaryModel, chat_id)
            if not summary:
                return {
                    "chat_id": chat_id,
                    "total_cost_usd": 0.0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                }
            return {
                "chat_id": chat_id,
                "total_cost_usd": summary.total_cost_usd,
                "total_input_tokens": summary.total_input_tokens,
                "total_output_tokens": summary.total_output_tokens,
            }

    async def get_daily_breakdown(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get per-day cost breakdown."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._read_daily_breakdown, days)

    def _read_daily_breakdown(self, days: int) -> List[Dict[str, Any]]:
        from suzent.database import get_database, CostLedgerModel
        from sqlmodel import Session, select, func

        db = get_database()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        with Session(db.engine) as session:
            day_col = func.date(CostLedgerModel.created_at).label("day")
            stmt = (
                select(
                    day_col,
                    func.sum(CostLedgerModel.cost_usd).label("cost"),
                    func.sum(CostLedgerModel.input_tokens).label("input_tokens"),
                    func.sum(CostLedgerModel.output_tokens).label("output_tokens"),
                    func.count(CostLedgerModel.id).label("calls"),
                )
                .where(CostLedgerModel.created_at >= cutoff)
                .group_by(day_col)
                .order_by(day_col)
            )
            rows = session.exec(stmt).all()
            return [
                {
                    "date": str(row[0]),
                    "cost_usd": row[1] or 0.0,
                    "input_tokens": row[2] or 0,
                    "output_tokens": row[3] or 0,
                    "calls": row[4] or 0,
                }
                for row in rows
            ]


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: Optional[CostTracker] = None


def get_cost_tracker() -> CostTracker:
    """Get the global CostTracker singleton."""
    global _instance
    if _instance is None:
        _instance = CostTracker()
    return _instance
