"""Offline tests for the Harbor and Pier agents in examples/harbor.

Neither runner is a Suzent dependency, so their imports are replaced with
stand-ins. The agents' shell commands are then really run in bash, against a
stub `suzent` executable, to check quoting, exit status and the files written.
"""

import asyncio
import importlib
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).parents[2]
_AGENT_DIR = _REPO / "examples" / "harbor"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="the agents' commands target a POSIX container shell",
)

# Prints its arguments as the run summary, records its environment and whether
# the usage proxy answered, and leaves a conversation file behind.
_STUB_SUZENT = """#!/bin/bash
mkdir -p "$HOME/.suzent/chats"
echo '{}' > "$HOME/.suzent/chats/chat-1.jsonl"
env > "$HOME/seen-env"
python3 - "$@" <<'PY'
import json, os, sys, time, urllib.request
proxy = None
for name in ("OPENAI_BASE_URL", "MOONSHOT_BASE_URL"):
    url = os.environ.get(name, "")
    if url.startswith("http://127.0.0.1:"):
        health = url.split("/", 3)[0] + "//" + url.split("/", 3)[2] + "/__usage_proxy_health"
        for _ in range(50):
            try:
                proxy = urllib.request.urlopen(health, timeout=1).read().decode()
                break
            except OSError:
                time.sleep(0.1)
print(json.dumps({"argv": sys.argv[1:], "proxy": proxy, "usage": {
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
    """Runs an agent's commands in a local bash with a throwaway HOME."""

    def __init__(self, home: Path):
        self.home = home
        self.commands: list[str] = []
        self.execute = True

    def run(self, command: str, env: dict[str, str] | None) -> _ExecResult:
        self.commands.append(command)
        if not self.execute:
            return _ExecResult(subprocess.CompletedProcess([], 0, "", ""))
        completed = subprocess.run(
            ["bash", "-c", f"set -o pipefail; {command}"],
            env={"PATH": os.environ["PATH"], "HOME": str(self.home), **(env or {})},
            capture_output=True,
            text=True,
        )
        return _ExecResult(completed)


class _FakeBaseInstalledAgent:
    """The slice of a runner's BaseInstalledAgent the Suzent agents rely on."""

    def __init__(
        self,
        logs_dir: Path,
        model_name: str | None = None,
        version: str | None = None,
        extra_env: dict[str, str] | None = None,
    ):
        self.logs_dir = logs_dir
        self.model_name = model_name
        self._version = version
        self._extra_env = dict(extra_env or {})
        self.logger = logging.getLogger("fake-runner")
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


@dataclass
class _InstallStep:
    run: str
    user: str = "agent"


@dataclass
class _AgentInstallSpec:
    agent_name: str
    steps: list[_InstallStep]
    version: str | None = None
    verification_command: str | None = None


@dataclass
class _NetworkAllowlist:
    domains: list[str] = field(default_factory=list)


def _runner_stubs(package: str) -> dict[str, dict[str, Any]]:
    return {
        package: {},
        f"{package}.agents": {},
        f"{package}.agents.installed": {},
        f"{package}.agents.installed.base": {
            "BaseInstalledAgent": _FakeBaseInstalledAgent,
            "with_prompt_template": lambda fn: fn,
        },
        f"{package}.environments": {},
        f"{package}.environments.base": {"BaseEnvironment": _LocalEnvironment},
        f"{package}.models": {},
        f"{package}.models.agent": {},
        f"{package}.models.agent.context": {"AgentContext": _FakeAgentContext},
        f"{package}.models.agent.install": {
            "AgentInstallSpec": _AgentInstallSpec,
            "InstallStep": _InstallStep,
        },
        f"{package}.models.agent.network": {"NetworkAllowlist": _NetworkAllowlist},
    }


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@dataclass
class _Kit:
    """The agent modules under test and the folders they write to."""

    common: types.ModuleType
    harbor: types.ModuleType
    pier: types.ModuleType
    logs_dir: Path
    home: Path

    def summary(self) -> dict[str, Any]:
        return json.loads((self.logs_dir / "suzent.json").read_text())

    def seen_env(self) -> dict[str, str]:
        lines = (self.home / "seen-env").read_text().splitlines()
        return dict(line.split("=", 1) for line in lines if "=" in line)

    def run(self, module: types.ModuleType, model: str | None, instruction: str, **kw):
        agent = module.SuzentAgent(self.logs_dir, model_name=model, **kw)
        context = _FakeAgentContext()
        asyncio.run(agent.run(instruction, _LocalEnvironment(self.home), context))
        agent.populate_context_post_run(context)
        return context


