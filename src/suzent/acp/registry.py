"""Discovery and configuration for local stdio ACP agents."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ACPAgent:
    id: str
    command: list[str]
    name: str
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None
    builtin: bool = False

    install_command: list[str] | None = None
    login_command: list[str] | None = None
    version_bounds: str | None = None
    auth_status: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.command and shutil.which(self.command[0]))

    def diagnostics(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "executable_path": shutil.which(self.command[0]) if self.command else None,
            "status": "ready" if self.available else "not_installed",
            "version_bounds": self.version_bounds,
            "auth_status": self.auth_status,
            "install_command": self.install_command,
            "login_command": self.login_command,
        }

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["available"] = self.available
        return value


_BUILTINS = (
    ACPAgent(
        id="claude-code",
        name="Claude Code",
        command=["acp-adapter", "--adapter", "claude"],
        builtin=True,
        install_command=[
            "sh",
            "-c",
            'curl -sSL https://raw.githubusercontent.com/beyond5959/acp-adapter/master/install.sh | INSTALL_DIR="$HOME/.local/bin" sh',
        ],
        login_command=["claude", "auth", "login"],
        auth_status="unknown",
    ),
    ACPAgent(
        id="codex-acp",
        name="Codex (ACP)",
        command=["codex-acp"],
        builtin=True,
    ),
)


class ACPAgentRegistry:
    """Load ACP stdio commands from ``~/.suzent/acp_agents.json``.

    ``SUZENT_DATA_DIR`` is honored for test and portable installations. The file
    may contain either ``{"agents": [...]}``, a list, or a mapping keyed by id.
    User entries replace built-in candidates with the same id. The Claude Agent
    SDK is deliberately not a candidate; only ACP-speaking executables are run.
    """

    def __init__(self, path: Path | None = None):
        root = Path(os.environ.get("SUZENT_DATA_DIR", "~/.suzent")).expanduser()
        self.path = path or root / "acp_agents.json"

    def list_agents(self) -> list[ACPAgent]:
        agents = {agent.id: agent for agent in _BUILTINS}
        for raw in self._read_entries():
            agent = self._parse(raw)
            if agent is not None:
                agents[agent.id] = agent
        return list(agents.values())

    def get(self, agent_id: str) -> ACPAgent:
        for agent in self.list_agents():
            if agent.id == agent_id:
                return agent
        raise KeyError(f"Unknown ACP agent: {agent_id}")

    def _read_entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if isinstance(data, dict) and isinstance(data.get("agents"), list):
            return [item for item in data["agents"] if isinstance(item, dict)]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            return [
                {"id": key, **value}
                for key, value in data.items()
                if isinstance(value, dict)
            ]
        return []

    @staticmethod
    def _parse(raw: dict[str, Any]) -> ACPAgent | None:
        agent_id = str(raw.get("id") or "").strip()
        command = raw.get("command")
        if isinstance(command, str):
            command = [command]
        if not agent_id or not isinstance(command, list) or not command:
            return None
        command = [str(part) for part in command if str(part)]
        if not command:
            return None
        env = raw.get("env") if isinstance(raw.get("env"), dict) else {}
        return ACPAgent(
            id=agent_id,
            name=str(raw.get("name") or agent_id),
            command=command,
            env={str(k): str(v) for k, v in env.items()},
            cwd=str(raw["cwd"]) if raw.get("cwd") else None,
        )
