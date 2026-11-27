"""Dialect adapters and on-disk state probes for local ACP agents.

Mirrors Orca's ``acp-dialects`` & on-disk usage/auth inspection pattern:
- Normalizes vendor-specific error messages (auth required, quota/rate limits).
- Inspects on-disk CLI state (e.g. ``~/.claude``, ``~/.codex``, ``~/.gemini``)
  without waking up the agent subprocess, providing zero-cost auth & usage hints.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ACPDialect:
    """Per-agent protocol dialect and on-disk state hints."""

    id: str
    # Substrings in JSON-RPC error messages or stderr that indicate auth is required
    # even when the agent did not use standard JSON-RPC code -32000.
    auth_error_patterns: tuple[str, ...] = (
        "not logged in",
        "not signed in",
        "authentication required",
        "login required",
        "unauthorized",
        "please run `claude auth login`",
        "please run `codex login`",
        "invalid api key",
        "api key not found",
    )
    # Substrings indicating quota/rate-limit exhaustion.
    quota_error_patterns: tuple[str, ...] = (
        "rate limit",
        "quota exceeded",
        "quota exhausted",
        "usage limit",
        "too many requests",
        "429",
    )
    # Environment variables to strip before launching this agent so inherited
    # process keys do not override the user's subscription login.
    env_to_strip: tuple[str, ...] = ()
    # Candidate paths (relative to user home) that prove the CLI has local credentials/state.
    auth_paths: tuple[str, ...] = ()
    # Candidate paths (relative to user home) where usage/quota state or config is stored.
    state_dir: str | None = None
    # Supported interaction modes or permission flags if any.
    supports_session_load: bool = True

    def is_auth_error(self, code: int | None, message: str, data: Any = None) -> bool:
        if code == -32000:
            return True
        haystack = f"{message} {data or ''}".lower()
        return any(pat in haystack for pat in self.auth_error_patterns)

    def is_quota_error(self, code: int | None, message: str, data: Any = None) -> bool:
        haystack = f"{message} {data or ''}".lower()
        return any(pat in haystack for pat in self.quota_error_patterns)


GENERIC_DIALECT = ACPDialect(id="generic")

_DIALECTS: dict[str, ACPDialect] = {
    "claude-code": ACPDialect(
        id="claude-code",
        auth_paths=(
            ".claude/.credentials.json",
            ".claude.json",
            ".claude/settings.json",
        ),
        state_dir=".claude",
    ),
    "codex": ACPDialect(
        id="codex",
        auth_paths=(".codex/auth.json", ".codex/config.toml"),
        state_dir=".codex",
    ),
    "gemini": ACPDialect(
        id="gemini",
        auth_paths=(
            ".gemini/oauth_creds.json",
            ".gemini/settings.json",
            ".config/gemini/credentials.json",
        ),
        state_dir=".gemini",
    ),
    "github-copilot-cli": ACPDialect(
        id="github-copilot-cli",
        auth_paths=(".copilot/config.json", ".config/github-copilot/hosts.json"),
        state_dir=".copilot",
    ),
    "qwen-code": ACPDialect(
        id="qwen-code",
        auth_paths=(".qwen/oauth_creds.json", ".qwen/settings.json"),
        state_dir=".qwen",
    ),
    "kimi-code": ACPDialect(
        id="kimi-code",
        auth_paths=(".kimi/config.toml", ".kimi/credentials.json", ".kimi/auth.json"),
        state_dir=".kimi",
    ),
    "grok": ACPDialect(
        id="grok",
        auth_paths=(
            ".grok/config.json",
            ".grok/credentials.json",
            ".config/grok/config.json",
        ),
        state_dir=".grok",
    ),
    "opencode": ACPDialect(
        id="opencode",
        auth_paths=(
            ".local/share/opencode/auth.json",
            ".config/opencode/opencode.json",
        ),
        state_dir=".local/share/opencode",
    ),
    "cursor": ACPDialect(
        id="cursor",
        auth_paths=(".cursor/cli-config.json", ".cursor/auth.json"),
        state_dir=".cursor",
    ),
    "cline": ACPDialect(
        id="cline",
        auth_paths=(".cline/config.json",),
        state_dir=".cline",
    ),
    "goose": ACPDialect(
        id="goose",
        auth_paths=(".config/goose/config.yaml", ".config/goose/profiles.yaml"),
        state_dir=".config/goose",
    ),
    "hermes": ACPDialect(
        id="hermes",
        auth_paths=(".hermes/config.yaml", ".hermes/.env"),
        state_dir=".hermes",
    ),
    "openclaw": ACPDialect(
        id="openclaw",
        auth_paths=(".openclaw/openclaw.json", ".openclaw/config.json"),
        state_dir=".openclaw",
    ),
    "auggie": ACPDialect(
        id="auggie",
        auth_paths=(".augment/session.json", ".config/augment/session.json"),
        state_dir=".augment",
    ),
    "kilo": ACPDialect(
        id="kilo",
        auth_paths=(".kilocode/config.json",),
        state_dir=".kilocode",
    ),
}


def get_dialect(agent_id: str) -> ACPDialect:
    return _DIALECTS.get(agent_id, GENERIC_DIALECT)


def inspect_local_agent_state(
    agent_id: str, agent_env: dict[str, str] | None = None
) -> dict[str, Any]:
    """Read on-disk CLI state without spawning the agent process.

    Returns a dictionary with:
    - ``auth_hint``: ``"ok"`` if local credentials/API key are detected, else ``None``.
    - ``usage_summary``: optional human-readable string (e.g. account email, plan, or
      recent token/session activity) when discoverable on disk.
    """
    dialect = get_dialect(agent_id)
    home = Path.home()
    env = {**os.environ, **(agent_env or {})}

    auth_hint: str | None = None
    usage_summary: str | None = None

    # 1. Check explicit API key env vars for API-backed agents
    if agent_id in ("claude-code", "claude-code-api") and env.get("ANTHROPIC_API_KEY"):
        auth_hint = "ok"
    elif agent_id == "codex" and env.get("OPENAI_API_KEY"):
        auth_hint = "ok"
    elif agent_id == "gemini" and (
        env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")
    ):
        auth_hint = "ok"

    # 2. Check on-disk auth files
    for rel in dialect.auth_paths:
        candidate = home / rel
        try:
            if candidate.is_file() and candidate.stat().st_size > 2:
                auth_hint = "ok"
                summary = _extract_summary_from_file(agent_id, candidate)
                if summary:
                    usage_summary = summary
                break
        except OSError:
            continue

    # 3. Check state directory for usage/quota or recent session count if summary still empty
    if dialect.state_dir and not usage_summary:
        state_path = home / dialect.state_dir
        try:
            if state_path.is_dir():
                usage_summary = _extract_dir_usage_summary(agent_id, state_path)
        except OSError:
            pass

    return {
        "auth_hint": auth_hint,
        "usage_summary": usage_summary,
    }


def _extract_summary_from_file(agent_id: str, path: Path) -> str | None:
    """Best-effort, non-secret metadata extraction (plan tier or account label)."""
    if path.suffix != ".json":
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        if len(raw) > 512_000:
            return None
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    # Claude credentials / config metadata (never expose tokens!)
    if agent_id in ("claude-code", "claude-code-api"):
        oauth = data.get("claudeAiOauth")
        if isinstance(oauth, dict):
            sub = oauth.get("subscriptionType") or oauth.get("rateLimitTier")
            if isinstance(sub, str) and sub.strip():
                return f"Plan: {sub.strip()}"
        acct = data.get("oauthAccount")
        if isinstance(acct, dict):
            email = acct.get("emailAddress")
            if isinstance(email, str) and email.strip():
                return email.strip()

    # Codex auth.json metadata
    if agent_id == "codex":
        tokens = data.get("tokens")
        if isinstance(tokens, dict) and tokens.get("account_id"):
            return "ChatGPT Account"
        if data.get("OPENAI_API_KEY"):
            return "API Key"

    return None


def _extract_dir_usage_summary(agent_id: str, state_path: Path) -> str | None:
    """Check on-disk usage or stats files when present."""
    # Claude stats-cache.json if present
    if agent_id in ("claude-code", "claude-code-api"):
        stats_file = state_path / "stats-cache.json"
        if stats_file.is_file():
            try:
                data = json.loads(
                    stats_file.read_text(encoding="utf-8", errors="replace")
                )
                if isinstance(data, dict):
                    total_sessions = data.get("totalSessions")
                    if isinstance(total_sessions, int) and total_sessions > 0:
                        return f"{total_sessions} local CLI sessions"
            except Exception:
                pass
    return None
