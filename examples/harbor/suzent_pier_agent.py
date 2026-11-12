"""Pier agent that runs Suzent headlessly inside a task container.

Pier is the Harbor fork FrontierHarness Eval uses for its DeepSWE tasks, which
run without internet access. Run Pier from this folder::

    pier run -p /work/deep-swe/tasks/<task> -m moonshot/kimi-k3 \
        --agent-import-path suzent_pier_agent:SuzentAgent

Pier runs the install steps while the task image is built, when the network
is still available, and at run time lets the container reach only the hosts
this agent lists: the model provider.
"""

import os
from typing import override

from pier.agents.installed.base import BaseInstalledAgent, with_prompt_template
from pier.environments.base import BaseEnvironment
from pier.models.agent.context import AgentContext
from pier.models.agent.install import AgentInstallSpec, InstallStep
from pier.models.agent.network import NetworkAllowlist

import suzent_common as common


class SuzentAgent(BaseInstalledAgent):
    """Installs Suzent in the task image and runs one task with it."""

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

    def _environ(self) -> dict[str, str]:
        """The runner's environment, with the job's agent env taking priority."""
        return {**os.environ, **self._extra_env}

    @override
    def install_spec(self) -> AgentInstallSpec:
        return AgentInstallSpec(
            agent_name=self.name(),
            version=self._version,
            steps=[
                InstallStep(user="root", run=common.ROOT_INSTALL_COMMAND),
                InstallStep(user="agent", run=common.install_command(self._version)),
            ],
            verification_command=f"{common.SUZENT} --version",
        )

    @override
    def network_allowlist(self) -> NetworkAllowlist:
        host = common.resolve_model(self.model_name, self._environ()).host
        return NetworkAllowlist(domains=[host] if host else [])

    @override
    @with_prompt_template
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        route = common.resolve_model(self.model_name, self._environ())
        await self.exec_as_agent(
            environment,
            command=common.run_command(
                route, instruction, self._tools, self._code_mode
            ),
            env=common.run_env(route, self._environ()),
        )

    @override
    def populate_context_post_run(self, context: AgentContext) -> None:
        usage = common.read_usage(self.logs_dir)
        if usage is None:
            self.logger.warning(f"No usable Suzent summary in {self.logs_dir}")
            return
        context.n_input_tokens = usage.get("input_tokens")
        context.n_output_tokens = usage.get("output_tokens")
        context.n_cache_tokens = usage.get("cache_read_tokens")
