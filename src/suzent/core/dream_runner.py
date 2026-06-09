"""Dream runner — autonomous memory consolidation.

A background BaseBrain service that, on a gate (time + volume) or on demand, runs a
forked, tool-restricted agent which consolidates the append-only daily memory logs
into the notebook vault (the "wiki keeper", run autonomously). The runner owns the
watermark (written to the vault's log.md) and regenerates MEMORY.md afterward.

See docs/03-developing/memory-consolidation-plan.md (Phase 3).
"""

import asyncio
import re
import time
from datetime import datetime, timezone
from typing import List, Optional

from suzent.config import CONFIG
from suzent.core.base_brain import BaseBrain, get_active
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.memory.lifecycle import get_memory_manager
from suzent.memory import memory_context

logger = get_logger(__name__)

DREAM_CHAT_ID = "system-dream"


def get_active_dream_runner() -> Optional["DreamRunner"]:
    """Return the active DreamRunner instance, or None."""
    return get_active(DreamRunner)


class DreamRunner(BaseBrain):
    """Gated autonomous consolidation of daily logs into the notebook vault."""

    _brain_name = "DreamRunner"

    def __init__(self):
        super().__init__()
        self._lock = asyncio.Lock()
        # Ephemeral pacing state (NOT the watermark, which lives in log.md).
        self._last_attempt_at: float = 0.0
        self._failures: dict = {}  # batch-end-date -> consecutive no-op count

    async def _run_loop(self):
        # Let startup settle before the first tick.
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            return
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Dream loop error: {e}")
            try:
                await asyncio.sleep(max(60, CONFIG.memory_consolidation_interval_seconds))
            except asyncio.CancelledError:
                break

    # ----- helpers -----

    @staticmethod
    def _today_utc() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _pending_dates(self, mgr, watermark: Optional[str]) -> List[str]:
        """Daily-log dates not yet consolidated and strictly before today (UTC)."""
        today = self._today_utc()
        dates: List[str] = []
        for p in sorted(mgr.markdown_store.archive_dir.glob("????-??-??.md")):
            d = p.stem
            if d >= today:  # never touch today's in-progress log
                continue
            if watermark and d <= watermark:
                continue
            dates.append(d)
        return dates

    def _count_fact_lines(self, mgr, dates: List[str]) -> int:
        n = 0
        for d in dates:
            p = mgr.markdown_store.archive_dir / f"{d}.md"
            if not p.exists():
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                if re.match(r"^-\s*\[", line.strip()):
                    n += 1
        return n

    def _content_pages_state(self, mgr) -> dict:
        """mtime snapshot of content pages (proof-of-work signal; excludes nav files)."""
        state: dict = {}
        try:
            for p in mgr.markdown_store.list_notebook_pages():
                try:
                    state[str(p)] = p.stat().st_mtime
                except Exception:
                    continue
        except Exception:
            pass
        return state

    # ----- gate + run -----

    async def _tick(self):
        if not CONFIG.memory_consolidation_enabled or self._lock.locked():
            return
        mgr = get_memory_manager()
        if not mgr or not mgr.markdown_store or not mgr.llm_client:
            return

        watermark = mgr.markdown_store.read_watermark()
        pending = self._pending_dates(mgr, watermark)
        if not pending:
            return

        behind = len(pending) > CONFIG.memory_consolidation_max_days
        if not behind:
            # Steady state: back off on attempts + require enough new material.
            if (time.time() - self._last_attempt_at) < CONFIG.memory_consolidation_min_hours * 3600:
                return
            if self._count_fact_lines(mgr, pending) < CONFIG.memory_consolidation_min_facts:
                return
        # behind => sprint (ignore the daily/volume gate) until caught up.
        await self._run_dream(mgr, watermark, pending)

    async def force_run(self) -> dict:
        """On-demand consolidation — bypasses time+volume gates (not the lock)."""
        mgr = get_memory_manager()
        if not mgr or not mgr.markdown_store or not mgr.llm_client:
            return {"ran": False, "reason": "memory system unavailable"}
        watermark = mgr.markdown_store.read_watermark()
        pending = self._pending_dates(mgr, watermark)
        if not pending:
            return {"ran": False, "reason": "nothing pending"}
        return await self._run_dream(mgr, watermark, pending)

    async def _run_dream(self, mgr, watermark: Optional[str], pending: List[str]) -> dict:
        if self._lock.locked():
            return {"ran": False, "reason": "already running"}
        async with self._lock:
            self._last_attempt_at = time.time()
            batch = pending[: CONFIG.memory_consolidation_max_days]
            w_new = batch[-1]

            # retry-then-skip: a batch that keeps producing nothing must not wedge the backlog.
            if self._failures.get(w_new, 0) >= CONFIG.memory_consolidation_max_retries:
                logger.warning(f"[dream] skipping un-consolidatable batch <= {w_new}")
                await self._advance_watermark(mgr, w_new)
                self._failures.pop(w_new, None)
                return {"ran": True, "skipped": True, "watermark": w_new}

            start = watermark or "0000-00-00"
            before = self._content_pages_state(mgr)

            self._pause_watcher()
            try:
                await self._reset_dream_chat()
                await self._run_agent(start, w_new)
            except Exception as e:
                logger.error(f"[dream] agent run failed: {e}")
            finally:
                self._resume_watcher()

            # Proof of work: a content page changed (excludes log.md/index.md churn).
            if self._content_pages_state(mgr) == before:
                self._failures[w_new] = self._failures.get(w_new, 0) + 1
                logger.info(f"[dream] no content changes; not advancing (W={w_new})")
                return {"ran": True, "changed": False, "watermark": watermark}

            self._failures.pop(w_new, None)
            await self._advance_watermark(mgr, w_new)
            # Promote MEMORY.md first so the reconcile pass indexes the fresh file.
            try:
                await mgr.promote_memory_md(CONFIG.user_id)
            except Exception as e:
                logger.error(f"[dream] promote_memory_md failed: {e}")
            try:
                await mgr._core_indexer.check_and_update(
                    markdown_store=mgr.markdown_store,
                    lancedb_store=mgr.store,
                    embedding_gen=mgr.embedding_gen,
                    user_id=CONFIG.user_id,
                )
            except Exception as e:
                logger.error(f"[dream] reindex failed: {e}")
            logger.info(f"[dream] consolidated through {w_new}")
            return {"ran": True, "changed": True, "watermark": w_new}

    async def _advance_watermark(self, mgr, w_new: str):
        await mgr.markdown_store.write_watermark_entry(self._today_utc(), w_new)

    # ----- watcher pause/resume (via lifecycle gate Event) -----

    @staticmethod
    def _pause_watcher():
        try:
            from suzent.memory import lifecycle

            gate = getattr(lifecycle, "core_watcher_gate", None)
            if gate is not None:
                gate.clear()
        except Exception:
            pass

    @staticmethod
    def _resume_watcher():
        try:
            from suzent.memory import lifecycle

            gate = getattr(lifecycle, "core_watcher_gate", None)
            if gate is not None:
                gate.set()
        except Exception:
            pass

    # ----- forked agent -----

    async def _reset_dream_chat(self):
        db = get_database()
        chat = db.get_chat(DREAM_CHAT_ID)
        if not chat:
            db.create_chat(
                title="Memory consolidation (dream)",
                config={"platform": "dream", "auto_approve_tools": True},
                chat_id=DREAM_CHAT_ID,
            )
        else:
            # Reset to a clean slate. agent_state=b"" (not None, which means "no change")
            # clears the history; the chat processor treats empty bytes as "no history".
            try:
                db.update_chat(DREAM_CHAT_ID, agent_state=b"", messages=[])
            except Exception:
                pass

    async def _run_agent(self, start: str, end: str):
        from suzent.core.chat_processor import ChatProcessor
        from suzent.agent_manager import build_agent_config

        base = {
            "platform": "dream",
            "memory_enabled": False,
            "auto_approve_tools": True,
            "tools": list(CONFIG.memory_dream_tools),
            "static_instructions": memory_context.DREAM_SYSTEM_PROMPT,
        }
        if CONFIG.memory_consolidation_model:
            base["model"] = CONFIG.memory_consolidation_model
        cfg = build_agent_config(base, require_social_tool=False)

        message = memory_context.DREAM_INSTRUCTIONS.format(start=start, end=end)
        await asyncio.wait_for(
            ChatProcessor().process_turn_text(
                chat_id=DREAM_CHAT_ID,
                user_id=CONFIG.user_id,
                message_content=message,
                config_override=cfg,
            ),
            timeout=CONFIG.memory_consolidation_timeout_seconds,
        )
