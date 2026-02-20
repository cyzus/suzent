import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ValidationError

from .logger import get_logger


def get_project_root() -> Path:
    """Get project root, handling both dev and bundled scenarios."""

    # In bundled mode, Tauri always sets SUZENT_APP_DATA to the app data directory
    # where config/, skills/, etc. are synced by the Rust side
    app_data = os.getenv("SUZENT_APP_DATA")
    if app_data:
        return Path(app_data)

    # Development mode
    # Project root (two levels above this file: src/suzent -> src -> project root)
    return Path(__file__).resolve().parents[2]


PROJECT_DIR = get_project_root()

DATA_DIR = PROJECT_DIR / ".suzent"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _normalize_keys(d: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize incoming keys to lowercase snake style the model expects.

    Accepts SCREAMING_SNAKE_CASE (TITLE) or snake_case (title).
    """
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if not isinstance(k, str):
            continue
        nk = k.strip().lower().replace("-", "_").replace(" ", "_")
        out[nk] = v
    return out


def get_tool_options() -> List[str]:
    """Discover available tool class names from the centralized registry."""
    from suzent.tools.registry import list_available_tools

    return list_available_tools()


def get_effective_volumes(custom_volumes: Optional[List[str]] = None) -> List[str]:
    """
    Calculate effective sandbox volumes by merging global config and per-chat volumes.
    Also auto-mounts the 'skills' directory if not already present.
    """
    global_volumes = CONFIG.sandbox_volumes or []
    per_chat_volumes = custom_volumes or []

    raw_volumes = list(set(global_volumes + per_chat_volumes))
    volumes = []

    from .tools.path_resolver import PathResolver

    for vol in raw_volumes:
        parsed = PathResolver.parse_volume_string(vol)
        if parsed:
            host, container = parsed
            # Resolve relative host paths against PROJECT_DIR
            if not Path(host).is_absolute():
                host = str((PROJECT_DIR / host).resolve())
                vol = f"{host}:{container}"

        volumes.append(vol)

    # Auto-mount skills directory if not already mapped
    if not any(v.endswith(":/mnt/skills") for v in volumes):
        skills_resolved = str((PROJECT_DIR / "skills").resolve())
        volumes.append(f"{skills_resolved}:/mnt/skills")

    return volumes


class ConfigModel(BaseModel):
    title: str = "SUZENT"
    server_url: str = "http://localhost:8000/chat"
    code_tag: str = "<code>"

    model_options: List[str] = []
    agent_options: List[str] = ["CodeAgent", "ToolcallingAgent"]

    default_tools: List[str] = [
        "WebSearchTool",
        "PlanningTool",
        "ReadFileTool",
        "WriteFileTool",
        "EditFileTool",
        "GlobTool",
        "GrepTool",
        "BashTool",
    ]
    tool_options: Optional[List[str]] = None

    mcp_urls: Dict[str, Any] = {}
    mcp_stdio_params: Dict[str, Any] = {}
    mcp_enabled: Dict[str, bool] = {}

    instructions: str = ""
    additional_authorized_imports: List[str] = []

    # Text-to-Speech
    tts_model: str = ""
    tts_voice: str = ""

    # Embedding
    embedding_model: Optional[str] = None
    embedding_dimension: int = 0

    # Memory
    memory_enabled: bool = False
    markdown_memory_enabled: bool = True
    extraction_model: Optional[str] = None
    user_id: str = "default-user"
    lancedb_uri: str = str(DATA_DIR / "memory")

    # Sandbox
    sandbox_enabled: bool = False
    sandbox_server_url: str = "http://localhost:7263"
    sandbox_data_path: str = str(DATA_DIR / "sandbox")
    sandbox_volumes: List[str] = []

    # Workspace (host mode execution root)
    workspace_root: str = str(DATA_DIR)

    # Node system
    nodes_enabled: bool = True
    node_auth_mode: str = "open"  # "open" | "approve" | "token"

    # Session lifecycle
    session_daily_reset_hour: int = 0
    session_idle_timeout_minutes: int = 0
    jsonl_transcripts_enabled: bool = True
    transcript_indexing_enabled: bool = False

    # Context management
    max_history_steps: int = 20
    max_context_tokens: int = 800_000

    @classmethod
    def load_from_files(cls) -> "ConfigModel":
        logger = get_logger(__name__)
        # Use the configured project root so config files are located at <project>/config
        cfg_dir = PROJECT_DIR / "config"

        # Load example and default files separately and merge them so that
        # keys from `default.yaml` override the values from
        # `default.example.yaml` on a per-key basis.
        example_path = cfg_dir / "default.example.yaml"
        default_path = cfg_dir / "default.yaml"

        example_data: Dict[str, Any] = {}
        default_data: Dict[str, Any] = {}
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

        data = {**example_data, **default_data}
        loaded_path = loaded_files[-1] if loaded_files else None

        try:
            if data:
                cfg = cls.model_validate(data)
            else:
                cfg = cls()
        except ValidationError as ve:
            logger.error("Config validation error: {}", ve)
            raise

        if not cfg.tool_options:
            try:
                discovered = get_tool_options()
            except Exception:
                discovered = []
            combined = list(dict.fromkeys(discovered + cfg.default_tools))
            cfg.tool_options = combined

        if loaded_path is not None:
            logger.info("Loaded configuration overrides from {}", loaded_path)
        return cfg

    def reload(self) -> None:
        """Reload configuration from disk."""
        new_config = self.load_from_files()
        for field in self.model_fields:
            setattr(self, field, getattr(new_config, field))

        logger = get_logger(__name__)
        logger.info("Configuration reloaded from disk.")


CONFIG = ConfigModel.load_from_files()