@pytest.fixture
def kit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _Kit:
    for package in ("harbor", "pier"):
        for name, attributes in _runner_stubs(package).items():
            module = types.ModuleType(name)
            vars(module).update(attributes)
            monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.syspath_prepend(str(_AGENT_DIR))
    for name in ("suzent_common", "suzent_agent", "suzent_pier_agent"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    common = importlib.import_module("suzent_common")
    harbor = importlib.import_module("suzent_agent")
    pier = importlib.import_module("suzent_pier_agent")

    logs_dir, home = tmp_path / "logs", tmp_path / "home"
    logs_dir.mkdir()
    home.mkdir()
    stub = tmp_path / "suzent"
    stub.write_text(_STUB_SUZENT)
    stub.chmod(0o755)
    monkeypatch.setattr(common, "LOGS_DIR", str(logs_dir))
    monkeypatch.setattr(common, "SUZENT", str(stub))
    monkeypatch.setattr(common, "PYTHON", sys.executable)
    monkeypatch.setattr(common, "SOURCE_DIR", str(_REPO))
    monkeypatch.setattr(common, "PROXY_PORT", _free_port())
    for key in [k for k in os.environ if k.endswith(("_API_KEY", "_BASE_URL"))]:
        monkeypatch.delenv(key)
    return _Kit(common, harbor, pier, logs_dir, home)


@pytest.fixture(params=["harbor", "pier"])
def agent_module(request: pytest.FixtureRequest, kit: _Kit) -> types.ModuleType:
    return getattr(kit, request.param)


def test_run_passes_the_instruction_through_the_shell_untouched(kit, agent_module):
    instruction = 'Fix `it\'s` $HOME "quoted"\n--json; rm -rf / # second line'

    kit.run(agent_module, "deepseek/deepseek-v4-flash", instruction)

    assert kit.summary()["argv"] == [
        "run",
        "--json",
        "--permission-mode",
        "full_access",
        "--model",
        "deepseek/deepseek-v4-flash",
        "--tools",
        kit.common.CODING_TOOLS,
        "--no-code-mode",
        "--keep-background-processes",
        "--",
        instruction,
    ]


def test_run_writes_settings_logs_and_the_conversation(kit, agent_module):
    kit.run(agent_module, "deepseek/deepseek-v4-flash", "Do the task")

    settings = (kit.home / ".suzent" / "config" / "local.yaml").read_text()
    assert settings == (
        'MODEL_OPTIONS:\n  - "deepseek/deepseek-v4-flash"\nSANDBOX_ENABLED: false\n'
    )
    assert (kit.logs_dir / "suzent.log").read_text() == "server noise\n"
    assert (kit.logs_dir / "chats" / "chat-1.jsonl").exists()


def test_run_reports_token_usage_to_the_runner(kit, agent_module):
    context = kit.run(agent_module, "deepseek/deepseek-v4-flash", "Do the task")

    assert context.n_input_tokens == 900
    assert context.n_output_tokens == 70
    assert context.n_cache_tokens == 400


def test_run_forwards_provider_credentials_only(kit, agent_module, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "stub-key")
    monkeypatch.setenv("UNRELATED_SETTING", "do-not-forward")

    kit.run(agent_module, "deepseek/deepseek-v4-flash", "Do the task")

    seen = kit.seen_env()
    assert seen["DEEPSEEK_API_KEY"] == "stub-key"
    assert seen["SUZENT_SECRET_BACKEND"] == "encrypted_sqlite"
    assert "UNRELATED_SETTING" not in seen


def test_the_tool_output_limit_is_passed_only_when_asked(kit, agent_module):
    kit.run(agent_module, "deepseek/deepseek-v4-flash", "Do the task")
    assert "--tool-output-limit" not in kit.summary()["argv"]


def test_other_providers_credentials_stay_out_of_the_container(
    kit, agent_module, monkeypatch
):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "stub-key")
    monkeypatch.setenv("OPENAI_API_KEY", "another-service")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "another-service")
    monkeypatch.setenv("SOME_BASE_URL", "https://internal.example")

    kit.run(agent_module, "deepseek/deepseek-v4-flash", "Do the task")

    seen = kit.seen_env()
    assert seen["DEEPSEEK_API_KEY"] == "stub-key"
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "SOME_BASE_URL"):
        assert name not in seen


