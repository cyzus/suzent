"""Harbor agent that runs Suzent headlessly inside a task container.

Run Harbor from this folder so it can import the module::

    harbor run -d terminal-bench-sample@2.0 -m moonshot/kimi-k3 \
        --agent-import-path suzent_agent:SuzentAgent

Each trial installs Suzent from Git, runs the task with ``suzent run``, and
reports the token usage Suzent printed. See README.md beside this file.
"""

import os
from typing import override

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

import suzent_common as common


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
        self._tools = tools or common.CODING_TOOLS
        self._code_mode = common.as_bool(code_mode)

    @staticmethod
    @override
    def name() -> str:
        return "suzent"

    @override
    def get_version_command(self) -> str | None:
        return f"{common.SUZENT} --version"

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        await self.ensure_system_dependencies(environment, ("curl", "git"))
        await self.exec_as_agent(
            environment, command=common.install_command(self._version)
        )

    @override
    @with_prompt_template
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        route = common.resolve_model(self.model_name, os.environ)
        await self.exec_as_agent(
            environment,
            command=common.run_command(
                route, instruction, self._tools, self._code_mode
            ),
            env=common.run_env(route, os.environ),
        )

    @override
    def populate_context_post_run(self, context: AgentContext) -> None:
        usage = common.read_usage(self.logs_dir)
        if usage is None:
            self.logger.warning(f"No usable Suzent summary in {self.logs_dir}")
            return
        # Harbor counts cached tokens inside the input total, as Suzent does.
        context.n_input_tokens = usage.get("input_tokens")
        context.n_output_tokens = usage.get("output_tokens")
        context.n_cache_tokens = usage.get("cache_read_tokens")
