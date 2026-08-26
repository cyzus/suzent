"""The Suzent configuration model and the file layering that populates it.

Split from the package ``__init__`` so that importing a path constant does not
also import pydantic, the permissions schema and this loader. See
:mod:`suzent.config.paths`.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ValidationError, field_validator

from suzent.logger import get_logger
from suzent.permissions.loader import load_permission_overrides
from suzent.config.paths import (
    DATA_DIR,
    DEFAULT_HOST,
    DEFAULT_PORT,
    PROJECT_DIR,
    USER_CONFIG_DIR,
)


def _normalize_keys(d: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize incoming keys to lowercase snake style the model expects."""
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if not isinstance(k, str):
            continue
        nk = k.strip().lower().replace("-", "_").replace(" ", "_")
        out[nk] = v
    return out


def get_tool_options() -> List[str]:
    """Discover available tool class names from the centralized registry."""
    from suzent.tools.registry import list_configurable_tools

    return list_configurable_tools()


def get_effective_volumes(custom_volumes: Optional[List[str]] = None) -> List[str]:
    """Calculate effective sandbox volumes by merging global and per-chat volumes."""
    global_volumes = CONFIG.sandbox_volumes or []
    per_chat_volumes = custom_volumes or []

    raw_volumes = list(set(global_volumes + per_chat_volumes))
    volumes = []

    from suzent.tools.filesystem.path_resolver import PathResolver

    for vol in raw_volumes:
        parsed = PathResolver.parse_volume_string(vol)
        if parsed:
            host, container = parsed
            if not Path(host).is_absolute():
                host = str((PROJECT_DIR / host).resolve())
                vol = f"{host}:{container}"

        volumes.append(vol)

    # Always expose the notebook vault at /mnt/notebook so the agent can read/write
    # durable knowledge (the dream consolidation agent + the "file a query result"
    # flow). Defaults to CONFIG.notebook_dir unless the user mapped their own.
    if not any(v.endswith(":/mnt/notebook") for v in volumes):
        notebook_resolved = str(Path(CONFIG.notebook_dir).resolve())
        Path(notebook_resolved).mkdir(parents=True, exist_ok=True)
        volumes.append(f"{notebook_resolved}:/mnt/notebook")

    return volumes


