"""Process-state persistence and single-instance locking for the service."""

from __future__ import annotations

import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

from suzent.config import DEFAULT_PORT, RUNTIME_DIR
from suzent.service.models import ServiceProcessState

SERVICE_STATE_PATH = RUNTIME_DIR / "service.json"
SERVICE_LOCK_PATH = RUNTIME_DIR / "service.lock"
LOCK_STARTUP_GRACE_SECONDS = 10.0


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def read_process_state() -> ServiceProcessState | None:
    """Read a valid service state file, returning ``None`` for stale data."""
    raw = _read_json(SERVICE_STATE_PATH)
    if raw is None:
        return None
    try:
        state = ServiceProcessState(
            instance_id=str(raw["instance_id"]),
            control_token=str(raw["control_token"]),
            pid=int(raw["pid"]),
            process_created_at=float(raw["process_created_at"]),
            started_at=str(raw["started_at"]),
            port=int(raw["port"]),
            version=str(raw["version"]),
        )
        process = psutil.Process(state.pid)
        if abs(process.create_time() - state.process_created_at) > 1.0:
            return None
        if not process.is_running():
            return None
    except (KeyError, TypeError, ValueError, psutil.Error):
        return None
    return state


class ServiceInstanceLock:
    """Cross-platform file lock tied to an exact process identity."""

    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self.instance_id = secrets.token_hex(16)
        self._acquired = False

    def acquire(self) -> ServiceProcessState:
        """Acquire the service lock or raise when another instance is alive."""
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        for attempt in range(2):
            try:
                fd = os.open(
                    SERVICE_LOCK_PATH,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError:
                current = read_process_state()
                if current is not None:
                    raise RuntimeError(
                        f"Suzent service is already running with PID {current.pid}."
                    )
                try:
                    lock_age = time.time() - SERVICE_LOCK_PATH.stat().st_mtime
                except OSError:
                    lock_age = LOCK_STARTUP_GRACE_SECONDS
                if lock_age < LOCK_STARTUP_GRACE_SECONDS:
                    raise RuntimeError(
                        "Another Suzent service instance is still starting."
                    )
                if attempt == 0:
                    SERVICE_LOCK_PATH.unlink(missing_ok=True)
                    SERVICE_STATE_PATH.unlink(missing_ok=True)
                    continue
                raise RuntimeError("Could not replace a stale Suzent service lock.")

            # Imported here so the `suzent service` CLI commands, which reach
            # this module for process state, do not drag the HTTP route layer
            # and the database stack in behind it.
            from suzent.routes.system_routes import get_backend_version

            process = psutil.Process(os.getpid())
            state = ServiceProcessState(
                instance_id=self.instance_id,
                control_token=secrets.token_urlsafe(32),
                pid=process.pid,
                process_created_at=process.create_time(),
                started_at=datetime.now(timezone.utc).isoformat(),
                port=self.port,
                version=get_backend_version(),
            )
            try:
                os.write(fd, self.instance_id.encode("ascii"))
            finally:
                os.close(fd)
            temporary_state = SERVICE_STATE_PATH.with_name(
                f".{SERVICE_STATE_PATH.name}.{self.instance_id}.tmp"
            )
            temporary_state.write_text(
                json.dumps(state.to_dict(), indent=2), encoding="utf-8"
            )
            try:
                temporary_state.chmod(0o600)
            except OSError:
                pass
            temporary_state.replace(SERVICE_STATE_PATH)
            self._acquired = True
            return state
        raise RuntimeError("Could not acquire the Suzent service lock.")

    def release(self) -> None:
        """Release only files owned by this exact service instance."""
        if not self._acquired:
            return
        persisted = _read_json(SERVICE_STATE_PATH)
        if persisted and persisted.get("instance_id") == self.instance_id:
            SERVICE_STATE_PATH.unlink(missing_ok=True)
        try:
            lock_owner = SERVICE_LOCK_PATH.read_text(encoding="ascii")
        except OSError:
            lock_owner = None
        if lock_owner == self.instance_id:
            SERVICE_LOCK_PATH.unlink(missing_ok=True)
        self._acquired = False

    def __enter__(self) -> ServiceProcessState:
        return self.acquire()

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.release()