@pytest.mark.parametrize(
    ("model", "variable"),
    [
        ("gemini/gemini-3-pro", "GOOGLE_API_KEY"),
        ("zai/glm-5.2", "ZHIPUAI_API_KEY"),
        ("zhipuai/glm-5.2", "ZAI_API_KEY"),
    ],
)
def test_provider_credential_aliases_are_forwarded(
    kit, agent_module, monkeypatch, model, variable
):
    monkeypatch.setenv(variable, "alias-stub")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "another-service")

    kit.run(agent_module, model, "Do the task")

    seen = kit.seen_env()
    assert seen[variable] == "alias-stub"
    assert "ANTHROPIC_API_KEY" not in seen


def test_fireworks_route_does_not_leak_an_unrelated_openai_key(
    kit, agent_module, monkeypatch
):
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw-stub")
    monkeypatch.setenv("OPENAI_API_KEY", "another-service")

    kit.run(
        agent_module, "fireworks_ai/accounts/fireworks/models/kimi-k3", "Do the task"
    )

    seen = kit.seen_env()
    assert seen["OPENAI_API_KEY"] == "fw-stub"
    assert "FIREWORKS_API_KEY" not in seen


def test_a_provider_suzent_cannot_redirect_runs_without_the_proxy(kit, agent_module):
    kit.run(agent_module, "deepseek/deepseek-v4-flash", "Do the task")

    assert kit.summary()["proxy"] is None
    assert not (kit.logs_dir / "usage-proxy.log").exists()


def test_fireworks_route_runs_through_the_proxy_and_openai_provider(
    kit, agent_module, monkeypatch
):
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw-stub")

    kit.run(
        agent_module, "fireworks_ai/accounts/fireworks/models/kimi-k3", "Do the task"
    )

    summary = kit.summary()
    assert "openai/accounts/fireworks/models/kimi-k3" in summary["argv"]
    assert summary["proxy"] == "ok"
    seen = kit.seen_env()
    port = kit.common.PROXY_PORT
    assert seen["OPENAI_BASE_URL"] == f"http://127.0.0.1:{port}/inference/v1"
    assert seen["OPENAI_API_KEY"] == "fw-stub"
    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", port)) != 0, "proxy still running"


def test_moonshot_route_keeps_its_provider_and_uses_the_proxy(kit, agent_module):
    kit.run(agent_module, "moonshot/kimi-k3", "Do the task")

    assert "moonshot/kimi-k3" in kit.summary()["argv"]
    assert kit.summary()["proxy"] == "ok"
    assert kit.seen_env()["MOONSHOT_BASE_URL"] == (
        f"http://127.0.0.1:{kit.common.PROXY_PORT}/v1"
    )


def test_the_official_openai_endpoint_is_never_proxied(kit, agent_module):
    kit.run(agent_module, "openai/gpt-test", "Do the task")

    assert kit.summary()["proxy"] is None
    assert "OPENAI_BASE_URL" not in kit.seen_env()


