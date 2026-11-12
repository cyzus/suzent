"""Offline tests for the Harbor agent in examples/harbor.

Harbor is not a Suzent dependency, so its three imports are replaced with
stand-ins. The agent's shell commands are then really run in bash, against a
stub `suzent` executable, to check quoting, exit status and the files written.
"""

import asyncio
import importlib.util
import json
import logging
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

_AGENT_FILE = Path(__file__).parents[2] / "examples" / "harbor" / "suzent_agent.py"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="the agent's commands target a POSIX container shell",
)

# Prints its arguments as the run summary, records its environment, and leaves
# a conversation file behind, as the real command does.
_STUB_SUZENT = """#!/bin/bash
mkdir -p "$HOME/.suzent/chats"
echo '{}' > "$HOME/.suzent/chats/chat-1.jsonl"
env > "$HOME/seen-env"
python3 - "$@" <<'PY'
import json, sys
print(json.dumps({"argv": sys.argv[1:], "usage": {
    "input_tokens": 900, "output_tokens": 70, "cache_read_tokens": 400}}))
PY
echo "server noise" >&2
exit 0
"""


class _ExecResult:
    def __init__(self, completed: subprocess.CompletedProcess[str]):
        self.return_code = completed.returncode
        self.stdout = completed.stdout
        self.stderr = completed.stderr


class _LocalEnvironment:
    """Runs the agent's commands in a local bash with a throwaway HOME."""

    def __init__(self, home: Path):
        self.home = home
        self.commands: list[str] = []

    def run(self, command: str, env: dict[str, str] | None) -> _ExecResult:
        self.commands.append(command)
        completed = subprocess.run(
            ["bash", "-c", f"set -o pipefail; {command}"],
            env={"PATH": os.environ["PATH"], "HOME": str(self.home), **(env or {})},
            capture_output=True,
            text=True,
        )
        return _ExecResult(completed)


class _FakeBaseInstalledAgent:
    """The slice of Harbor's BaseInstalledAgent the Suzent agent relies on."""

    def __init__(
        self, logs_dir: Path, model_name: str | None = None, version: str | None = None
    ):
        self.logs_dir = logs_dir
        self.model_name = model_name
        self._version = version
        self.logger = logging.getLogger("fake-harbor")
        self.system_dependencies: tuple[str, ...] = ()

    async def ensure_system_dependencies(
        self, environment: _LocalEnvironment, packages: tuple[str, ...]
    ) -> None:
        self.system_dependencies = packages

    async def exec_as_agent(
        self,
        environment: _LocalEnvironment,
        command: str,
        env: dict[str, str] | None = None,
    ) -> _ExecResult:
        result = environment.run(command, env)
        if result.return_code != 0:
            raise RuntimeError(f"exit {result.return_code}: {result.stderr}")
        return result


class _FakeAgentContext:
    n_input_tokens: int | None = None
    n_output_tokens: int | None = None
    n_cache_tokens: int | None = None


