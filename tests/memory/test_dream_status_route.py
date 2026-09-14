"""Dream status must tolerate storage failures without blocking the event loop."""

import errno
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from starlette.requests import Request

from suzent.core import dream_runner
from suzent.routes.memory_routes import get_dream_status


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/memory/dream/status"})


async def test_status_reads_run_off_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    event_loop_thread = threading.get_ident()
    payload = {"active": True, "available": True, "running": False}

    def status() -> dict[str, bool]:
        assert threading.get_ident() != event_loop_thread
        return payload

    monkeypatch.setattr(
        dream_runner, "get_active_dream_runner", lambda: SimpleNamespace(status=status)
    )
    response = await get_dream_status(_request())
    assert response.status_code == 200
    assert json.loads(response.body) == payload


@pytest.mark.parametrize("error_number", [errno.ETIMEDOUT, errno.EIO])
async def test_storage_failure_is_retryable(
    monkeypatch: pytest.MonkeyPatch, error_number: int
) -> None:
    status = Mock(
        side_effect=OSError(error_number, "storage failure", "/private/memory")
    )
    monkeypatch.setattr(
        dream_runner, "get_active_dream_runner", lambda: SimpleNamespace(status=status)
    )
    response = await get_dream_status(_request())
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert "/private/memory" not in response.body.decode()

    status.side_effect = None
    status.return_value = {"active": True, "available": True}
    recovered = await get_dream_status(_request())
    assert recovered.status_code == 200
    assert json.loads(recovered.body) == status.return_value


async def test_inactive_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dream_runner, "get_active_dream_runner", lambda: None)
    response = await get_dream_status(_request())
    assert response.status_code == 200
    assert json.loads(response.body)["active"] is False
