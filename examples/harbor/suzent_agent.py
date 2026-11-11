"""Harbor agent that runs Suzent headlessly inside a task container.

Use it with Harbor's import-path option::

    harbor run -d terminal-bench-sample@2.0 -m moonshot/kimi-k3 \
        --agent-import-path suzent_agent:SuzentAgent

Each trial installs Suzent from Git, runs the task with ``suzent run``, and
reports the token usage Suzent printed. See README.md beside this file.
"""

import json
import os
import shlex
from typing import override

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

_REPO_URL = "https://github.com/cyzus/suzent"
_SOURCE_DIR = "$HOME/suzent-src"
_SUZENT = f"{_SOURCE_DIR}/.venv/bin/suzent"
_PATH = 'export PATH="$HOME/.local/bin:$PATH"; '
_SUMMARY_FILE = "suzent.json"
_LOGS_DIR = "/logs/agent"

# Harbor names models by LiteLLM route. Suzent has no Fireworks provider, so a
# Fireworks route runs through its OpenAI-compatible one.
_FIREWORKS_PREFIX = "fireworks_ai/"
_FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"

_FORWARDED_ENV_SUFFIXES = ("_API_KEY", "_BASE_URL")

# Every tool definition is resent on each model call, so a terminal coding
# task runs with file and shell tools only. Override with the `tools` kwarg.
_CODING_TOOLS = (
    "ReadFileTool,WriteFileTool,EditFileTool,GlobTool,GrepTool,"
    "RunCommandTool,StartCommandTool,CheckCommandTool,StopCommandTool"
)


class SuzentAgent(BaseInstalledAgent):
    """Installs Suzent in the task container and runs one task with it."""

    def __init__(
        self,
        *args,
        tools: str | None = None,
        code_mode: bool | str = False,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._tools = tools or _CODING_TOOLS
        # Agent kwargs given on Harbor's command line arrive as strings.
        self._code_mode = str(code_mode).lower() in ("true", "1", "yes", "on")

    @staticmethod
    @override
    def name() -> str:
        return "suzent"

    @override
    def get_version_command(self) -> str | None:
        return f"{_SUZENT} --version"

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        await self.ensure_system_dependencies(environment, ("curl", "git"))
        # A bare fetch takes a branch, a tag or a commit, so one path pins all three.
        ref = shlex.quote(self._version or "main")
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                "curl -LsSf https://astral.sh/uv/install.sh | sh; "
                f"{_PATH}"
                f'mkdir -p "{_SOURCE_DIR}" && cd "{_SOURCE_DIR}" && '
                f"git init -q && git fetch -q --depth 1 {_REPO_URL} {ref} && "
                "git checkout -q FETCH_HEAD && "
                "uv sync --frozen --no-dev --python 3.12"
            ),
        )

    def _suzent_model(self) -> tuple[str, dict[str, str]]:
        """Translate Harbor's model name into Suzent's, plus the env it needs."""
        if not self.model_name:
            raise ValueError("Pass a model with -m, for example moonshot/kimi-k3")
        if self.model_name.startswith(_FIREWORKS_PREFIX):
            env = {"OPENAI_BASE_URL": _FIREWORKS_BASE_URL}
            if key := os.environ.get("FIREWORKS_API_KEY"):
                env["OPENAI_API_KEY"] = key
            return f"openai/{self.model_name.removeprefix(_FIREWORKS_PREFIX)}", env
        return self.model_name, {}

    @override
    @with_prompt_template
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        model, model_env = self._suzent_model()
        env = {
            key: value
            for key, value in os.environ.items()
            if key.endswith(_FORWARDED_ENV_SUFFIXES)
        }
        env.update(model_env)
        # A container has no OS keychain for Suzent's default secret store.
        env["SUZENT_SECRET_BACKEND"] = "encrypted_sqlite"

        # Pinning MODEL_OPTIONS makes the requested model the only one Suzent
        # may use, so a typo fails the run instead of falling back silently.
        settings = f"MODEL_OPTIONS:\n  - {json.dumps(model)}\nSANDBOX_ENABLED: false\n"
        await self.exec_as_agent(
            environment,
            command=(
                'mkdir -p "$HOME/.suzent/config" && '
                f"printf %s {shlex.quote(settings)} "
                '> "$HOME/.suzent/config/local.yaml"; '
                f"{_PATH}"
                f"{_SUZENT} run --json --permission-mode full_access "
                f"--model {shlex.quote(model)} --tools {shlex.quote(self._tools)} "
                f"{'--code-mode' if self._code_mode else '--no-code-mode'} "
                f"-- {shlex.quote(instruction)} "
                f"> {_LOGS_DIR}/{_SUMMARY_FILE} 2> {_LOGS_DIR}/suzent.log; "
                "status=$?; "
                f'cp -r "$HOME/.suzent/chats" {_LOGS_DIR}/chats 2>/dev/null; '
                "exit $status"
            ),
            env=env,
        )

    @override
    def populate_context_post_run(self, context: AgentContext) -> None:
        summary_path = self.logs_dir / _SUMMARY_FILE
        try:
            usage = json.loads(summary_path.read_text()).get("usage", {})
        except (OSError, json.JSONDecodeError):
            self.logger.warning(f"No usable Suzent summary at {summary_path}")
            return
        # Harbor counts cached tokens inside the input total, as Suzent does.
        context.n_input_tokens = usage.get("input_tokens")
        context.n_output_tokens = usage.get("output_tokens")
        context.n_cache_tokens = usage.get("cache_read_tokens")
