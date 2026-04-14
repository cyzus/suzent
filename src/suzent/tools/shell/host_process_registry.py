"""
HostProcessRegistry
===================

In-process registry for background processes started by BashTool in host mode.

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

_ID_BYTES = 6  # → 12 hex chars


@dataclass
class _HostProcess:
    process: subprocess.Popen
    output_file: Path
    chat_id: str
    exit_code: Optional[int] = field(default=None)
    _file_handle = None  # kept open so Popen can write

    def poll(self) -> Optional[int]:
        """Refresh exit_code; returns it if done, else None."""
        if self.exit_code is None:
            rc = self.process.poll()
            if rc is not None:
                self.exit_code = rc
        return self.exit_code

    def kill(self) -> bool:
        """Send SIGTERM (SIGKILL on Windows). Returns True if signal was sent."""
        if self.process.poll() is not None:
            return False
        try:
            self.process.terminate()
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
        process_id = secrets.token_hex(_ID_BYTES)

        # Temp file for merged output — persists until explicitly evicted
        out_fd, out_path = tempfile.mkstemp(prefix=f"suzent_proc_{process_id}_")
        out_file = Path(out_path)

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdout=out_fd,
                stderr=out_fd,
                # Detach from our process group so it survives if the parent
                # thread exits, matching CC's non-blocking semantics.
                close_fds=True,
            )
        except Exception:
            os.close(out_fd)
            out_file.unlink(missing_ok=True)
            raise
        finally:
            # Close our copy of the fd; the child still has its own
            try:
                os.close(out_fd)
            except OSError:
                pass

        entry = _HostProcess(
            process=proc,
            output_file=out_file,
            chat_id=chat_id,
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

    def kill(self, chat_id: str, process_id: str) -> bool:
        """Send SIGTERM. Returns True if signal was sent."""
        entry = self._get(chat_id, process_id)
        return entry.kill()

    def evict(self, chat_id: str, process_id: str) -> None:
        """Remove entry and delete temp output file."""
        with self._lock:
            entry = self._processes.pop(process_id, None)
        if entry and entry.chat_id == chat_id:
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
