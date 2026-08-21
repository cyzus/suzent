"""Discovery and configuration for local stdio ACP agents."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# npm package detection
#
# An `npx -y <pkg>` command is *not* proof the agent is usable: `npx` ships
# with Node, so `shutil.which("npx")` succeeds on any machine with Node even
# when the package has never been downloaded. Reporting those agents as
# "ready" made every agent look installed, so nothing was ever flagged as
# missing. Detect the package itself instead.
# ---------------------------------------------------------------------------

# npx would download a missing package on first use, but that happens *inside*
# the ACP handshake while the client waits on `initialize`, so a cold fetch
# reads as a hung agent. Treating uncached packages as not-installed keeps the
# failure in the settings tab, where it comes with a copyable install command.
_NPM_CACHE_TTL = 5.0
_npm_cache: dict[str, tuple[float, bool]] = {}


def _npm_global_roots() -> list[Path]:
    """Candidate global ``node_modules`` directories, without invoking npm."""
    roots: list[Path] = []
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            roots.append(Path(appdata) / "npm" / "node_modules")
        node = shutil.which("node")
        if node:
            roots.append(Path(node).parent / "node_modules")
    else:
        node = shutil.which("node")
        if node:
            roots.append(Path(node).parent.parent / "lib" / "node_modules")
        roots.extend(
            [
                Path("/usr/local/lib/node_modules"),
                Path("/usr/lib/node_modules"),
                Path.home() / ".npm-global" / "lib" / "node_modules",
            ]
        )
    return roots


def _npx_cache_roots() -> list[Path]:
    """Directories holding npx's on-demand package cache."""
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return [Path(local) / "npm-cache" / "_npx"]
        return []
    return [Path.home() / ".npm" / "_npx"]


def _npm_package_installed(package: str) -> bool:
    """True when ``package`` is present globally or already in the npx cache."""
    now = time.monotonic()
    hit = _npm_cache.get(package)
    if hit and now - hit[0] < _NPM_CACHE_TTL:
        return hit[1]

    found = any((root / package).is_dir() for root in _npm_global_roots())
    if not found:
        for cache_root in _npx_cache_roots():
            try:
                entries = list(cache_root.iterdir())
            except OSError:
                continue
            if any((entry / "node_modules" / package).is_dir() for entry in entries):
                found = True
                break

    _npm_cache[package] = (now, found)
    return found


def _npx_package(command: list[str]) -> str | None:
    """The package an ``npx`` command would run, or None if not an npx call."""
    executable = Path(command[0].replace("\\", "/")).stem.lower() if command else ""
    if executable != "npx":
        return None
    for part in command[1:]:
        if part.startswith("-"):
            continue
        # `npx pkg@1.2.3` — the version suffix isn't part of the directory name
        # (`@scope/name@ver` keeps the leading @, so only split past index 0).
        at = part.rfind("@")
        return part[:at] if at > 0 else part
    return None


@dataclass(frozen=True)
class ACPAgent:
    id: str
    command: list[str]
    name: str
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None
    builtin: bool = False
    description: str | None = None
    requires_executable: str | None = None

    install_command: list[str] | None = None
    login_command: list[str] | None = None
    version_bounds: str | None = None
    auth_status: str | None = None

    @property
    def available(self) -> bool:
        if not self.command or not shutil.which(self.command[0]):
            return False
        if self.requires_executable and not shutil.which(self.requires_executable):
            return False
        package = _npx_package(self.command)
        if package and not _npm_package_installed(package):
            return False
        return True

    @property
    def display_command(self) -> str:
        """What to name when the agent can't run.

        ``command[0]`` is an implementation detail: for the CLI bridge it is
        the Python interpreter, and telling a user their own interpreter is
        unavailable helps nobody.
        """
        if self.requires_executable:
            return self.requires_executable
        package = _npx_package(self.command)
        if package:
            return package
        return self.command[0] if self.command else self.name

    def diagnostics(self) -> dict[str, Any]:
        # Show the user-facing executable, not an intermediate launcher.
        if self.requires_executable:
            exe = shutil.which(self.requires_executable)
        elif _npx_package(self.command):
            # `npx` itself is a meaningless path to show — name the package.
            exe = _npx_package(self.command)
        elif self.command:
            exe = shutil.which(self.command[0])
        else:
            exe = None
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "executable_path": exe,
            "status": "ready" if self.available else "not_installed",
            "builtin": self.builtin,
            "version_bounds": self.version_bounds,
            "auth_status": self.auth_status,
            "install_command": self.install_command,
            "login_command": self.login_command,
        }

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["available"] = self.available
        return value


# ---------------------------------------------------------------------------
# Built-in agents
# ---------------------------------------------------------------------------