def test_a_custom_openai_endpoint_goes_through_the_proxy(
    kit, agent_module, monkeypatch
):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.example/v1")

    kit.run(agent_module, "openai/gpt-test", "Do the task")

    assert kit.summary()["proxy"] == "ok"
    assert kit.seen_env()["OPENAI_BASE_URL"] == (
        f"http://127.0.0.1:{kit.common.PROXY_PORT}/v1"
    )


def test_a_failed_run_still_saves_its_evidence_and_fails(kit, agent_module):
    stub = Path(kit.common.SUZENT)
    stub.write_text(stub.read_text().replace("exit 0", "exit 1"))

    with pytest.raises(RuntimeError, match="exit 1"):
        kit.run(agent_module, "moonshot/kimi-k3", "Do the task")

    assert (kit.logs_dir / "chats" / "chat-1.jsonl").exists()
    assert kit.summary()["usage"]


def test_tools_and_code_mode_kwargs_reach_the_command(kit, agent_module):
    kit.run(
        agent_module,
        "deepseek/deepseek-v4-flash",
        "Do the task",
        tools="ReadFileTool,WebSearchTool",
        code_mode="true",
    )

    argv = kit.summary()["argv"]
    assert argv[argv.index("--tools") + 1] == "ReadFileTool,WebSearchTool"
    assert "--code-mode" in argv


def test_run_requires_a_model(kit, agent_module):
    with pytest.raises(ValueError, match="-m"):
        kit.run(agent_module, None, "Do the task")


def test_missing_summary_leaves_the_context_empty(kit, agent_module):
    agent = agent_module.SuzentAgent(kit.logs_dir, model_name="m/x")
    context = _FakeAgentContext()

    agent.populate_context_post_run(context)

    assert context.n_input_tokens is None


def test_harbor_install_fetches_the_pinned_version(kit):
    agent = kit.harbor.SuzentAgent(
        kit.logs_dir, model_name="m/x", version="v0.25.0; echo hacked"
    )
    environment = _LocalEnvironment(kit.home)
    environment.execute = False

    asyncio.run(agent.install(environment))

    assert agent.system_dependencies == ("curl", "git")
    command = environment.commands[0]
    assert "git fetch -q --depth 1 https://github.com/cyzus/suzent " in command
    assert "'v0.25.0; echo hacked'" in command
    assert "uv sync --frozen --no-dev" in command


def test_pier_installs_at_build_time_as_root_then_agent(kit):
    agent = kit.pier.SuzentAgent(kit.logs_dir, model_name="m/x", version="abc123")

    spec = agent.install_spec()

    assert spec.agent_name == "suzent"
    assert spec.version == "abc123"
    assert [step.user for step in spec.steps] == ["root", "agent"]
    assert "apt-get install -y curl git" in spec.steps[0].run
    assert "git fetch -q --depth 1 https://github.com/cyzus/suzent abc123" in (
        spec.steps[1].run
    )


@pytest.mark.parametrize(
    ("model", "domains"),
    [
        ("fireworks_ai/accounts/fireworks/models/kimi-k3", ["api.fireworks.ai"]),
        ("moonshot/kimi-k3", ["api.moonshot.cn"]),
        ("openai/gpt-test", ["api.openai.com"]),
        ("deepseek/deepseek-v4-flash", []),
    ],
)
def test_pier_allows_only_the_model_provider(kit, model, domains):
    agent = kit.pier.SuzentAgent(kit.logs_dir, model_name=model)

    assert agent.network_allowlist().domains == domains


def test_pier_job_env_overrides_the_provider_endpoint(kit):
    agent = kit.pier.SuzentAgent(
        kit.logs_dir,
        model_name="moonshot/kimi-k3",
        extra_env={"MOONSHOT_BASE_URL": "https://gateway.example/v1"},
    )

    assert agent.network_allowlist().domains == ["gateway.example"]
