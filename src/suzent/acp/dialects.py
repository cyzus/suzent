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


def _normalize_cwd_for_match(cwd: str) -> str:
    """Normalize a path string for case-insensitive workspace comparison."""
    cleaned = str(cwd or "").strip()
    if cleaned.lower().startswith("file:///"):
        cleaned = cleaned[8:]
    elif cleaned.lower().startswith("file://"):
        cleaned = cleaned[7:]
    cleaned = cleaned.replace("\\", "/").rstrip("/")
    return cleaned.lower()


def _encode_claude_project_slug(cwd: str) -> str:
    """Encode a filesystem path the way Claude Code names ``~/.claude/projects/<slug>``."""
    import re

    cleaned = str(cwd or "").strip().rstrip("\\/")
    return re.sub(r"[^a-zA-Z0-9]", "-", cleaned).lower()


def _clean_session_title(raw: str, max_len: int = 120) -> str:
    text = " ".join(str(raw or "").split())
    if not text:
        return ""
    return text[: max_len - 1] + "…" if len(text) > max_len else text


def discover_local_agent_sessions(
    agent_id: str | None = None,
    cwd: str | None = None,
    *,
    query: str | None = None,
    limit: int = 15,
    home: Path | None = None,
) -> list[dict[str, Any]]:
    """Zero-wakeup local disk discovery of external CLI sessions (metadata only).

    Scans on-disk session files for ``agent_id`` (or all supported agents when
    omitted/``"all"``) without spawning any subprocess. Returns a list of
    ``{session_id, agent_id, title, cwd, updated_at, mtime}`` sorted
    newest-first, optionally filtered by ``query``.
    """
    base_home = home or Path.home()
    target_cwd_norm = _normalize_cwd_for_match(cwd) if cwd else ""
    aid = (agent_id or "").strip().lower()
    q_norm = (query or "").strip().lower()
    scan_limit = max(limit * 4, 60) if q_norm else limit

    items: list[dict[str, Any]] = []
    if not aid or aid in ("all", "claude-code", "claude-code-api", "claude-acp"):
        items.extend(
            _discover_claude_sessions(
                base_home, target_cwd_norm, cwd or "", limit=scan_limit
            )
        )
    if not aid or aid in ("all", "codex"):
        items.extend(
            _discover_codex_sessions(base_home, target_cwd_norm, limit=scan_limit)
        )

    if q_norm:
        items = [
            it
            for it in items
            if q_norm in str(it.get("title") or "").lower()
            or q_norm in str(it.get("session_id") or "").lower()
            or q_norm in str(it.get("cwd") or "").lower()
            or q_norm in str(it.get("agent_id") or "").lower()
        ]

    items.sort(key=lambda it: float(it.get("mtime") or 0.0), reverse=True)
    return items[:limit]


def _discover_claude_sessions(
    home: Path,
    target_cwd_norm: str,
    raw_cwd: str,
    *,
    limit: int = 15,
) -> list[dict[str, Any]]:
    projects_root = home / ".claude" / "projects"
    if not projects_root.is_dir():
        return []

    target_slug = _encode_claude_project_slug(raw_cwd) if raw_cwd else ""
    candidate_dirs: list[Path] = []
    try:
        for entry in projects_root.iterdir():
            if not entry.is_dir():
                continue
            name_lower = entry.name.lower()
            if target_slug and name_lower == target_slug:
                candidate_dirs.insert(0, entry)
            elif not target_slug or name_lower.startswith(target_slug):
                candidate_dirs.append(entry)
    except OSError:
        return []

    files: list[tuple[float, Path]] = []
    for d in candidate_dirs:
        try:
            for f in d.glob("*.jsonl"):
                try:
                    st = f.stat()
                    if st.st_size > 0:
                        files.append((st.st_mtime, f))
                except OSError:
                    continue
        except OSError:
            continue

    files.sort(key=lambda item: item[0], reverse=True)
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for mtime, fpath in files:
        if len(results) >= limit:
            break
        session_id = fpath.stem
        if not session_id or session_id in seen_ids:
            continue
        custom_title = ""
        first_user_title = ""
        session_cwd = ""
        updated_iso = ""
        is_sidechain = False
        try:
            with fpath.open("r", encoding="utf-8", errors="replace") as fh:
                for idx, line in enumerate(fh):
                    if idx > 80:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    if obj.get("isSidechain") is True:
                        is_sidechain = True
                        break
                    if not session_cwd and isinstance(obj.get("cwd"), str):
                        session_cwd = obj["cwd"]
                    if isinstance(obj.get("timestamp"), str):
                        updated_iso = obj["timestamp"]
                    ltype = obj.get("type")
                    if ltype == "custom-title" and isinstance(
                        obj.get("customTitle"), str
                    ):
                        ct = obj["customTitle"].strip()
                        if ct and ct.lower() != "new session":
                            custom_title = _clean_session_title(ct)
                    elif ltype == "summary" and isinstance(obj.get("summary"), str):
                        st_txt = obj["summary"].strip()
                        if st_txt and not custom_title:
                            custom_title = _clean_session_title(st_txt)
                    elif not first_user_title:
                        if ltype == "queue-operation" and isinstance(
                            obj.get("content"), str
                        ):
                            first_user_title = _clean_session_title(obj["content"])
                        elif ltype == "user":
                            msg = obj.get("message")
                            if isinstance(msg, dict):
                                content = msg.get("content")
                                if isinstance(content, str):
                                    first_user_title = _clean_session_title(content)
                                elif isinstance(content, list):
                                    for blk in content:
                                        if isinstance(blk, dict) and isinstance(
                                            blk.get("text"), str
                                        ):
                                            first_user_title = _clean_session_title(
                                                blk["text"]
                                            )
                                            if first_user_title:
                                                break
                    if custom_title and session_cwd:
                        break
        except OSError:
            continue

        title = custom_title or first_user_title
        if is_sidechain or not title:
            continue
        if (
            target_cwd_norm
            and session_cwd
            and _normalize_cwd_for_match(session_cwd) != target_cwd_norm
        ):
            continue

        seen_ids.add(session_id)
        results.append(
            {
                "session_id": session_id,
                "agent_id": "claude-code",
                "title": title,
                "cwd": session_cwd or raw_cwd,
                "updated_at": updated_iso,
                "mtime": mtime,
            }
        )
    return results