_BUILTINS = (
    # ── Claude Code (CLI Bridge) ─────────────────────────────────────
    # Wraps ``claude -p`` — works with Pro / Max subscriptions, no API key.
    ACPAgent(
        id="claude-code",
        name="Claude Code (CLI)",
        command=[sys.executable, "-m", "suzent.acp.claude_bridge"],
        builtin=True,
        description="Wraps the Claude CLI for Pro/Max subscribers — no API key needed.",
        requires_executable="claude",
        login_command=["claude", "auth", "login"],
        auth_status="unknown",
    ),
    # ── Claude Code (API Adapter) ────────────────────────────────────
    # Official @agentclientprotocol adapter using the Agent SDK (2.4k ⭐).
    # npx downloads on first use and caches; ``install_command`` offers a
    # permanent global install.
    ACPAgent(
        id="claude-code-api",
        name="Claude Code (API)",
        command=["npx", "-y", "@agentclientprotocol/claude-agent-acp"],
        builtin=True,
        description="Official ACP adapter via Agent SDK — requires an Anthropic API key.",
        install_command=[
            "npm",
            "install",
            "-g",
            "@agentclientprotocol/claude-agent-acp",
        ],
    ),
    # ── Codex ────────────────────────────────────────────────────────
    # Official @agentclientprotocol adapter for the OpenAI Codex CLI.
    ACPAgent(
        id="codex",
        name="Codex",
        command=["npx", "-y", "@agentclientprotocol/codex-acp"],
        builtin=True,
        description="Official ACP adapter for the OpenAI Codex CLI.",
        install_command=["npm", "install", "-g", "@agentclientprotocol/codex-acp"],
        login_command=["codex", "auth"],
    ),
    # ── Hermes ───────────────────────────────────────────────────────
    # Nous Research's autonomous AI agent with ACP support.
    ACPAgent(
        id="hermes",
        name="Hermes",
        # `acp` is a subcommand, not a flag: `hermes --acp` is an argparse
        # usage error, so the process died before the handshake.
        command=["hermes", "acp"],
        builtin=True,
        description="Nous Research's autonomous AI agent with native ACP support.",
        # `hermes login` is deprecated and `hermes auth` has no `login`
        # subcommand; the CLI points users at `setup` for provider auth.
        login_command=["hermes", "setup"],
    ),
    # ── OpenClaw ─────────────────────────────────────────────────────
    # Popular open-source coding agent with its own ACP adapter.
    ACPAgent(
        id="openclaw",
        name="OpenClaw",
        command=["npx", "-y", "@openclaw/acpx"],
        builtin=True,
        description="Open-source coding agent with ACP support via @openclaw/acpx.",
        install_command=["npm", "install", "-g", "@openclaw/acpx"],
    ),
)


# Built-in ids that have been renamed. Chats created before the rename still
# carry the old id in their config, and every send would fail without this.
_RENAMED_IDS = {"codex-acp": "codex"}


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
            agent = self._parse(raw, builtin=agents.get(str(raw.get("id") or "")))
            if agent is not None:
                agents[agent.id] = agent
        return list(agents.values())

    def get(self, agent_id: str) -> ACPAgent:
        agents = self.list_agents()
        for agent in agents:
            if agent.id == agent_id:
                return agent
        # Fall back to the new id only when nothing claims the old one, so a
        # user-defined agent keeping the retired id still wins.
        renamed = _RENAMED_IDS.get(agent_id)
        if renamed:
            for agent in agents:
                if agent.id == renamed:
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
    def _parse(raw: dict[str, Any], builtin: ACPAgent | None = None) -> ACPAgent | None:
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

        def _command_field(key: str, fallback: list[str] | None) -> list[str] | None:
            value = raw.get(key)
            if isinstance(value, str):
                value = [value]
            if isinstance(value, list):
                parts = [str(part) for part in value if str(part)]
                if parts:
                    return parts
            return fallback

        # Overriding a built-in's command shouldn't discard its install/login
        # metadata -- the UI needs those to offer setup actions.
        return ACPAgent(
            id=agent_id,
            name=str(raw.get("name") or (builtin.name if builtin else agent_id)),
            command=command,
            env={str(k): str(v) for k, v in env.items()},
            cwd=str(raw["cwd"])
            if raw.get("cwd")
            else (builtin.cwd if builtin else None),
            builtin=bool(builtin),
            description=str(raw["description"])
            if raw.get("description")
            else (builtin.description if builtin else None),
            requires_executable=str(raw["requires_executable"])
            if raw.get("requires_executable")
            else (builtin.requires_executable if builtin else None),
            install_command=_command_field(
                "install_command", builtin.install_command if builtin else None
            ),
            login_command=_command_field(
                "login_command", builtin.login_command if builtin else None
            ),
            version_bounds=str(raw["version_bounds"])
            if raw.get("version_bounds")
            else (builtin.version_bounds if builtin else None),
            auth_status=str(raw["auth_status"])
            if raw.get("auth_status")
            else (builtin.auth_status if builtin else None),
        )