@pytest.fixture
def agent_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> types.ModuleType:
    """The agent module, loaded against stand-in Harbor modules."""
    stubs: dict[str, dict[str, Any]] = {
        "harbor": {},
        "harbor.agents": {},
        "harbor.agents.installed": {},
        "harbor.agents.installed.base": {
            "BaseInstalledAgent": _FakeBaseInstalledAgent,
            "with_prompt_template": lambda fn: fn,
        },
        "harbor.environments": {},
        "harbor.environments.base": {"BaseEnvironment": _LocalEnvironment},
        "harbor.models": {},
        "harbor.models.agent": {},
        "harbor.models.agent.context": {"AgentContext": _FakeAgentContext},
    }
    for name, attributes in stubs.items():
        module = types.ModuleType(name)
        vars(module).update(attributes)
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location(
        "suzent_agent_under_test", _AGENT_FILE
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    stub = tmp_path / "suzent"
    stub.write_text(_STUB_SUZENT)
    stub.chmod(0o755)
    monkeypatch.setattr(module, "_LOGS_DIR", str(logs_dir))
    monkeypatch.setattr(module, "_SUZENT", str(stub))
    for key in [k for k in os.environ if k.endswith(("_API_KEY", "_BASE_URL"))]:
        monkeypatch.delenv(key)
    return module


@pytest.fixture
def home(tmp_path: Path) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    return path


def _run(module: types.ModuleType, home: Path, model: str | None, instruction: str):
    logs_dir = Path(module._LOGS_DIR)
    agent = module.SuzentAgent(logs_dir, model_name=model)
    environment = _LocalEnvironment(home)
    context = _FakeAgentContext()
    asyncio.run(agent.run(instruction, environment, context))
    agent.populate_context_post_run(context)
    return agent, environment, context


def test_run_passes_the_instruction_through_the_shell_untouched(agent_module, home):
    instruction = 'Fix `it\'s` $HOME "quoted"\n--json; rm -rf / # second line'

    _run(agent_module, home, "moonshot/kimi-k3", instruction)

    summary = json.loads((Path(agent_module._LOGS_DIR) / "suzent.json").read_text())
    assert summary["argv"] == [
        "run",
        "--json",
        "--permission-mode",
        "full_access",
        "--model",
        "moonshot/kimi-k3",
        "--tools",
        agent_module._CODING_TOOLS,
        "--no-code-mode",
        "--",
        instruction,
    ]


def test_run_writes_settings_logs_and_the_conversation(agent_module, home):
    _run(agent_module, home, "moonshot/kimi-k3", "Do the task")

    settings = (home / ".suzent" / "config" / "local.yaml").read_text()
    assert (
        settings == 'MODEL_OPTIONS:\n  - "moonshot/kimi-k3"\nSANDBOX_ENABLED: false\n'
    )
    logs_dir = Path(agent_module._LOGS_DIR)
    assert (logs_dir / "suzent.log").read_text() == "server noise\n"
    assert (logs_dir / "chats" / "chat-1.jsonl").exists()


def test_run_reports_token_usage_to_harbor(agent_module, home):
    _, _, context = _run(agent_module, home, "moonshot/kimi-k3", "Do the task")

    assert context.n_input_tokens == 900
    assert context.n_output_tokens == 70
    assert context.n_cache_tokens == 400


def test_run_forwards_provider_credentials_only(agent_module, home, monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "stub-key")
    monkeypatch.setenv("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1")
    monkeypatch.setenv("UNRELATED_SETTING", "do-not-forward")

    _run(agent_module, home, "moonshot/kimi-k3", "Do the task")

    seen = dict(
        line.split("=", 1) for line in (home / "seen-env").read_text().splitlines()
    )
    assert seen["MOONSHOT_API_KEY"] == "stub-key"
    assert seen["MOONSHOT_BASE_URL"] == "https://api.moonshot.ai/v1"
    assert seen["SUZENT_SECRET_BACKEND"] == "encrypted_sqlite"
    assert "UNRELATED_SETTING" not in seen


def test_fireworks_route_runs_through_the_openai_compatible_provider(
    agent_module, home, monkeypatch
):
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw-stub")

    _run(
        agent_module,
        home,
        "fireworks_ai/accounts/fireworks/models/kimi-k3",
        "Do the task",
    )

    summary = json.loads((Path(agent_module._LOGS_DIR) / "suzent.json").read_text())
    assert "openai/accounts/fireworks/models/kimi-k3" in summary["argv"]
    seen = (home / "seen-env").read_text()
    assert "OPENAI_BASE_URL=https://api.fireworks.ai/inference/v1" in seen
    assert "OPENAI_API_KEY=fw-stub" in seen


def test_a_failed_run_still_saves_its_evidence_and_fails(agent_module, home):
    stub = Path(agent_module._SUZENT)
    stub.write_text(stub.read_text().replace("exit 0", "exit 1"))

    with pytest.raises(RuntimeError, match="exit 1"):
        _run(agent_module, home, "moonshot/kimi-k3", "Do the task")

    logs_dir = Path(agent_module._LOGS_DIR)
    assert (logs_dir / "chats" / "chat-1.jsonl").exists()
    assert json.loads((logs_dir / "suzent.json").read_text())["usage"]


def test_tools_kwarg_replaces_the_coding_tool_set(agent_module, home):
    agent = agent_module.SuzentAgent(
        Path(agent_module._LOGS_DIR),
        model_name="moonshot/kimi-k3",
        tools="ReadFileTool,WebSearchTool",
    )

    asyncio.run(agent.run("Do the task", _LocalEnvironment(home), _FakeAgentContext()))

    summary = json.loads((Path(agent_module._LOGS_DIR) / "suzent.json").read_text())
    argv = summary["argv"]
    assert argv[argv.index("--tools") + 1] == "ReadFileTool,WebSearchTool"


@pytest.mark.parametrize(
    ("value", "flag"),
    [("true", "--code-mode"), (True, "--code-mode"), ("false", "--no-code-mode")],
)
def test_code_mode_kwarg_selects_the_flag(agent_module, home, value, flag):
    agent = agent_module.SuzentAgent(
        Path(agent_module._LOGS_DIR), model_name="moonshot/kimi-k3", code_mode=value
    )

    asyncio.run(agent.run("Do the task", _LocalEnvironment(home), _FakeAgentContext()))

    summary = json.loads((Path(agent_module._LOGS_DIR) / "suzent.json").read_text())
    assert flag in summary["argv"]


def test_run_requires_a_model(agent_module, home):
    with pytest.raises(ValueError, match="-m"):
        _run(agent_module, home, None, "Do the task")


def test_missing_summary_leaves_the_context_empty(agent_module, tmp_path):
    agent = agent_module.SuzentAgent(Path(agent_module._LOGS_DIR), model_name="m/x")
    context = _FakeAgentContext()

    agent.populate_context_post_run(context)

    assert context.n_input_tokens is None


def test_install_fetches_the_pinned_version(agent_module, home):
    agent = agent_module.SuzentAgent(
        Path(agent_module._LOGS_DIR), model_name="m/x", version="v0.25.0; echo hacked"
    )
    environment = _LocalEnvironment(home)
    environment.run = lambda command, env: (  # type: ignore[method-assign]
        environment.commands.append(command)
        or _ExecResult(subprocess.CompletedProcess([], 0, "", ""))
    )

    asyncio.run(agent.install(environment))

    assert agent.system_dependencies == ("curl", "git")
    command = environment.commands[0]
    assert "git fetch -q --depth 1 https://github.com/cyzus/suzent " in command
    assert "'v0.25.0; echo hacked'" in command
    assert "uv sync --frozen --no-dev" in command