def _load_codex_session_titles(home: Path) -> dict[str, str]:
    """Read AI-generated thread titles from ``~/.codex/session_index.jsonl``."""
    index_file = home / ".codex" / "session_index.jsonl"
    if not index_file.is_file():
        return {}
    titles: dict[str, str] = {}
    try:
        with index_file.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                sid = str(obj.get("id") or "").strip()
                tname = str(obj.get("thread_name") or "").strip()
                if sid and tname and not tname.startswith("<"):
                    cleaned = _clean_session_title(tname)
                    if cleaned:
                        titles[sid] = cleaned
    except OSError:
        return {}
    return titles


def _discover_codex_sessions(
    home: Path,
    target_cwd_norm: str,
    *,
    limit: int = 15,
) -> list[dict[str, Any]]:
    sessions_root = home / ".codex" / "sessions"
    if not sessions_root.is_dir():
        return []

    indexed_titles = _load_codex_session_titles(home)

    files: list[tuple[float, Path]] = []
    try:
        for f in sessions_root.rglob("rollout-*.jsonl"):
            try:
                st = f.stat()
                if st.st_size > 0:
                    files.append((st.st_mtime, f))
            except OSError:
                continue
    except OSError:
        return []

    files.sort(key=lambda item: item[0], reverse=True)
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for mtime, fpath in files:
        if len(results) >= limit:
            break
        session_id = ""
        session_cwd = ""
        updated_iso = ""
        title = ""
        is_subagent = False

        try:
            with fpath.open("r", encoding="utf-8", errors="replace") as fh:
                for idx, line in enumerate(fh):
                    if idx > 50:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    ltype = obj.get("type")
                    payload = (
                        obj.get("payload")
                        if isinstance(obj.get("payload"), dict)
                        else {}
                    )
                    if isinstance(obj.get("timestamp"), str):
                        updated_iso = obj["timestamp"]

                    if ltype == "session_meta":
                        if payload.get(
                            "thread_source"
                        ) == "guardian_review" or isinstance(
                            payload.get("source"), dict
                        ):
                            is_subagent = True
                            break
                        session_id = str(
                            payload.get("id") or payload.get("session_id") or ""
                        ).strip()
                        if isinstance(payload.get("cwd"), str):
                            session_cwd = payload["cwd"]
                        if (
                            target_cwd_norm
                            and session_cwd
                            and _normalize_cwd_for_match(session_cwd) != target_cwd_norm
                        ):
                            is_subagent = True
                            break
                    elif (
                        ltype == "response_item"
                        and payload.get("type") == "message"
                        and payload.get("role") == "user"
                    ):
                        content = payload.get("content")
                        if isinstance(content, list):
                            for blk in content:
                                if isinstance(blk, dict) and isinstance(
                                    blk.get("text"), str
                                ):
                                    txt = blk["text"].strip()
                                    if txt and not txt.startswith("<"):
                                        title = _clean_session_title(txt)
                                        break
                    elif (
                        ltype == "event_msg" and payload.get("type") == "item_completed"
                    ):
                        item = payload.get("item")
                        if isinstance(item, dict) and item.get("type") == "UserMessage":
                            for blk in item.get("content") or []:
                                if isinstance(blk, dict) and isinstance(
                                    blk.get("text"), str
                                ):
                                    txt = blk["text"].strip()
                                    if txt and not txt.startswith("<"):
                                        title = _clean_session_title(txt)
                                        break
                    if session_id and title:
                        break
        except OSError:
            continue

        if session_id and session_id in indexed_titles:
            title = indexed_titles[session_id]
        if is_subagent or not session_id or not title or session_id in seen_ids:
            continue
        if (
            target_cwd_norm
            and session_cwd
            and _normalize_cwd_for_match(session_cwd) != target_cwd_norm
        ):
            continue

        seen_ids.add(session_id)
        results.append(
            {
                "session_id": session_id,
                "agent_id": "codex",
                "title": title,
                "cwd": session_cwd,
                "updated_at": updated_iso,
                "mtime": mtime,
            }
        )
    return results
