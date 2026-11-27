"""Discovery and configuration for local stdio ACP agents."""

from __future__ import annotations

import json
import os
import shutil
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
    """Candidate global and Suzent-managed ``node_modules`` directories."""
    roots: list[Path] = []
    suzent_dir = Path(os.environ.get("SUZENT_DATA_DIR", "~/.suzent")).expanduser()
    roots.append(suzent_dir / "acp_adapters" / "node_modules")
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


def resolve_managed_npx_command(command: list[str]) -> list[str]:
    """Rewrite ``npx [-y] <pkg> [args...]`` to the installed binary in ``~/.suzent/acp_adapters``.

    Adding ``~/.suzent/acp_adapters/node_modules/.bin`` to ``PATH`` does not
    prevent ``npx -y @scope/pkg`` from re-downloading when invoked inside a
    project workspace: ``npm exec`` checks the workspace dependency tree rather
    than ``NODE_PATH``. When the package is installed in Suzent's managed
    adapter directory, resolve its bin entry directly so the workspace ``cwd``
    is preserved without triggering an npm fetch.
    """
    package = _npx_package(command)
    if not package:
        return list(command)

    pkg_index = -1
    for i, part in enumerate(command[1:], start=1):
        if not part.startswith("-"):
            pkg_index = i
            break
    if pkg_index < 0:
        return list(command)
    specifier = command[pkg_index]
    at = specifier.rfind("@")
    requested_version = specifier[at + 1 :].strip() if at > 0 else ""
    trailing_args = command[pkg_index + 1 :]

    adapter_root = (
        Path(os.environ.get("SUZENT_DATA_DIR", "~/.suzent")).expanduser()
        / "acp_adapters"
        / "node_modules"
    )
    pkg_dir = adapter_root / package
    if not pkg_dir.is_dir():
        return list(command)

    unscoped = package.split("/")[-1]
    bin_name = unscoped
    rel_target: str | None = None
    pkg_json_path = pkg_dir / "package.json"
    if pkg_json_path.is_file():
        try:
            data = json.loads(pkg_json_path.read_text(encoding="utf-8"))
            installed_version = str(data.get("version") or "").strip()
            if (
                requested_version
                and requested_version != "latest"
                and installed_version != requested_version
            ):
                return list(command)
            bin_field = data.get("bin")
            if isinstance(bin_field, str) and bin_field.strip():
                rel_target = bin_field.strip()
            elif isinstance(bin_field, dict) and bin_field:
                chosen_key = (
                    unscoped if unscoped in bin_field else next(iter(bin_field.keys()))
                )
                bin_name = str(chosen_key)
                target = bin_field.get(chosen_key)
                if isinstance(target, str) and target.strip():
                    rel_target = target.strip()
        except Exception:
            if requested_version and requested_version != "latest":
                return list(command)
    elif requested_version and requested_version != "latest":
        return list(command)

    # 1. Prefer the npm-generated shim in node_modules/.bin so native binaries
    # and non-Node shebang scripts run under their own interpreter.
    bin_dir = adapter_root / ".bin"
    candidates = (
        [bin_dir / f"{bin_name}.cmd", bin_dir / f"{bin_name}.exe", bin_dir / bin_name]
        if os.name == "nt"
        else [bin_dir / bin_name]
    )
    for candidate in candidates:
        if candidate.is_file():
            return [str(candidate), *trailing_args]

    # 2. Fallback to the package.json bin target if no .bin shim exists.
    if rel_target:
        script_path = (pkg_dir / rel_target).resolve()
        if script_path.is_file():
            is_js = script_path.suffix.lower() in (".js", ".mjs", ".cjs")
            if not is_js:
                try:
                    head = script_path.read_bytes()[:128]
                    first_line = head.splitlines()[0] if head else b""
                    if first_line.startswith(b"#!") and b"node" in first_line.lower():
                        is_js = True
                except OSError:
                    pass
            if is_js:
                node_exe = shutil.which("node")
                if node_exe:
                    return [node_exe, str(script_path), *trailing_args]
            return [str(script_path), *trailing_args]

    return list(command)


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
    # Where the vendor documents installation. Install routes are plural and
    # platform-specific (brew, curl, native installer, Docker, npm), so we link
    # to the page that tracks them instead of hardcoding one command.
    docs_url: str | None = None

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

    @property
    def adapter_package(self) -> str | None:
        """The npm adapter this agent is launched through, if any.

        Priming it is Suzent's requirement, not the vendor's: a cold `npx`
        download happens inside the `initialize` handshake, where it reads as
        a hung agent.
        """
        return _npx_package(self.command)

    def diagnostics(self) -> dict[str, Any]:
        from .dialects import inspect_local_agent_state

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

        ready = self.available
        local_state = (
            inspect_local_agent_state(self.id, self.env)
            if ready
            else {"auth_hint": None, "usage_summary": None}
        )
        effective_auth = (
            self.auth_status
            if self.auth_status not in (None, "unknown")
            else (local_state.get("auth_hint") or self.auth_status)
        )
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "executable_path": exe,
            "status": "ready" if ready else "not_installed",
            "builtin": self.builtin,
            "version_bounds": self.version_bounds,
            "auth_status": effective_auth,
            "usage_summary": local_state.get("usage_summary"),
            "install_command": self.install_command,
            "login_command": self.login_command,
            "docs_url": self.docs_url,
            "adapter_package": self.adapter_package,
        }

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["available"] = self.available
        return value


