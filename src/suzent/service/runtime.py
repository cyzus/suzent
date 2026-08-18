"""Foreground entry point used by operating-system service managers."""

from __future__ import annotations

import os
import runpy

from suzent.config import DEFAULT_PORT
from suzent.logger import logger
from suzent.service.state import ServiceInstanceLock


def run_service() -> None:
    """Run the normal Suzent server under a service lifetime lock."""
    os.environ["SUZENT_RUN_MODE"] = "service"
    os.environ.setdefault("SUZENT_HOST", "127.0.0.1")
    os.environ.setdefault("SUZENT_PORT", str(DEFAULT_PORT))
    port = int(os.environ["SUZENT_PORT"])

    lock = ServiceInstanceLock(port=port)
    try:
        state = lock.acquire()
    except RuntimeError as exc:
        logger.error("Suzent service could not acquire its instance lock: {}", exc)
        raise SystemExit(73) from exc
    os.environ["SUZENT_SERVICE_CONTROL_TOKEN"] = state.control_token
    logger.info("Suzent service starting with PID {} on port {}", state.pid, port)
    try:
        runpy.run_module("suzent.server", run_name="__main__")
    finally:
        lock.release()
        logger.info("Suzent service stopped")
    if os.environ.pop("SUZENT_SERVICE_RECYCLE", "") == "1":
        raise SystemExit(75)


if __name__ == "__main__":
    run_service()
