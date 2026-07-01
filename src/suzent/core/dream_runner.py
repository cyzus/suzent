"""Dream runner — autonomous memory consolidation.

A background BaseBrain service that, on a gate (time + volume) or on demand, runs a
forked, tool-restricted agent which consolidates the append-only daily memory logs
into the notebook vault (the "wiki keeper", run autonomously). The runner owns the
watermark (written to the vault's log.md) and regenerates MEMORY.md afterward.

See docs/02-concepts/memory/consolidation.md (Phase 3).
"""

import asyncio
import re
import time
from datetime import datetime, timezone
from typing import Any, List, Optional

from suzent.config import CONFIG
from suzent.core.base_brain import BaseBrain, get_active
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.memory.lifecycle import get_memory_manager
from suzent.memory import memory_context

logger = get_logger(__name__)

DREAM_CHAT_ID = "system-dream"
DREAM_LINT_CHAT_ID = "system-dream-lint"
_REASONING_DETAILS_RE = re.compile(
    r"<details\s+data-reasoning=[\"']true[\"'][^>]*>.*?</details>\s*",
    re.IGNORECASE | re.DOTALL,
)


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
        self._last_started_at: Optional[str] = None
        self._last_finished_at: Optional[str] = None
        self._last_result: Optional[dict[str, Any]] = None
        self._last_ingest_finished_at: Optional[str] = None
        self._last_ingest_result: Optional[dict[str, Any]] = None
        self._last_lint_finished_at: Optional[str] = None
        self._last_lint_result: Optional[dict[str, Any]] = None
        self._phase: str = "idle"
        self._background_task: Optional[asyncio.Task] = None
        self._reindex_task: Optional[asyncio.Task] = None
        # Lint pacing (ephemeral; the durable "last lint" signal is log.md entries).
        self._last_lint_attempt_at: float = 0.0

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
                await asyncio.sleep(
                    max(60, CONFIG.memory_consolidation_interval_seconds)
                )
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
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
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

    def status(self) -> dict[str, Any]:
        """Return a frontend-safe snapshot of dream consolidation state."""
        running = self._lock.locked() or self._phase == "queued"
        persisted_ingest = self._load_last_result_from_dream_chat(
            DREAM_CHAT_ID,
            phase="ingest",
        )
        persisted_lint = self._load_last_result_from_dream_chat(
            DREAM_LINT_CHAT_ID,
            phase="lint",
        )
        last_ingest_finished_at = self._last_ingest_finished_at or persisted_ingest.get(
            "last_finished_at"
        )
        last_ingest_result = self._last_ingest_result or persisted_ingest.get(
            "last_result"
        )
        last_lint_finished_at = self._last_lint_finished_at or persisted_lint.get(
            "last_finished_at"
        )
        last_lint_result = self._last_lint_result or persisted_lint.get("last_result")
        last_started_at = self._last_started_at or persisted_ingest.get(
            "last_started_at"
        )
        last_finished_at = self._last_finished_at or last_ingest_finished_at
        last_result = self._last_result or last_ingest_result
        mgr = get_memory_manager()
        if not mgr or not getattr(mgr, "markdown_store", None):
            return {
                "active": True,
                "available": False,
                "running": running,
                "phase": self._phase,
                "reason": "memory system unavailable",
                "enabled": CONFIG.memory_consolidation_enabled,
                "last_started_at": last_started_at,
                "last_finished_at": last_finished_at,
                "last_result": last_result,
                "last_ingest_finished_at": last_ingest_finished_at,
                "last_ingest_result": last_ingest_result,
                "last_lint_finished_at": last_lint_finished_at,
                "last_lint_result": last_lint_result,
            }

        watermark = mgr.markdown_store.read_watermark()
        pending = self._pending_dates(mgr, watermark)
        pending_facts = self._count_fact_lines(mgr, pending)
        all_dates = [
            p.stem
            for p in sorted(mgr.markdown_store.archive_dir.glob("????-??-??.md"))
            if p.stem < self._today_utc()
        ]
        consolidated_count = len(
            [date for date in all_dates if watermark and date <= watermark]
        )
        total_count = len(all_dates)
        progress_percent = (
            round((consolidated_count / total_count) * 100) if total_count > 0 else 100
        )
        next_batch = pending[: CONFIG.memory_consolidation_max_days]
        available = bool(getattr(mgr, "llm_client", None))
        last_lint = mgr.markdown_store.read_last_lint_date()
        lint_days = self._days_since(last_lint)
        return {
            "active": True,
            "available": available,
            "reason": None if available else "consolidation model unavailable",
            "enabled": CONFIG.memory_consolidation_enabled,
            "running": running,
            "phase": self._phase,
            "watermark": watermark,
            "pending_dates": pending,
            "pending_count": len(pending),
            "pending_facts": pending_facts,
            "archive_count": total_count,
            "consolidated_count": consolidated_count,
            "progress_percent": progress_percent,
            "next_batch_end": next_batch[-1] if next_batch else None,
            "last_attempt_at": self._last_attempt_at or None,
            "last_started_at": last_started_at,
            "last_finished_at": last_finished_at,
            "last_result": last_result,
            "last_ingest_finished_at": last_ingest_finished_at,
            "last_ingest_result": last_ingest_result,
            "last_lint_finished_at": last_lint_finished_at,
            "last_lint_result": last_lint_result,
            "failures": dict(self._failures),
            "min_facts": CONFIG.memory_consolidation_min_facts,
            "min_hours": CONFIG.memory_consolidation_min_hours,
            "max_days": CONFIG.memory_consolidation_max_days,
            "lint_enabled": CONFIG.memory_lint_enabled,
            "lint_last_run": last_lint,
            "lint_days_since": round(lint_days, 1) if lint_days is not None else None,
            "lint_due": self._lint_due(mgr) if not pending else False,
            "lint_min_days": CONFIG.memory_lint_min_days,
        }

    # ----- gate + run -----

    async def _tick(self):
        if not CONFIG.memory_consolidation_enabled or self._lock.locked():
            return
        mgr = get_memory_manager()
        if not mgr or not mgr.markdown_store or not mgr.llm_client:
            return

        watermark = mgr.markdown_store.read_watermark()
        pending = self._pending_dates(mgr, watermark)
        if pending:
            behind = len(pending) > CONFIG.memory_consolidation_max_days
            if not behind:
                # Steady state: back off on attempts + require enough new material.
                if (
                    time.time() - self._last_attempt_at
                ) < CONFIG.memory_consolidation_min_hours * 3600:
                    return
                if (
                    self._count_fact_lines(mgr, pending)
                    < CONFIG.memory_consolidation_min_facts
                ):
                    return
            # behind => sprint (ignore the daily/volume gate) until caught up.
            await self._run_dream(mgr, watermark, pending)
            return

        # Ingest is caught up. Only now consider the (slower) lint pass, so the
        # editorial audit never starves new-log consolidation.
        if self._lint_due(mgr):
            await self._run_lint(mgr)

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

    def start_force_run(self) -> dict:
        """Start on-demand ingest consolidation in the background for UI triggers."""
        if self._lock.locked() or self._phase == "queued":
            return {"ran": False, "started": False, "reason": "already running"}

        mgr = get_memory_manager()
        if not mgr or not mgr.markdown_store or not mgr.llm_client:
            return {
                "ran": False,
                "started": False,
                "reason": "memory system unavailable",
            }

        watermark = mgr.markdown_store.read_watermark()
        pending = self._pending_dates(mgr, watermark)
        if not pending:
            return {"ran": False, "started": False, "reason": "nothing pending"}

        self._phase = "queued"
        target = pending[: CONFIG.memory_consolidation_max_days][-1]
        task = asyncio.create_task(self._run_dream(mgr, watermark, pending))
        self._background_task = task

        def _done(done_task: asyncio.Task) -> None:
            try:
                done_task.result()
            except Exception as e:
                self._phase = "idle"
                logger.error(f"[dream] background run failed: {e}")

        task.add_done_callback(_done)
        return {
            "ran": True,
            "started": True,
            "phase": "ingest",
            "watermark": watermark,
            "target": target,
        }

    def start_lint_run(self) -> dict:
        """Start an on-demand lint pass in the background for UI triggers."""
        if self._lock.locked() or self._phase == "queued":
            return {"ran": False, "started": False, "reason": "already running"}

        mgr = get_memory_manager()
        if not mgr or not mgr.markdown_store or not mgr.llm_client:
            return {
                "ran": False,
                "started": False,
                "reason": "memory system unavailable",
            }
        if not CONFIG.memory_lint_enabled:
            return {"ran": False, "started": False, "reason": "lint disabled"}

        self._phase = "queued"
        task = asyncio.create_task(self._run_lint(mgr))
        self._background_task = task

        def _done(done_task: asyncio.Task) -> None:
            try:
                done_task.result()
            except Exception as e:
                self._phase = "idle"
                logger.error(f"[dream] background lint failed: {e}")

        task.add_done_callback(_done)
        return {"ran": True, "started": True, "phase": "lint"}

    async def _run_dream(
        self, mgr, watermark: Optional[str], pending: List[str]
    ) -> dict:
        if self._lock.locked():
            return {"ran": False, "reason": "already running"}
        async with self._lock:
            self._phase = "preparing"
            self._last_attempt_at = time.time()
            self._last_started_at = datetime.now(timezone.utc).isoformat()
            batch = pending[: CONFIG.memory_consolidation_max_days]
            w_new = batch[-1]

            # retry-then-skip: a batch that keeps producing nothing must not wedge the backlog.
            if self._failures.get(w_new, 0) >= CONFIG.memory_consolidation_max_retries:
                logger.warning(f"[dream] skipping un-consolidatable batch <= {w_new}")
                await self._advance_watermark(mgr, w_new)
                self._failures.pop(w_new, None)
                result = {
                    "ran": True,
                    "phase": "ingest",
                    "skipped": True,
                    "watermark": w_new,
                }
                self._record_result(result)
                return result

            start = watermark or "0000-00-00"
            before = self._content_pages_state(mgr)

            self._pause_watcher()
            agent_ok = False
            summary = ""
            try:
                await self._reset_dream_chat(
                    DREAM_CHAT_ID,
                    title="Memory consolidation (dream ingest)",
                )
                self._phase = "running_agent"
                summary = await self._run_agent(start, w_new)
                agent_ok = True
            except Exception as e:
                logger.error(f"[dream] agent run failed: {e}")
            finally:
                self._resume_watcher()

            self._phase = "finalizing"
            # Advance ONLY when the agent finished cleanly AND produced real page
            # changes. A failed or timed-out run can leave a partially-written page,
            # so "a content page changed" alone is NOT proof of work — advancing on it
            # would mark the whole batch consolidated and let the indexer drop the raw
            # daily logs (<= watermark) for facts that were never folded into the vault
            # (silent data loss). On any failure we bump the retry counter and keep the
            # watermark put, so the batch is re-attempted from the same start (and
            # eventually retry-skipped if it stays un-consolidatable).
            changed = self._content_pages_state(mgr) != before
            if not (agent_ok and changed):
                self._failures[w_new] = self._failures.get(w_new, 0) + 1
                reason = (
                    "agent run failed/timed out"
                    if not agent_ok
                    else "no content changes"
                )
                logger.info(
                    f"[dream] not advancing ({reason}); watermark stays {watermark} (target {w_new})"
                )
                result = {
                    "ran": True,
                    "phase": "ingest",
                    "changed": changed,
                    "advanced": False,
                    "watermark": watermark,
                    "summary": summary or reason,
                }
                self._record_result(result)
                return result

            self._failures.pop(w_new, None)
            result_summary = summary or f"Consolidated through {w_new}."
            await self._advance_watermark(mgr, w_new)
            # Promote MEMORY.md (bounded) so the curated summary reflects this batch.
            try:
                await asyncio.wait_for(
                    mgr.promote_memory_md(CONFIG.user_id),
                    timeout=CONFIG.memory_consolidation_timeout_seconds,
                )
            except Exception as e:
                logger.error(f"[dream] promote_memory_md failed/timed out: {e}")
            logger.info(f"[dream] consolidated through {w_new}")
            result = {
                "ran": True,
                "phase": "ingest",
                "changed": True,
                "advanced": True,
                "watermark": w_new,
                "summary": result_summary,
            }
            # Consolidation is durably complete now (watermark + MEMORY.md). The search
            # reindex is just index maintenance and can be SLOW (minutes on fat early
            # logs, hundreds of embeddings each) — running it inline pins the panel in
            # 'finalizing' and holds the lock the whole time. Mark the run done and fan
            # the reindex out to the background instead.
            self._record_result(result)
            self._schedule_reindex(mgr)
            return result

    def _record_result(self, result: dict[str, Any]) -> None:
        self._last_result = result
        self._last_finished_at = datetime.now(timezone.utc).isoformat()
        if result.get("phase") == "lint":
            self._last_lint_result = result
            self._last_lint_finished_at = self._last_finished_at
        else:
            self._last_ingest_result = result
            self._last_ingest_finished_at = self._last_finished_at
        self._phase = "idle"

    @staticmethod
    def _clean_summary(content: str) -> str:
        return _REASONING_DETAILS_RE.sub("", content).strip()

    def _extract_final_summary_from_message(self, message: dict[str, Any]) -> str:
        """Return the final assistant text block from a persisted display message."""
        parts = message.get("parts")
        if isinstance(parts, list):
            final_text_parts: list[str] = []
            for part in parts:
                if not isinstance(part, dict):
                    continue
                part_type = part.get("type")
                if part_type == "tool":
                    final_text_parts.clear()
                    continue
                if part_type != "text":
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    final_text_parts.append(text)
            if final_text_parts:
                return self._clean_summary("".join(final_text_parts))

        return self._clean_summary(str(message.get("content") or ""))

    def _load_last_result_from_dream_chat(
        self,
        chat_id: str,
        *,
        phase: str,
    ) -> dict[str, Any]:
        try:
            chat = get_database().get_chat(chat_id)
            if not chat:
                return {}
            for message in reversed(chat.messages or []):
                if not isinstance(message, dict) or message.get("role") != "assistant":
                    continue
                if message.get("_streaming_draft"):
                    continue
                content = self._extract_final_summary_from_message(message)
                if not content:
                    continue
                return {
                    "last_started_at": None,
                    "last_finished_at": chat.updated_at.isoformat()
                    if chat.updated_at
                    else None,
                    "last_result": {
                        "ran": True,
                        "phase": phase,
                        "summary": content,
                    },
                }
        except Exception as e:
            logger.debug(f"[dream] failed to load last result from chat: {e}")
        return {}

    async def _advance_watermark(self, mgr, w_new: str):
        await mgr.markdown_store.write_watermark_entry(self._today_utc(), w_new)

    async def _reindex(self, mgr) -> None:
        """Reconcile the vault into the search index, with a hard timeout.

        The indexer embeds every changed page and grabs its own shared lock; a stalled
        embedding call would otherwise run unbounded. The watermark is already advanced
        by the time we get here, so a timed-out reindex is non-fatal — the indexer is
        idempotent and the next reconcile picks up whatever was missed.
        """
        await asyncio.wait_for(
            mgr._core_indexer.check_and_update(
                markdown_store=mgr.markdown_store,
                lancedb_store=mgr.store,
                embedding_gen=mgr.embedding_gen,
                user_id=CONFIG.user_id,
            ),
            timeout=CONFIG.memory_consolidation_timeout_seconds,
        )
        # Compact the archival table while we're already doing background maintenance.
        # Per-fact inserts fragment it into hundreds of tiny files; left uncompacted,
        # the memory list/stats views slow to seconds. This keeps them sub-100ms.
        store = getattr(mgr, "store", None)
        if store is not None and hasattr(store, "optimize"):
            try:
                await asyncio.wait_for(
                    store.optimize(),
                    timeout=CONFIG.memory_consolidation_timeout_seconds,
                )
            except Exception as e:
                logger.warning(f"[dream] archival compaction failed/timed out: {e}")

    def _schedule_reindex(self, mgr) -> None:
        """Fan the (slow) search reindex out to the background so it never blocks the
        dream cycle or pins the panel in 'finalizing'. The indexer is idempotent and
        catches up whatever's missed, so if one is already in flight we just skip —
        the next cycle's reindex will cover this batch too.
        """
        if self._reindex_task is not None and not self._reindex_task.done():
            return  # one already running; it will pick up the latest vault state

        async def _bg() -> None:
            try:
                await self._reindex(mgr)
            except Exception as e:
                logger.error(f"[dream] background reindex failed/timed out: {e}")

        try:
            self._reindex_task = asyncio.create_task(_bg())
        except Exception as e:
            logger.error(f"[dream] failed to schedule background reindex: {e}")

    # ----- lint phase (editorial audit; runs only once ingest is caught up) -----

    @staticmethod
    def _days_since(date_str: Optional[str]) -> Optional[float]:
        if not date_str:
            return None
        try:
            then = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - then).total_seconds() / 86400.0
        except Exception:
            return None

    def _lint_due(self, mgr) -> bool:
        """True if the vault is overdue for a lint pass (and not rate-limited)."""
        if not CONFIG.memory_lint_enabled:
            return False
        # Don't re-attempt within a day even if the last pass logged nothing.
        if (time.time() - self._last_lint_attempt_at) < 24 * 3600:
            return False
        last = mgr.markdown_store.read_last_lint_date()
        days = self._days_since(last)
        # Never linted, or older than the configured cadence.
        return days is None or days >= CONFIG.memory_lint_min_days

    async def _run_lint(self, mgr) -> dict:
        """Run the editorial lint pass. Records a log entry on a clean run (no watermark)."""
        if self._lock.locked():
            return {"ran": False, "reason": "already running"}
        async with self._lock:
            self._phase = "preparing"
            self._last_lint_attempt_at = time.time()
            self._last_started_at = datetime.now(timezone.utc).isoformat()

            before = self._content_pages_state(mgr)
            self._pause_watcher()
            agent_ok = False
            summary = ""
            try:
                await self._reset_dream_chat(
                    DREAM_LINT_CHAT_ID,
                    title="Memory consolidation (dream lint)",
                )
                self._phase = "running_lint"
                summary = await self._run_lint_agent()
                agent_ok = True
            except Exception as e:
                logger.error(f"[dream] lint run failed: {e}")
            finally:
                self._resume_watcher()

            self._phase = "finalizing"
            changed = self._content_pages_state(mgr) != before
            # Lint may legitimately find nothing to fix, so unlike ingest a clean
            # no-change run is still "success" — we record the pass either way so the
            # weekly cadence advances. We only skip the log entry if the agent errored.
            if not agent_ok:
                result = {
                    "ran": True,
                    "phase": "lint",
                    "ok": False,
                    "changed": changed,
                    "summary": summary or "lint run failed/timed out",
                }
                self._record_result(result)
                return result

            try:
                await mgr.markdown_store.write_lint_entry(self._today_utc())
            except Exception as e:
                logger.error(f"[dream] write_lint_entry failed: {e}")
            logger.info(f"[dream] lint pass complete (changed={changed})")
            result = {
                "ran": True,
                "phase": "lint",
                "ok": True,
                "changed": changed,
                "summary": summary or "Lint pass complete (no changes).",
            }
            # Mark done, then reindex in the background (see _run_dream rationale).
            self._record_result(result)
            if changed:
                self._schedule_reindex(mgr)
            return result

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

    async def _reset_dream_chat(self, chat_id: str, *, title: str):
        db = get_database()
        chat = db.get_chat(chat_id)
        if not chat:
            db.create_chat(
                title=title,
                config={
                    "platform": "dream",
                    "permission_mode": "auto",
                    "interaction_profile": "headless",
                },
                chat_id=chat_id,
            )
        else:
            # Reset to a clean slate. agent_state=b"" (not None, which means "no change")
            # clears the history; the chat processor treats empty bytes as "no history".
            try:
                db.update_chat(chat_id, agent_state=b"", messages=[])
            except Exception:
                pass

    async def _run_agent(self, start: str, end: str) -> str:
        """Ingest phase: fold daily logs in (start, end] into the vault.

        Returns the agent's one-paragraph summary (shown in the dream panel).
        """
        return await self._run_forked_agent(
            DREAM_CHAT_ID,
            memory_context.DREAM_SYSTEM_PROMPT,
            memory_context.DREAM_INSTRUCTIONS.format(start=start, end=end),
        )

    async def _run_lint_agent(self) -> str:
        """Lint phase: editorial audit/repair of the existing vault. Returns the summary."""
        return await self._run_forked_agent(
            DREAM_LINT_CHAT_ID,
            memory_context.LINT_SYSTEM_PROMPT,
            memory_context.LINT_INSTRUCTIONS,
        )

    async def _run_forked_agent(
        self,
        chat_id: str,
        system_prompt: str,
        message: str,
    ) -> str:
        """Run the tool-restricted dream agent; return its FINAL summary text.

        process_turn_text concatenates every assistant text segment across the turn,
        so its return value is `preamble + ...tool steps... + final summary` — the panel
        would then show the opening line ("I'll start by orienting myself…"), not the
        wrap-up. We instead watch the event stream and keep only the LAST contiguous
        text block (the text emitted after the agent's final tool call), which is the
        actual summary the prompt asks for.
        """
        from suzent.core.chat_processor import ChatProcessor
        from suzent.agent_manager import build_agent_config
        from suzent.core.stream_parser import TextChunk, ToolCall

        base = {
            "platform": "dream",
            "memory_enabled": False,
            "permission_mode": "auto",
            "interaction_profile": "headless",
            "suppress_environment_context": True,
            "tools": list(CONFIG.memory_dream_tools),
            "static_instructions": system_prompt,
        }
        if CONFIG.memory_consolidation_model:
            base["model"] = CONFIG.memory_consolidation_model
        cfg = build_agent_config(base, require_social_tool=False)

        last_block: list[str] = []
        _saw_text = False

        async def _on_event(event) -> None:
            nonlocal _saw_text
            if isinstance(event, TextChunk):
                # New text block begins right after a tool call — drop the prior block
                # so we end up holding only the final, post-tool summary.
                if not _saw_text:
                    last_block.clear()
                last_block.append(event.content)
                _saw_text = True
            elif isinstance(event, ToolCall):
                _saw_text = False  # next text starts a fresh (later) block

        full = await asyncio.wait_for(
            ChatProcessor().process_turn_text(
                chat_id=chat_id,
                user_id=CONFIG.user_id,
                message_content=message,
                config_override=cfg,
                on_event=_on_event,
            ),
            timeout=CONFIG.memory_consolidation_timeout_seconds,
        )
        # Prefer the last block; fall back to the full text if no boundaries were seen.
        text = self._clean_summary("".join(last_block).strip() or (full or "").strip())
        # Cap so the panel's LAST RESULT box stays readable (it's a status line, not a log).
        if len(text) > 600:
            text = text[:597].rstrip() + "…"
        return text