# ---------------------------------------------------------------------------
# Built-in agents
# ---------------------------------------------------------------------------

_BUILTINS = (
    # ── Claude Code ──────────────────────────────────────────────────
    # Official @agentclientprotocol adapter using the Claude Agent SDK.
    # Supports both Claude Subscription (`claude auth login --claudeai`) and
    # Anthropic Console / API key (`claude auth login --console` or ANTHROPIC_API_KEY).
    ACPAgent(
        id="claude-code",
        name="Claude Code",
        command=["npx", "-y", "@agentclientprotocol/claude-agent-acp"],
        builtin=True,
        description="Anthropic's Claude coding agent — supports Claude Subscription (Pro/Max) and API keys.",
        docs_url="https://docs.claude.com/en/docs/claude-code/setup",
        login_command=["claude", "auth", "login"],
    ),
    # ── Codex ────────────────────────────────────────────────────────
    # Official @agentclientprotocol adapter for the OpenAI Codex CLI.
    ACPAgent(
        id="codex",
        name="Codex",
        command=["npx", "-y", "@agentclientprotocol/codex-acp"],
        builtin=True,
        description="Official ACP adapter for the OpenAI Codex CLI.",
        docs_url="https://developers.openai.com/codex/cli/",
        # `auth` doesn't exist on the Codex CLI; the subcommand is `login`.
        login_command=["codex", "login"],
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
        docs_url="https://github.com/NousResearch/hermes-agent",
        # `hermes login` is deprecated and `hermes auth` has no `login`
        # subcommand; the CLI points users at `setup` for provider auth.
        login_command=["hermes", "setup"],
    ),
    # ── OpenClaw ─────────────────────────────────────────────────────
    # `openclaw acp` is bridge mode: it exposes a running Gateway session as
    # an ACP server.  The @openclaw/acpx package points the other way -- it is
    # a plugin that lets OpenClaw *drive* other ACP agents -- and it publishes
    # no bin, so `npx @openclaw/acpx` could never have started.
    ACPAgent(
        id="openclaw",
        name="OpenClaw",
        command=["openclaw", "acp"],
        builtin=True,
        description="Bridges a running OpenClaw Gateway session over ACP.",
        docs_url="https://docs.openclaw.ai/start/getting-started",
        login_command=["openclaw", "onboard"],
    ),
    # ── Gemini CLI ───────────────────────────────────────────────────
    ACPAgent(
        id="gemini",
        name="Gemini CLI",
        command=["npx", "-y", "@google/gemini-cli", "--acp"],
        builtin=True,
        description="Google's official CLI for Gemini with native ACP support.",
        docs_url="https://github.com/google-gemini/gemini-cli",
        login_command=["gemini"],
    ),
    # ── GitHub Copilot CLI ───────────────────────────────────────────
    ACPAgent(
        id="github-copilot-cli",
        name="GitHub Copilot",
        command=["npx", "-y", "@github/copilot", "--acp"],
        builtin=True,
        description="GitHub's AI pair programmer CLI speaking ACP.",
        docs_url="https://github.com/features/copilot/cli/",
        login_command=["copilot", "auth", "login"],
    ),
    # ── Qwen Code ────────────────────────────────────────────────────
    ACPAgent(
        id="qwen-code",
        name="Qwen Code",
        command=["npx", "-y", "@qwen-code/qwen-code", "--acp"],
        builtin=True,
        description="Alibaba's Qwen coding assistant with ACP support.",
        docs_url="https://github.com/QwenLM/qwen-code",
        login_command=["qwen"],
    ),
    # ── Kimi Code ────────────────────────────────────────────────────
    ACPAgent(
        id="kimi-code",
        name="Kimi Code",
        command=["npx", "-y", "@moonshot-ai/kimi-code", "acp"],
        builtin=True,
        description="Moonshot AI's next-generation coding agent.",
        docs_url="https://github.com/MoonshotAI/kimi-code",
        login_command=["kimi", "login"],
    ),
    # ── Grok Build ───────────────────────────────────────────────────
    ACPAgent(
        id="grok",
        name="Grok",
        command=["npx", "-y", "@xai-official/grok", "agent", "stdio"],
        builtin=True,
        description="xAI's coding agent and CLI over ACP stdio.",
        docs_url="https://x.ai/cli",
        login_command=["grok", "login"],
    ),
    # ── OpenCode ─────────────────────────────────────────────────────
    ACPAgent(
        id="opencode",
        name="OpenCode",
        command=["opencode", "acp"],
        builtin=True,
        description="Open-source coding agent with native ACP support.",
        docs_url="https://opencode.ai/docs/cli/",
        login_command=["opencode", "auth", "login"],
    ),
    # ── Cursor CLI ───────────────────────────────────────────────────
    ACPAgent(
        id="cursor",
        name="Cursor",
        command=["cursor-agent", "acp"],
        builtin=True,
        description="Cursor's CLI coding agent speaking ACP.",
        docs_url="https://cursor.com/docs/cli/acp",
        login_command=["cursor-agent", "login"],
    ),
    # ── Cline ────────────────────────────────────────────────────────
    ACPAgent(
        id="cline",
        name="Cline",
        command=["npx", "-y", "cline", "--acp"],
        builtin=True,
        description="Autonomous coding agent CLI for files, shell, and browser.",
        docs_url="https://docs.cline.bot/cline-cli/overview",
        login_command=["cline", "auth"],
    ),
    # ── Goose ────────────────────────────────────────────────────────
    ACPAgent(
        id="goose",
        name="Goose",
        command=["goose", "acp"],
        builtin=True,
        description="Block's local, extensible open-source engineering agent.",
        docs_url="https://block.github.io/goose/",
        login_command=["goose", "configure"],
    ),
    # ── Auggie CLI ───────────────────────────────────────────────────
    ACPAgent(
        id="auggie",
        name="Auggie",
        command=["npx", "-y", "@augmentcode/auggie", "--acp"],
        builtin=True,
        description="Augment Code's software agent with context engine.",
        docs_url="https://docs.augmentcode.com/cli/overview",
        login_command=["auggie", "login"],
    ),
    # ── Kilo Code ────────────────────────────────────────────────────
    ACPAgent(
        id="kilo",
        name="Kilo Code",
        command=["npx", "-y", "@kilocode/cli", "acp"],
        builtin=True,
        description="Open-source coding agent CLI speaking ACP.",
        docs_url="https://kilo.ai/docs/cli",
    ),
)


# Built-in ids that have been renamed. Chats created before the rename still
# carry the old id in their config, and every send would fail without this.
_RENAMED_IDS = {
    "codex-acp": "codex",
    "claude-acp": "claude-code",
    "claude-code-api": "claude-code",
    "grok-build": "grok",
}


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
            docs_url=str(raw["docs_url"])
            if raw.get("docs_url")
            else (builtin.docs_url if builtin else None),
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
