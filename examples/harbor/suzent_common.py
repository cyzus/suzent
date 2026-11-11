"""Shared logic for the Harbor and Pier agents that run Suzent in a container.

Standard library only: Harbor and Pier import their agents inside their own
isolated environments, where Suzent's dependencies are not installed.
"""

import json
import shlex
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

REPO_URL = "https://github.com/cyzus/suzent"
SOURCE_DIR = "$HOME/suzent-src"
SUZENT = f"{SOURCE_DIR}/.venv/bin/suzent"
PYTHON = f"{SOURCE_DIR}/.venv/bin/python"
LOGS_DIR = "/logs/agent"
SUMMARY_FILE = "suzent.json"
USAGE_LOG_FILE = "suzent-usage.jsonl"
PROXY_PORT = 8899

_PATH = 'export PATH="$HOME/.local/bin:$PATH"; '
_FORWARDED_ENV_SUFFIXES = ("_API_KEY", "_BASE_URL")

# Every tool definition is resent on each model call, so a terminal coding
# task runs with file and shell tools only.
CODING_TOOLS = (
    "ReadFileTool,WriteFileTool,EditFileTool,GlobTool,GrepTool,"
    "RunCommandTool,StartCommandTool,CheckCommandTool,StopCommandTool"
)

ROOT_INSTALL_COMMAND = (
    "if command -v apt-get >/dev/null 2>&1; then"
    " apt-get update && apt-get install -y curl git ca-certificates;"
    " elif command -v apk >/dev/null 2>&1; then"
    " apk add --no-cache curl git bash ca-certificates;"
    " elif command -v dnf >/dev/null 2>&1; then dnf install -y curl git;"
    " elif command -v yum >/dev/null 2>&1; then yum install -y curl git;"
    " fi"
)


@dataclass(frozen=True)
class ModelRoute:
    """How a benchmark's model name reaches a provider through Suzent."""

    model: str
    # Where the provider is served, and the Suzent setting that can point the
    # provider somewhere else. Both are None when Suzent cannot redirect it,
    # which also means its calls cannot be logged one by one.
    base_url: str | None = None
    base_url_env: str | None = None
    env: dict[str, str] = field(default_factory=dict)

    @property
    def host(self) -> str | None:
        return urlsplit(self.base_url).hostname if self.base_url else None


def resolve_model(model_name: str | None, environ: Mapping[str, str]) -> ModelRoute:
    """Translate a runner's model name into Suzent's `<provider>/<model>` ID."""
    if not model_name:
        raise ValueError("Pass a model with -m, for example moonshot/kimi-k3")
    provider, _, model_id = model_name.partition("/")
    match provider:
        case "fireworks_ai":
            # Runners name models by LiteLLM route. Suzent has no Fireworks
            # provider, so the route runs through its OpenAI-compatible one.
            env = {}
            if key := environ.get("FIREWORKS_API_KEY"):
                env["OPENAI_API_KEY"] = key
            return ModelRoute(
                model=f"openai/{model_id}",
                base_url="https://api.fireworks.ai/inference/v1",
                base_url_env="OPENAI_BASE_URL",
                env=env,
            )
        case "moonshot":
            return ModelRoute(
                model=model_name,
                base_url=environ.get("MOONSHOT_BASE_URL")
                or "https://api.moonshot.ai/v1",
                base_url_env="MOONSHOT_BASE_URL",
            )
        case "openai":
            return ModelRoute(
                model=model_name,
                base_url=environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1",
                base_url_env="OPENAI_BASE_URL",
            )
        case _:
            return ModelRoute(model=model_name)


def install_command(ref: str | None) -> str:
    """Shell command that installs Suzent at ``ref`` for the current user."""
    # A bare fetch takes a branch, a tag or a commit, so one path pins all three.
    return (
        "set -euo pipefail; "
        "curl -LsSf https://astral.sh/uv/install.sh | sh; "
        f"{_PATH}"
        f'mkdir -p "{SOURCE_DIR}" && cd "{SOURCE_DIR}" && '
        f"git init -q && git fetch -q --depth 1 {REPO_URL} {shlex.quote(ref or 'main')} "
        "&& git checkout -q FETCH_HEAD && "
        "uv sync --frozen --no-dev --python 3.12"
    )


def run_env(route: ModelRoute, environ: Mapping[str, str]) -> dict[str, str]:
    """Environment for the run: provider credentials, and the proxy when used."""
    env = {
        key: value
        for key, value in environ.items()
        if key.endswith(_FORWARDED_ENV_SUFFIXES)
    }
    env.update(route.env)
    if route.base_url and route.base_url_env:
        path = urlsplit(route.base_url).path
        env[route.base_url_env] = f"http://127.0.0.1:{PROXY_PORT}{path}"
    # A container has no OS keychain for Suzent's default secret store.
    env["SUZENT_SECRET_BACKEND"] = "encrypted_sqlite"
    return env


def run_command(
    route: ModelRoute, instruction: str, tools: str, code_mode: bool
) -> str:
    """Shell command that runs one task and leaves its evidence in LOGS_DIR."""
    # Pinning MODEL_OPTIONS makes the requested model the only one Suzent may
    # use, so a typo fails the run instead of falling back silently.
    settings = (
        f"MODEL_OPTIONS:\n  - {json.dumps(route.model)}\nSANDBOX_ENABLED: false\n"
    )
    proxy_start = proxy_stop = ""
    if route.base_url and route.base_url_env:
        origin = urlsplit(route.base_url)
        proxy_start = (
            f"{PYTHON} {SOURCE_DIR}/examples/harbor/usage_proxy.py {PROXY_PORT} "
            f"{LOGS_DIR}/{USAGE_LOG_FILE} "
            f"{shlex.quote(f'{origin.scheme}://{origin.netloc}')} "
            f"> {LOGS_DIR}/usage-proxy.log 2>&1 & proxy=$!; "
        )
        proxy_stop = "kill $proxy 2>/dev/null; "
    return (
        'mkdir -p "$HOME/.suzent/config" && '
        f"printf %s {shlex.quote(settings)} "
        '> "$HOME/.suzent/config/local.yaml"; '
        f"{_PATH}{proxy_start}"
        f"{SUZENT} run --json --permission-mode full_access "
        f"--model {shlex.quote(route.model)} --tools {shlex.quote(tools)} "
        f"{'--code-mode' if code_mode else '--no-code-mode'} "
        f"-- {shlex.quote(instruction)} "
        f"> {LOGS_DIR}/{SUMMARY_FILE} 2> {LOGS_DIR}/suzent.log; "
        "status=$?; "
        f"{proxy_stop}"
        f'cp -r "$HOME/.suzent/chats" {LOGS_DIR}/chats 2>/dev/null; '
        "exit $status"
    )


def read_usage(logs_dir: Path) -> dict[str, int] | None:
    """Token totals Suzent printed for the run, or None without a summary."""
    try:
        summary = json.loads((logs_dir / SUMMARY_FILE).read_text())
    except (OSError, json.JSONDecodeError):
        return None
    usage = summary.get("usage")
    return usage if isinstance(usage, dict) else None


def as_bool(value: bool | str) -> bool:
    """Agent kwargs given on a runner's command line arrive as strings."""
    return str(value).lower() in ("true", "1", "yes", "on")
