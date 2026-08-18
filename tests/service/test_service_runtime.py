from types import SimpleNamespace

import pytest

from suzent.service import runtime


class _Lock:
    released = False

    def __init__(self, port: int):
        self.port = port

    def acquire(self):
        return SimpleNamespace(control_token="token", pid=123)

    def release(self) -> None:
        self.released = True


def test_watchdog_recycle_exits_with_failure_for_supervisor_restart(monkeypatch):
    lock = _Lock(25314)
    monkeypatch.setattr(runtime, "ServiceInstanceLock", lambda port: lock)

    def fake_run_module(*_args, **_kwargs) -> None:
        monkeypatch.setenv("SUZENT_SERVICE_RECYCLE", "1")

    monkeypatch.setattr(runtime.runpy, "run_module", fake_run_module)

    with pytest.raises(SystemExit) as exc:
        runtime.run_service()

    assert exc.value.code == 75
    assert lock.released is True


def test_normal_shutdown_returns_successfully(monkeypatch):
    lock = _Lock(25314)
    monkeypatch.setattr(runtime, "ServiceInstanceLock", lambda port: lock)
    monkeypatch.setattr(runtime.runpy, "run_module", lambda *_args, **_kwargs: None)
    monkeypatch.delenv("SUZENT_SERVICE_RECYCLE", raising=False)

    runtime.run_service()

    assert lock.released is True
