"""
HostProcessRegistry
===================

In-process registry for background commands started by ShellCapability in host mode.

Each entry tracks:
- The Popen handle
- A temp file capturing combined stdout+stderr
- Exit code once finished

Process IDs are 12-character hex strings scoped per chat_id to prevent
cross-session access.

Thread safety: All mutations hold _lock (threading.Lock).
"""

from __future__ import annotations

import os
import secrets
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Dict, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

_ID_BYTES = 6  # → 12 hex chars
_MAX_ACTIVE_PROCESSES = 64
_MAX_RETAINED_PROCESSES = 256
_COMPLETED_PROCESS_TTL_SECONDS = 10 * 60
_MAX_OUTPUT_BYTES = 16 * 1024 * 1024


def _capture_output(stream: BinaryIO, output_file: Path, max_bytes: int) -> None:
    """Drain a child pipe while keeping its on-disk output strictly bounded."""
    marker = f"\n[output truncated: {max_bytes} byte capture limit reached]\n".encode()
    content_limit = max(0, max_bytes - len(marker))
    written = 0
    truncated = False
    with output_file.open("wb") as handle:
        while chunk := stream.read(64 * 1024):
            if truncated:
                continue
            available = content_limit - written
            if len(chunk) <= available:
                handle.write(chunk)
                written += len(chunk)
                handle.flush()
                continue
            if available > 0:
                handle.write(chunk[:available])
            handle.write(marker[: max_bytes - min(content_limit, max_bytes)])
            handle.flush()
            truncated = True
    stream.close()


@dataclass
class _HostProcess:
    process: subprocess.Popen
    output_file: Path
    chat_id: str
    exit_code: Optional[int] = field(default=None)
    created_at: float = field(default_factory=time.monotonic)
    completed_at: Optional[float] = field(default=None)
    capture_thread: threading.Thread | None = field(default=None)
    _file_handle = None  # kept open so Popen can write

    def poll(self) -> Optional[int]:
        """Refresh exit_code; returns it if done, else None."""
        if self.exit_code is None:
            rc = self.process.poll()
            if rc is not None:
                self.exit_code = rc
                self.completed_at = time.monotonic()
                if self.capture_thread is not None:
                    self.capture_thread.join(timeout=1)
        return self.exit_code

    def kill(self) -> bool:
        """Terminate the process tree. Returns True when a signal was sent."""
        if self.process.poll() is not None:
            return False
        try:
            import psutil

            parent = psutil.Process(self.process.pid)
            processes = [*parent.children(recursive=True), parent]
            for process in processes:
                process.terminate()
            _, alive = psutil.wait_procs(processes, timeout=5)
            for process in alive:
                process.kill()
            return True
        except Exception:
            try:
                self.process.kill()
                return True
            except Exception:
                return False

    def read_output(self, offset: int) -> tuple[str, int]:
        """Read output bytes from `offset`. Returns (text, new_offset)."""
        try:
            with open(self.output_file, "rb") as f:
                f.seek(offset)
                chunk = f.read()
            text = chunk.decode("utf-8", errors="replace")
            return text, offset + len(chunk)
        except Exception:
            return "", offset


