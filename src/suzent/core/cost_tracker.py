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
        cache_write_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> None:
        """Record a single LLM call's cost, estimated via genai-prices."""
        try:
            from genai_prices import calc_price
            from genai_prices.types import Usage as GPUsage

            gp_usage = GPUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_write_tokens=cache_write_tokens or None,
                cache_read_tokens=cache_read_tokens or None,
            )
            # Our model IDs are "provider/model-ref"; genai-prices wants them split
            if "/" in model:
                provider_id, model_ref = model.split("/", 1)
            else:
                provider_id, model_ref = None, model
            cost_usd = float(
                calc_price(gp_usage, model_ref, provider_id=provider_id).total_price
            )
        except Exception:
            cost_usd = 0.0

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
                cache_write_tokens,
                cache_read_tokens,
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
        cache_write_tokens: int,
        cache_read_tokens: int,
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
                cache_write_tokens=cache_write_tokens,
                cache_read_tokens=cache_read_tokens,
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
                    summary.total_cache_write_tokens += cache_write_tokens
                    summary.total_cache_read_tokens += cache_read_tokens
                    summary.last_updated_at = now
                else:
                    summary = ChatCostSummaryModel(
                        chat_id=chat_id,
                        total_cost_usd=cost_usd,
                        total_input_tokens=input_tokens,
                        total_output_tokens=output_tokens,
                        total_cache_write_tokens=cache_write_tokens,
                        total_cache_read_tokens=cache_read_tokens,
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
                    "total_cache_write_tokens": 0,
                    "total_cache_read_tokens": 0,
                }
            return {
                "chat_id": chat_id,
                "total_cost_usd": summary.total_cost_usd,
                "total_input_tokens": summary.total_input_tokens,
                "total_output_tokens": summary.total_output_tokens,
                "total_cache_write_tokens": summary.total_cache_write_tokens,
                "total_cache_read_tokens": summary.total_cache_read_tokens,
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

    async def get_hourly_breakdown(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get per-hour cost breakdown."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._read_hourly_breakdown, days)

    def _read_hourly_breakdown(self, days: int) -> List[Dict[str, Any]]:
        from suzent.database import get_database, CostLedgerModel
        from sqlmodel import Session, select, func

        db = get_database()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        with Session(db.engine) as session:
            hour_col = func.strftime(
                "%Y-%m-%dT%H:00:00.000Z", CostLedgerModel.created_at
            ).label("hour")
            stmt = (
                select(
                    hour_col,
                    func.sum(CostLedgerModel.cost_usd).label("cost"),
                    func.sum(CostLedgerModel.input_tokens).label("input_tokens"),
                    func.sum(CostLedgerModel.output_tokens).label("output_tokens"),
                    func.count(CostLedgerModel.id).label("calls"),
                )
                .where(CostLedgerModel.created_at >= cutoff)
                .group_by(hour_col)
                .order_by(hour_col)
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

    async def get_activity_binned(
        self, days: int, interval_minutes: int
    ) -> List[Dict[str, Any]]:
        """Get cost breakdown binned by arbitrary minutes interval."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._read_activity_binned, days, interval_minutes
        )

    def _read_activity_binned(
        self, days: int, interval_minutes: int
    ) -> List[Dict[str, Any]]:
        from suzent.database import get_database, CostLedgerModel
        from sqlmodel import Session, select, func
        from sqlalchemy import cast, Integer

        db = get_database()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        interval_secs = interval_minutes * 60

        with Session(db.engine) as session:
            epoch_col = cast(func.strftime("%s", CostLedgerModel.created_at), Integer)
            bin_col = ((epoch_col / interval_secs) * interval_secs).label("bin")

            stmt = (
                select(
                    bin_col,
                    func.sum(CostLedgerModel.cost_usd).label("cost"),
                    func.sum(CostLedgerModel.input_tokens).label("input_tokens"),
                    func.sum(CostLedgerModel.output_tokens).label("output_tokens"),
                    func.count(CostLedgerModel.id).label("calls"),
                )
                .where(CostLedgerModel.created_at >= cutoff)
                .group_by(bin_col)
                .order_by(bin_col)
            )
            rows = session.exec(stmt).all()

            result = []
            for row in rows:
                if row[0] is None:
                    continue
                dt = datetime.fromtimestamp(int(row[0]), timezone.utc)
                result.append(
                    {
                        "date": dt.strftime("%Y-%m-%dT%H:%M:00.000Z"),
                        "cost_usd": row[1] or 0.0,
                        "input_tokens": row[2] or 0,
                        "output_tokens": row[3] or 0,
                        "calls": row[4] or 0,
                    }
                )
            return result

    async def get_model_breakdown(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get per-model cost breakdown."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._read_model_breakdown, days)

    def _read_model_breakdown(self, days: int) -> List[Dict[str, Any]]:
        from suzent.database import get_database, CostLedgerModel
        from sqlmodel import Session, select, func

        db = get_database()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        with Session(db.engine) as session:
            stmt = (
                select(
                    CostLedgerModel.model,
                    func.sum(CostLedgerModel.cost_usd).label("cost"),
                    func.sum(CostLedgerModel.input_tokens).label("input_tokens"),
                    func.sum(CostLedgerModel.output_tokens).label("output_tokens"),
                    func.count(CostLedgerModel.id).label("calls"),
                )
                .where(CostLedgerModel.created_at >= cutoff)
                .group_by(CostLedgerModel.model)
                .order_by(func.sum(CostLedgerModel.cost_usd).desc())
            )
            rows = session.exec(stmt).all()
            return [
                {
                    "model": row[0],
                    "cost_usd": row[1] or 0.0,
                    "input_tokens": row[2] or 0,
                    "output_tokens": row[3] or 0,
                    "calls": row[4] or 0,
                }
                for row in rows
            ]

    async def get_activity_stats(self) -> Dict[str, Any]:
        """Get activity stats (streaks, peak, cumulative)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._read_activity_stats)

    def _read_activity_stats(self) -> Dict[str, Any]:
        from suzent.database import get_database, CostLedgerModel
        from sqlmodel import Session, select, func

        db = get_database()
        with Session(db.engine) as session:
            # 1. Cumulative Tokens
            stmt_cum = select(
                func.sum(CostLedgerModel.input_tokens),
                func.sum(CostLedgerModel.output_tokens),
            )
            cum_row = session.exec(stmt_cum).one()
            cum_input = cum_row[0] or 0
            cum_output = cum_row[1] or 0
            cumulative_tokens = cum_input + cum_output

            # 2. Get daily token totals to compute peak and streaks
            day_col = func.date(CostLedgerModel.created_at).label("day")
            stmt_daily = (
                select(
                    day_col,
                    func.sum(
                        CostLedgerModel.input_tokens + CostLedgerModel.output_tokens
                    ).label("total_tokens"),
                )
                .group_by(day_col)
                .order_by(day_col)
            )
            daily_rows = session.exec(stmt_daily).all()

            peak_tokens = 0
            current_streak = 0
            longest_streak = 0

            if daily_rows:
                # We expect daily_rows to be ordered by day ascending
                peak_tokens = max((row[1] or 0 for row in daily_rows), default=0)

                from datetime import datetime

                streaks = []
                current = 0
                last_date = None

                today = datetime.now(timezone.utc).date()

                for row in daily_rows:
                    dt = datetime.strptime(str(row[0]), "%Y-%m-%d").date()
                    if last_date is None:
                        current = 1
                    else:
                        if (dt - last_date).days == 1:
                            current += 1
                        elif (dt - last_date).days > 1:
                            streaks.append(current)
                            current = 1
                    last_date = dt
                if current > 0:
                    streaks.append(current)

                longest_streak = max(streaks, default=0)

                if last_date is not None:
                    if (today - last_date).days <= 1:
                        current_streak = current
                    else:
                        current_streak = 0

            return {
                "cumulative_tokens": int(cumulative_tokens),
                "peak_tokens": int(peak_tokens),
                "current_streak": current_streak,
                "longest_streak": longest_streak,
            }


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
