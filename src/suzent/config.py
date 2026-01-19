import os
import importlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .logger import get_logger  # project logger required

from smolagents import Tool as _SmolTool  # type: ignore

from pydantic import BaseModel, ValidationError

# Project root (two levels above this file: src/suzent -> src -> project root)
PROJECT_DIR = Path(__file__).resolve().parents[2]


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
    """Discover Tool subclasses in the suzent.tools package and return their class names."""
    tools_dir = PROJECT_DIR / "src" / "suzent" / "tools"
    tool_options: List[str] = []
    if not tools_dir.exists():
        return tool_options
    for f in os.listdir(tools_dir):
        if f.endswith(".py") and not f.startswith("__"):
            module_name = f"suzent.tools.{f[:-3]}"
            try:
                module = importlib.import_module(module_name)
            except Exception:
                continue
            for attribute_name in dir(module):
                attribute = getattr(module, attribute_name)
                if (
                    isinstance(attribute, type)
                    and issubclass(attribute, _SmolTool)
                    and attribute is not _SmolTool
                    and getattr(attribute, "__module__", "").startswith("suzent.tools")
                ):
                    tool_options.append(attribute.__name__)

    # Note: Memory tools are added dynamically when memory system initializes
    # See agent_manager.init_memory_system()

    return tool_options


def get_effective_volumes(custom_volumes: Optional[List[str]] = None) -> List[str]:
    """
    Calculate effective sandbox volumes by merging global config and per-chat volumes.
    Also auto-mounts the 'skills' directory if not present.

    Args:
        custom_volumes: Optional list of per-chat volume strings.

    Returns:
        Merged list of volume strings.
    """
    global_volumes = CONFIG.sandbox_volumes or []
    per_chat_volumes = custom_volumes or []

    # Merge and deduplicate
    volumes = list(set(global_volumes + per_chat_volumes))

    # Auto-mount skills directory
    # Host path: relative 'skills' -> resolves to {container_workspace}/skills
    # Container path: /mnt/skills
    mount_str = "skills:/mnt/skills"
    if mount_str not in volumes:
        volumes.append(mount_str)

    return volumes


class ConfigModel(BaseModel):
    title: str = "SUZENT"
    server_url: str = "http://localhost:8000/chat"
    code_tag: str = "<code>"

    # Keep model options empty by default; prefer specifying models in YAML
    model_options: List[str] = []
    agent_options: List[str] = ["CodeAgent", "ToolcallingAgent"]

    # Default tools available; discovery will merge with these if tool_options not set
    default_tools: List[str] = [
        "WebSearchTool",
        "PlanningTool",
        "ReadFileTool",
        "WriteFileTool",
        "EditFileTool",
        "GlobTool",
        "GrepTool",
    ]
    tool_options: Optional[List[str]] = None

    # No MCP endpoints by default; provide via YAML when needed
    mcp_urls: Dict[str, str] = {}

    # MCP stdio params default empty; user can configure stdio-backed MCPs in YAML
    mcp_stdio_params: Dict[str, Any] = {}

    instructions: str = ""
    additional_authorized_imports: List[str] = []

    # Embedding configuration
    embedding_model: str = None
    embedding_dimension: int = 0

    # Memory system
    memory_enabled: bool = False
    extraction_model: str = (
        None  # LLM model for fact extraction (None = use heuristics)
    )
    user_id: str = "default-user"  # Default user identifier for memory system
    lancedb_uri: str = ".suzent/data/memory"  # Path to LanceDB storage

    # Sandbox system
    sandbox_enabled: bool = False
    sandbox_server_url: str = "http://localhost:7263"
    sandbox_data_path: str = "data/sandbox-data"
    sandbox_volumes: List[
        str
    ] = []  # Additional volume mounts (format: "host_path:container_path")

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
                try:
                    import yaml  # type: ignore

                    with p.open("r", encoding="utf-8") as fh:
                        return yaml.safe_load(fh) or {}
                except Exception:
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

        # Merge with default_data taking precedence over example_data
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

        # If tool_options missing or falsy, discover tools from disk and combine with defaults
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


# Load configuration at import time and expose typed CONFIG instance
CONFIG = ConfigModel.load_from_files()
# Export CONFIG (typed) and helper get_tool_options
