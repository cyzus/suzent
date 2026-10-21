"""Cancellable outbound login jobs; credentials stay with each agent's CLI."""

import asyncio
import os
import shutil
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

from suzent.acp.client import ACPClient
from suzent.acp.terminal_login import run_terminal_login, terminal_available

if TYPE_CHECKING:
    from suzent.acp.manager import ACPManager


class LoginState(BaseModel):
    attempt: int = 0
    status: Literal[
        "idle",
        "starting",
        "authenticating",
        "terminal",
        "verifying",
        "ready",
        "failed",
        "cancelled",
    ] = "idle"
    error: Literal["unavailable", "failed", "timeout", "verification_failed"] | None = (
        None
    )
    result: dict[str, Any] | None = None


class ACPLogins:
    def __init__(self, manager: "ACPManager") -> None:
        self.manager = manager
        self.states: dict[str, LoginState] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.attempts: dict[str, int] = {}

    def state(self, agent_id: str) -> LoginState:
        return self.states.get(agent_id, LoginState()).model_copy(
            update={"attempt": self.attempts.get(agent_id, 0)}
        )

    def start(
        self, agent_id: str, cwd: str, method_id: str | None = None
    ) -> LoginState:
        agent = self.manager.registry.get(agent_id)
        if not agent.available:
            raise ValueError("Agent is not installed")
        if agent_id in self.tasks and not self.tasks[agent_id].done():
            return self.state(agent_id)
        if sum(not task.done() for task in self.tasks.values()) >= 4:
            raise ValueError("Too many active sign-ins")
        self.states[agent_id] = LoginState(status="starting")
        self.attempts[agent_id] = self.attempts.get(agent_id, 0) + 1
        self.tasks[agent_id] = asyncio.create_task(self._run(agent_id, cwd, method_id))
        return self.state(agent_id)

    async def cancel(self, agent_id: str) -> None:
        task = self.tasks.get(agent_id)
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self.states[agent_id] = LoginState(status="cancelled")

    async def shutdown(self) -> None:
        await asyncio.gather(*(self.cancel(key) for key in list(self.tasks)))

    async def _run(self, agent_id: str, cwd: str, method_id: str | None) -> None:
        try:
            async with asyncio.timeout(300):
                agent = self.manager.registry.get(agent_id)
                command: list[str] | None = None
                env = {**os.environ, **agent.env}
                if agent_id == "claude-code":
                    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
                        env.pop(key, None)
                client = ACPClient(agent.command, cwd=agent.cwd or cwd, env=agent.env)
                client.terminal_auth = terminal_available()
                try:
                    await client.start()
                    init = await client.initialize()
                    methods = [
                        item
                        for item in (init.get("authMethods") or [])
                        if isinstance(item, dict) and isinstance(item.get("id"), str)
                    ]
                    selected = (
                        next(
                            (item for item in methods if item["id"] == method_id), None
                        )
                        if method_id
                        else next(
                            (
                                item
                                for kind in ("agent", "terminal")
                                for item in methods
                                if item.get("type", "agent") == kind
                                and (kind != "terminal" or client.terminal_auth)
                            ),
                            None,
                        )
                    )
                    if method_id and selected is None:
                        raise ValueError("Unknown authentication method")
                    if (
                        selected is not None
                        and selected.get("type", "agent") == "agent"
                    ):
                        self.states[agent_id] = LoginState(status="authenticating")
                        await client.authenticate(selected["id"])
                        self.states[agent_id] = LoginState(status="verifying")
                        await client.new_session(cwd)
                        previous = self.manager._authenticated.pop(agent_id, None)
                        self.manager._authenticated[agent_id] = (client, init)
                        if previous:
                            await previous[0].close()
                        client = None
                    elif selected is not None and selected.get("type") == "terminal":
                        args = selected.get("args", [])
                        overrides = selected.get("env", {})
                        if (
                            not isinstance(args, list)
                            or not all(isinstance(item, str) for item in args)
                            or not isinstance(overrides, dict)
                            or not all(
                                isinstance(k, str) and isinstance(v, str)
                                for k, v in overrides.items()
                            )
                        ):
                            raise ValueError("Invalid terminal method")
                        command = [*agent.command, *args]
                        env.update(overrides)
                    elif selected is None and agent.login_command:
                        command = agent.login_command
                    else:
                        self.states[agent_id] = LoginState(
                            status="failed", error="unavailable"
                        )
                        return
                finally:
                    if client is not None:
                        await client.close()
                if command is not None:
                    if not terminal_available():
                        self.states[agent_id] = LoginState(
                            status="failed", error="unavailable"
                        )
                        return
                    self.states[agent_id] = LoginState(status="terminal")
                    await run_terminal_login(command, agent.cwd or cwd, env)
                    # A pre-login cached connection must not mask a failed login.
                    previous = self.manager._authenticated.pop(agent_id, None)
                    if previous:
                        await previous[0].close()
                self.states[agent_id] = LoginState(status="verifying")
                result = await self.manager.probe(agent_id, cwd)
                self.states[agent_id] = (
                    LoginState(status="ready", result=result)
                    if result["status"] == "ready"
                    else LoginState(
                        status="failed", error="verification_failed", result=result
                    )
                )
        except asyncio.CancelledError:
            self.states[agent_id] = LoginState(status="cancelled")
            raise
        except TimeoutError:
            self.states[agent_id] = LoginState(status="failed", error="timeout")
        except Exception:
            # Authentication output may contain secrets; never expose raw exceptions.
            self.states[agent_id] = LoginState(status="failed", error="failed")


async def claude_authenticated(cwd: str, overrides: dict[str, str]) -> bool:
    env = {**os.environ, **overrides}
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        env.pop(key, None)
    executable = shutil.which("claude", path=env.get("PATH"))
    if not executable:
        raise ValueError("Claude CLI is not installed")
    process = await asyncio.create_subprocess_exec(
        executable,
        "auth",
        "status",
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        **({"creationflags": 0x08000000} if os.name == "nt" else {}),
    )
    try:
        async with asyncio.timeout(15):
            code = await process.wait()
        if code not in (0, 1):
            raise ValueError(
                "Could not check Claude authentication; update the CLI and retry"
            )
        return code == 0
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