class ConfigModel(BaseModel):
    title: str = "SUZENT"
    server_url: str = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/chat"
    code_tag: str = "<code>"

    model_options: List[str] = []
    agent_options: List[str] = ["Agent"]

    default_tools: List[str] = [
        "WebSearchTool",
        "GoalTool",
        "TaskCreateTool",
        "TaskUpdateTool",
        "TaskListTool",
        "ReadFileTool",
        "WriteFileTool",
        "EditFileTool",
        "GlobTool",
        "GrepTool",
        "RunCommandTool",
        "StartCommandTool",
        "CheckCommandTool",
        "StopCommandTool",
        "ImageGenerationTool",
        "AgentTool",
        "MemorySearchTool",
        "SessionSearchTool",
    ]
    tool_options: Optional[List[str]] = None

    @field_validator("default_tools", "tool_options", mode="before")
    @classmethod
    def migrate_legacy_shell_tools(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        from suzent.tools.names import migrate_shell_tool_names

        return migrate_shell_tool_names(value)

    instructions: str = ""
    additional_authorized_imports: List[str] = []

    # Unified role → model mapping (new)
    role_models: Dict[str, Any] = {}

    tts_model: str = ""
    tts_voice: str = ""

    embedding_model: Optional[str] = None
    embedding_dimension: int = 0
    # Hard cap on a single embedding API call. Without this, a slow/unreachable
    # provider blocks memory search indefinitely (the tool appears to hang).
    embedding_timeout: float = 30.0

    image_generation_model: Optional[str] = None

    memory_enabled: bool = False
    markdown_memory_enabled: bool = True
    extraction_model: Optional[str] = None

    # --- Notebook vault + dream consolidation ---
    notebook_dir: str = str(DATA_DIR / "notebook")
    memory_consolidation_enabled: bool = True
    memory_consolidation_min_hours: float = 24.0
    memory_consolidation_min_facts: int = 20
    memory_consolidation_interval_seconds: int = 1800
    memory_consolidation_timeout_seconds: int = 600
    memory_consolidation_max_days: int = 14
    memory_consolidation_max_retries: int = 3
    # Confirmations and expiring claims are queued by the write path, not by a daily
    # log, so an install whose conversations only repeat known facts is "caught up"
    # while the queues grow. This many pending confirmations makes a run worth doing
    # on its own. Kept well above a single chatty afternoon so it never competes with
    # ordinary ingest.
    memory_consolidation_min_confirmations: int = 25
    memory_consolidation_memory_max_lines: int = 200
    memory_consolidation_model: Optional[str] = None
    memory_dream_tools: List[str] = [
        "ReadFileTool",
        "WriteFileTool",
        "EditFileTool",
        "GlobTool",
        "GrepTool",
        "MemorySearchTool",
    ]
    # Lint phase: a periodic editorial audit of the vault (contradictions, broken
    # links, orphans, decay) run by the same dream runner AFTER ingest catches up.
    # Distinct prompt + its own (slower) gate; ingest always takes priority.
    memory_lint_enabled: bool = True
    memory_lint_min_days: float = 7.0

    cron_presets: List[Dict[str, Any]] = []
    user_id: str = "default-user"
    lancedb_uri: str = str(DATA_DIR / "memory")

    sandbox_enabled: bool = False
    sandbox_image: str = "python:3.11-slim"
    sandbox_network: str = "bridge"
    sandbox_idle_timeout_minutes: int = 30
    sandbox_setup_command: str = ""
    sandbox_env: Dict[str, Any] = {}
    sandbox_data_path: str = str(DATA_DIR / "sandbox")
    sandbox_volumes: List[str] = []
    shell_env: Optional[Dict[str, str]] = None
    shell_denied_env_patterns: List[str] = []

    workspace_root: str = str(DATA_DIR)

    permission_policies: Dict[str, Dict[str, Any]] = {}
    permission_rules: List[Dict[str, Any]] = []
    # Permission mode new chats inherit when the client does not pin one.
    default_permission_mode: str = "default"

    nodes_enabled: bool = True
    # Advertise this server over mDNS and allow LAN/Tailscale peer discovery.
    node_discovery_enabled: bool = True
    # Bind the server to all interfaces (0.0.0.0) so peer devices can reach it,
    # overriding a loopback-only SUZENT_HOST. Required for cross-device nodes;
    # exposes the HTTP API on the network, so keep on trusted/tailnet only.
    node_lan_bind: bool = False

    # Publish an A2A Agent Card at /.well-known/agent-card.json, making this
    # device discoverable and callable by any A2A-speaking agent. Off by
    # default: the card is unauthenticated by design, so serving it reveals the
    # device name and skill list to anything that can reach the port.
    a2a_enabled: bool = False
    # Operator-facing name on the published card. Blank falls back to hostname.
    a2a_agent_name: str = ""

    session_daily_reset_hour: int = 0
    session_idle_timeout_minutes: int = 0
    jsonl_transcripts_enabled: bool = True
    transcript_indexing_enabled: bool = False

    max_context_tokens: int = 800_000
    context_compaction_trigger: float = 0.80
    context_soft_trim_threshold: float = 0.60
    context_hard_trim_threshold: float = 0.80
    compaction_keep_recent_turns: int = 3
    compaction_chunk_size: int = 20
    compaction_timeout_seconds: int = 60

    plan_watcher_interval: float = 2.0

    # Goal mode: max autonomous continuation turns before auto-pausing.
    goals_max_turns: int = 20

    @classmethod
    def load_from_files(cls) -> "ConfigModel":
        logger = get_logger(__name__)
        cfg_dir = PROJECT_DIR / "config"
        user_cfg_dir = USER_CONFIG_DIR

        example_path = cfg_dir / "default.example.yaml"
        default_path = cfg_dir / "default.yaml"
        user_default_path = user_cfg_dir / "default.yaml"
        # Machine-specific overrides — never synced across devices.
        # Put sandbox_volumes, sandbox_data_path, workspace_root, lancedb_uri etc. here.
        user_local_path = user_cfg_dir / "local.yaml"

        example_data: Dict[str, Any] = {}
        default_data: Dict[str, Any] = {}
        user_data: Dict[str, Any] = {}
        local_data: Dict[str, Any] = {}
        loaded_files: List[Path] = []

        def _read_file(p: Path) -> Dict[str, Any]:
            try:
                import yaml  # type: ignore

                with p.open("r", encoding="utf-8") as fh:
                    return yaml.safe_load(fh) or {}
            except Exception:
                pass

            try:
                with p.open("r", encoding="utf-8") as fh:
                    return json.load(fh)
            except Exception as exc:
                logger.debug("Failed to parse config file {}: {}", p, exc)
                return {}

        if example_path.exists():
            raw_example = _read_file(example_path)
            if isinstance(raw_example, dict):
                example_data = _normalize_keys(raw_example)
                loaded_files.append(example_path)

        if default_path.exists():
            raw_default = _read_file(default_path)
            if isinstance(raw_default, dict):
                default_data = _normalize_keys(raw_default)
                loaded_files.append(default_path)

        if user_default_path.exists():
            raw_user = _read_file(user_default_path)
            if isinstance(raw_user, dict):
                user_data = _normalize_keys(raw_user)
                loaded_files.append(user_default_path)

        if user_local_path.exists():
            raw_local = _read_file(user_local_path)
            if isinstance(raw_local, dict):
                local_data = _normalize_keys(raw_local)
                loaded_files.append(user_local_path)

        data = {**example_data, **default_data, **user_data, **local_data}

        try:
            permission_overrides = load_permission_overrides(
                PROJECT_DIR, logger, USER_CONFIG_DIR
            )
            if permission_overrides:
                data.update(permission_overrides)
        except Exception as exc:
            logger.warning("Failed to load permissions config overlays: {}", exc)

        loaded_path = loaded_files[-1] if loaded_files else None

        try:
            if data:
                cfg = cls.model_validate(data)
            else:
                cfg = cls()
        except ValidationError as ve:
            logger.error("Config validation error: {}", ve)
            raise

        if loaded_path is not None:
            logger.info("Loaded configuration overrides from {}", loaded_path)
        return cfg

    def ensure_tool_options(self) -> List[str]:
        """Return the tool catalog, discovering it from the registry on first use.

        Discovery imports every tool module, and with them pydantic-ai, MCP and
        the LanceDB stack -- roughly half a second. Keeping it out of
        ``load_from_files`` means the CLI no longer pays for the whole agent
        runtime just to read a config file.
        """
        if not self.tool_options:
            try:
                discovered = get_tool_options()
            except Exception:
                discovered = []
            self.tool_options = list(dict.fromkeys(discovered + self.default_tools))
        return self.tool_options

    def reload(self) -> None:
        """Reload configuration from disk."""
        new_config = self.load_from_files()
        for field in self.model_fields:
            setattr(self, field, getattr(new_config, field))

        logger = get_logger(__name__)
        logger.info("Configuration reloaded from disk.")


CONFIG = ConfigModel.load_from_files()