class HostProcessRegistry:
    """Singleton registry for host-mode background processes."""

    _instance: Optional["HostProcessRegistry"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "HostProcessRegistry":
        with cls._instance_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._processes: Dict[str, _HostProcess] = {}
                inst._lock = threading.Lock()
                cls._instance = inst
        return cls._instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(
        self,
        chat_id: str,
        cmd: list[str],
        cwd: str,
        env: dict,
    ) -> str:
        """
        Spawn a background process and return its process_id.

        stdout and stderr are merged into a single temp file so the model
        can poll them with a single byte offset (same as CC's approach).
        """
        self.sweep()
        with self._lock:
            active_count = sum(
                1 for entry in self._processes.values() if entry.poll() is None
            )
        if active_count >= _MAX_ACTIVE_PROCESSES:
            raise RuntimeError(
                f"Host background process limit reached ({_MAX_ACTIVE_PROCESSES})."
            )

        process_id = secrets.token_hex(_ID_BYTES)

        # Temp file for merged output — persists until explicitly evicted.
        # A dedicated pipe-draining thread prevents a noisy command from growing
        # this file without bound or blocking once the capture limit is reached.
        out_fd, out_path = tempfile.mkstemp(prefix=f"suzent_proc_{process_id}_")
        out_file = Path(out_path)
        os.close(out_fd)

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                # Detach from our process group so it survives if the parent
                # thread exits, matching CC's non-blocking semantics.
                close_fds=True,
            )
        except Exception:
            out_file.unlink(missing_ok=True)
            raise

        assert proc.stdout is not None
        capture_thread = threading.Thread(
            target=_capture_output,
            args=(proc.stdout, out_file, _MAX_OUTPUT_BYTES),
            name=f"suzent-output-{process_id}",
            daemon=True,
        )
        capture_thread.start()

        entry = _HostProcess(
            process=proc,
            output_file=out_file,
            chat_id=chat_id,
            capture_thread=capture_thread,
        )

        with self._lock:
            self._processes[process_id] = entry

        logger.info(f"[HostProcessRegistry] started pid={proc.pid} id={process_id}")
        return process_id

    def poll(self, chat_id: str, process_id: str, offset: int) -> dict:
        """
        Returns dict with keys: output, offset, done, exit_code.
        Raises KeyError if process_id unknown or belongs to another chat.
        """
        entry = self._get(chat_id, process_id)
        exit_code = entry.poll()
        output, new_offset = entry.read_output(offset)
        return {
            "output": output,
            "offset": new_offset,
            "done": exit_code is not None,
            "exit_code": exit_code,
        }

    def sweep(self) -> int:
        """Evict expired completed entries and cap retained process metadata."""
        now = time.monotonic()
        removed: list[_HostProcess] = []
        with self._lock:
            completed: list[tuple[str, _HostProcess]] = []
            for process_id, entry in list(self._processes.items()):
                poll = getattr(entry, "poll", None)
                if poll is None or poll() is None:
                    continue
                completed.append((process_id, entry))
                completed_at = getattr(entry, "completed_at", None)
                if completed_at is not None and (
                    now - completed_at >= _COMPLETED_PROCESS_TTL_SECONDS
                ):
                    self._processes.pop(process_id, None)
                    removed.append(entry)

            overflow = len(self._processes) - _MAX_RETAINED_PROCESSES
            if overflow > 0:
                retained_completed = [
                    pair for pair in completed if pair[0] in self._processes
                ]
                retained_completed.sort(
                    key=lambda pair: getattr(pair[1], "completed_at", now) or now
                )
                for process_id, entry in retained_completed[:overflow]:
                    self._processes.pop(process_id, None)
                    removed.append(entry)

        for entry in removed:
            entry.output_file.unlink(missing_ok=True)
        if removed:
            logger.debug(
                f"[HostProcessRegistry] evicted {len(removed)} completed processes"
            )
        return len(removed)

    def shutdown(self) -> None:
        """Terminate every owned process and remove its temporary output."""
        with self._lock:
            entries = list(self._processes.items())
        for process_id, entry in entries:
            try:
                entry.kill()
                entry.poll()
            except Exception:
                pass
            with self._lock:
                self._processes.pop(process_id, None)
            entry.output_file.unlink(missing_ok=True)

    def kill(self, chat_id: str, process_id: str) -> bool:
        """Send SIGTERM. Returns True if signal was sent."""
        entry = self._get(chat_id, process_id)
        return entry.kill()

    def evict(self, chat_id: str, process_id: str) -> None:
        """Remove entry and delete temp output file."""
        with self._lock:
            entry = self._processes.get(process_id)
            if entry is not None and entry.chat_id == chat_id:
                self._processes.pop(process_id, None)
            else:
                entry = None
        if entry:
            entry.output_file.unlink(missing_ok=True)

    def evict_chat(self, chat_id: str) -> None:
        """Kill and evict all processes belonging to a chat session."""
        with self._lock:
            ids = [pid for pid, e in self._processes.items() if e.chat_id == chat_id]
        for pid in ids:
            try:
                self.kill(chat_id, pid)
            except Exception:
                pass
            self.evict(chat_id, pid)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get(self, chat_id: str, process_id: str) -> _HostProcess:
        with self._lock:
            entry = self._processes.get(process_id)
        if entry is None:
            raise KeyError(f"Unknown process_id: {process_id}")
        if entry.chat_id != chat_id:
            raise KeyError(f"process_id {process_id} does not belong to this session")
        return entry
