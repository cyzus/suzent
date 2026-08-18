from __future__ import annotations

import io
from dataclasses import dataclass

from suzent.tools.shell import host_process_registry as registry_module
from suzent.tools.shell.host_process_registry import HostProcessRegistry


@dataclass
class FakeProcess:
    output_file: object
    completed_at: float | None
    chat_id: str = "chat"
    killed: bool = False

    def poll(self):
        return 0 if self.completed_at is not None else None

    def kill(self):
        self.killed = True
        return True


def test_sweep_removes_expired_completed_processes(tmp_path, monkeypatch):
    registry = HostProcessRegistry()
    registry._processes.clear()
    output = tmp_path / "process.log"
    output.write_text("done", encoding="utf-8")
    registry._processes["completed"] = FakeProcess(output, completed_at=10.0)
    monkeypatch.setattr(registry_module.time, "monotonic", lambda: 1000.0)
    monkeypatch.setattr(registry_module, "_COMPLETED_PROCESS_TTL_SECONDS", 100)

    assert registry.sweep() == 1
    assert registry._processes == {}
    assert not output.exists()


def test_shutdown_kills_active_process_and_removes_output(tmp_path):
    registry = HostProcessRegistry()
    registry._processes.clear()
    output = tmp_path / "process.log"
    output.write_text("running", encoding="utf-8")
    process = FakeProcess(output, completed_at=None)
    registry._processes["active"] = process

    registry.shutdown()

    assert process.killed is True
    assert registry._processes == {}
    assert not output.exists()


def test_output_capture_is_strictly_bounded(tmp_path):
    output = tmp_path / "bounded.log"
    stream = io.BytesIO(b"x" * 10_000)

    registry_module._capture_output(stream, output, max_bytes=1024)

    captured = output.read_bytes()
    assert len(captured) <= 1024
    assert b"output truncated" in captured
