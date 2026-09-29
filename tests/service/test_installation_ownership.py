from pathlib import Path

import pytest

from suzent.service import manager as module
from suzent.service.manager import ServiceController
from suzent.service.models import ServiceProcessState
from suzent.service.platforms.windows import WindowsServiceManager


@pytest.mark.parametrize("foreign_registry", [False, True])
def test_owned_definition_also_requires_owned_autostart(
    monkeypatch, tmp_path: Path, foreign_registry: bool
) -> None:
    definition = tmp_path / "service.pyw"
    python = tmp_path / "current/.venv/Scripts/python.exe"
    definition.write_text(f"PYTHON = {str(python)!r}\n")
    monkeypatch.setattr(
        WindowsServiceManager, "definition_path", property(lambda self: definition)
    )
    monkeypatch.setattr(
        WindowsServiceManager, "python_executable", property(lambda self: python)
    )
    monkeypatch.setattr(
        WindowsServiceManager, "_autostart_command", lambda self: "owned command"
    )
    monkeypatch.setattr(
        WindowsServiceManager,
        "_read_autostart",
        lambda self: "foreign command" if foreign_registry else "owned command",
    )
    if foreign_registry:
        with pytest.raises(RuntimeError):
            WindowsServiceManager().assert_definition_owned()
    else:
        WindowsServiceManager().assert_definition_owned()


@pytest.mark.parametrize("action", ["install", "uninstall", "start", "stop", "restart"])
def test_stopped_foreign_definition_cannot_be_controlled(
    monkeypatch, tmp_path: Path, action: str
) -> None:
    definition = tmp_path / "service.pyw"
    definition.write_text(
        f"PYTHON = {str(tmp_path / 'other/.venv/Scripts/python.exe')!r}\n"
    )
    monkeypatch.setattr(
        WindowsServiceManager, "definition_path", property(lambda self: definition)
    )
    monkeypatch.setattr(
        WindowsServiceManager,
        "python_executable",
        property(lambda self: tmp_path / "current/.venv/Scripts/python.exe"),
    )
    monkeypatch.setattr(
        WindowsServiceManager, "_read_autostart", lambda self: "registered"
    )
    monkeypatch.setattr(module, "read_process_state", lambda: None)
    controller = ServiceController(WindowsServiceManager())
    with pytest.raises(RuntimeError, match="another or unknown"):
        getattr(controller, action)()
    assert "other" in definition.read_text()
    assert controller.status().error is not None


@pytest.mark.parametrize(
    "owned,parent_owned,created",
    [(True, False, 10), (False, True, 10), (False, False, 10), (True, False, 20)],
)
def test_legacy_state_requires_exact_venv_process_identity(
    monkeypatch, tmp_path: Path, owned: bool, parent_owned: bool, created: int
) -> None:
    root = tmp_path.resolve()
    launcher = root / ".venv/Scripts/python.exe"

    class Process:
        def __init__(self, matches: bool, timestamp: int):
            self.matches = matches
            self.timestamp = timestamp

        def create_time(self) -> float:
            return float(self.timestamp)

        def cmdline(self) -> list[str]:
            return ["python", "-m", "suzent.service.runtime"]

        def exe(self) -> str:
            return str(launcher if self.matches else root / "shared-uv/python.exe")

        def parent(self) -> "Process":
            return Process(parent_owned, 9)

    state = ServiceProcessState(
        instance_id="id",
        control_token="token",
        pid=42,
        process_created_at=10,
        started_at="2026-01-01T00:00:00+00:00",
        port=25314,
        version="0.14.0",
    )
    monkeypatch.setattr(module.psutil, "Process", lambda pid: Process(owned, created))
    assert ServiceController._owns_legacy_process(state, root) == (
        (owned or parent_owned) and created == 10
    )
