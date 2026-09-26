"""Track user-started background commands independently of chat turns."""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from suzent.sandbox import SandboxManager

from pydantic import BaseModel, Field

from suzent.logger import get_logger

logger = get_logger(__name__)
_OUTPUT_LIMIT = 8000
_HISTORY_LIMIT = 256


class BackgroundCommand(BaseModel):
    task_id: str
    command_id: str
    kind: Literal["shell"] = "shell"
    parent_chat_id: str
    chat_id: str = ""
    description: str
    tools_allowed: list[str] = Field(default_factory=list)
    mode: Literal["host", "sandbox"]
    status: Literal["running", "completed", "failed", "cancelled"] = "running"
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None
    result_summary: str = ""
    error: str | None = None
    exit_code: int | None = None
    offset: int = Field(default=0, exclude=True)
    consumed: bool = Field(default=False, exclude=True)
    notified: bool = Field(default=False, exclude=True)


class BackgroundCommands:
    def __init__(self) -> None:
        self._commands: dict[str, BackgroundCommand] = {}
        self._lock = threading.RLock()
        self._sandbox_managers: dict[str, SandboxManager] = {}
        self._worker: asyncio.Task[None] | None = None

    def register(
        self,
        chat_id: str,
        command_id: str,
        description: str,
        mode: Literal["host", "sandbox"],
        manager: SandboxManager | None = None,
    ) -> None:
        task = BackgroundCommand(
            task_id=f"shell_{command_id}",
            command_id=command_id,
            parent_chat_id=chat_id,
            description=description,
            mode=mode,
        )
        with self._lock:
            self._commands[task.task_id] = task
            if manager is not None:
                self._sandbox_managers[task.task_id] = manager
            finished = [
                key
                for key, value in self._commands.items()
                if value.status != "running" and (value.consumed or value.notified)
            ]
            for key in finished[: max(0, len(self._commands) - _HISTORY_LIMIT)]:
                del self._commands[key]
                self._sandbox_managers.pop(key, None)

    def list_tasks(self, chat_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            return [
                task.model_dump()
                for task in self._commands.values()
                if chat_id is None or task.parent_chat_id == chat_id
            ]

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            task = self._commands.get(task_id)
            return task.model_dump() if task else None

    def observe(
        self,
        chat_id: str,
        command_id: str,
        result: dict[str, Any],
        *,
        consumed: bool = False,
    ) -> None:
        with self._lock:
            task = self._commands.get(f"shell_{command_id}")
            if task is None or task.parent_chat_id != chat_id:
                return
            if result.get("done") and consumed:
                task.consumed = True
                if task.status == "running":
                    # A tool read may overlap the monitor; do not append its
                    # independently-offset output to the monitor buffer.
                    if result.get("output"):
                        task.result_summary = str(result["output"])[-_OUTPUT_LIMIT:]
                    result = {**result, "output": ""}
            if task.status != "running":
                return
            output = str(result.get("output") or "")
            task.result_summary = (task.result_summary + output)[-_OUTPUT_LIMIT:]
            task.offset = result.get("offset", task.offset)
            if result.get("done"):
                task.exit_code = result.get("exit_code")
                task.status = "completed" if task.exit_code == 0 else "failed"
                task.error = result.get("error") or (
                    f"Command exited with code {task.exit_code}"
                    if task.status == "failed"
                    else None
                )
                task.finished_at = datetime.now(UTC).isoformat()

    def suppress_wakeup(self, task_id: str) -> bool:
        with self._lock:
            task = self._commands.get(task_id)
            return bool(task and (task.consumed or task.status == "cancelled"))

    def cancel(self, chat_id: str, command_id: str) -> None:
        with self._lock:
            task = self._commands.get(f"shell_{command_id}")
            if task and task.parent_chat_id == chat_id:
                task.consumed = True
                task.status = "cancelled"
                task.error = None
                task.finished_at = datetime.now(UTC).isoformat()

    def remove_chat(self, chat_id: str) -> None:
        with self._lock:
            for key in list(self._commands):
                if self._commands[key].parent_chat_id == chat_id:
                    del self._commands[key]
                    self._sandbox_managers.pop(key, None)

    def _poll(self, task: BackgroundCommand) -> dict[str, Any]:
        if task.mode == "host":
            from suzent.tools.shell.host_process_registry import HostProcessRegistry

            return HostProcessRegistry().poll(
                task.parent_chat_id, task.command_id, task.offset
            )
        with self._lock:
            manager = self._sandbox_managers.get(task.task_id)
        if manager is None:
            raise KeyError(task.task_id)
        return manager.poll_process(task.parent_chat_id, task.command_id, task.offset)

    def _poll_running(self) -> None:
        with self._lock:
            tasks = [
                task.model_copy()
                for task in self._commands.values()
                if task.status == "running"
            ]
        for task in tasks:
            try:
                result = self._poll(task)
            except KeyError:
                result = {"done": True, "error": "Command is no longer available"}
            except Exception:  # noqa: BLE001 - backend failures must not stop other commands
                logger.warning(f"Could not check background command {task.task_id}")
                continue
            self.observe(task.parent_chat_id, task.command_id, result)

    def _notify_finished(self) -> None:
        from suzent.core.agent_inbox import enqueue_agent_message

        with self._lock:
            for task in self._commands.values():
                if (
                    task.status not in ("completed", "failed")
                    or task.consumed
                    or task.notified
                ):
                    continue
                try:
                    enqueue_agent_message(
                        message_id=f"shell-result-{task.command_id}",
                        target_chat_id=task.parent_chat_id,
                        sender_chat_id=None,
                        kind="background_task_result",
                        content=(
                            f"Background shell command {task.command_id} {task.status}.\n"
                            f"Task: {task.description}\nExit code: {task.exit_code}\n"
                            f"{task.error or ''}\nOutput (last {_OUTPUT_LIMIT} characters):\n"
                            f"{task.result_summary}\n"
                            "Use check_command for the retained full output if needed."
                        ),
                        payload={"task_id": task.task_id, "kind": "shell"},
                    )
                    task.notified = True
                except Exception:  # noqa: BLE001 - backend failures must not stop other commands
                    logger.warning(f"Could not enqueue completion for {task.task_id}")

    async def tick(self) -> None:
        await asyncio.to_thread(self._poll_running)
        self._notify_finished()

    async def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._run(), name="background_commands")

    async def _run(self) -> None:
        while True:
            await self.tick()
            await asyncio.sleep(1)

    async def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    def begin_stop(self, chat_id: str, command_id: str) -> bool:
        with self._lock:
            task = self._commands.get(f"shell_{command_id}")
            if task is None or task.parent_chat_id != chat_id:
                return False
            previous = task.consumed
            task.consumed = True
            return previous

    def finish_stop(
        self, chat_id: str, command_id: str, stopped: bool, previously_consumed: bool
    ) -> None:
        if stopped:
            self.cancel(chat_id, command_id)
            return
        with self._lock:
            task = self._commands.get(f"shell_{command_id}")
            if task and task.parent_chat_id == chat_id:
                task.consumed = previously_consumed

    async def stop_command(self, task_id: str) -> bool:
        task = self.get(task_id)
        if not task or task["status"] != "running":
            return False
        # Suppress completion before signalling the process, including racing polls.
        previous = self.begin_stop(task["parent_chat_id"], task["command_id"])
        stopped = False
        try:
            if task["mode"] == "host":
                from suzent.tools.shell.host_process_registry import HostProcessRegistry

                stopped = await asyncio.to_thread(
                    HostProcessRegistry().kill,
                    task["parent_chat_id"],
                    task["command_id"],
                )
            else:
                with self._lock:
                    manager = self._sandbox_managers[task_id]
                stopped = await asyncio.to_thread(
                    manager.kill_process, task["parent_chat_id"], task["command_id"]
                )
        except Exception:  # noqa: BLE001 - backend failures must not stop other commands
            logger.warning(f"Could not stop background command {task_id}")
        finally:
            self.finish_stop(
                task["parent_chat_id"], task["command_id"], stopped, previous
            )
        return stopped


_commands = BackgroundCommands()


def get_background_commands() -> BackgroundCommands:
    return _commands
