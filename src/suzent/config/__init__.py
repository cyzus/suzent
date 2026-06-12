import json
import os
import shutil
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ValidationError

from ..logger import get_logger
from suzent.permissions.loader import load_permission_overrides

DEFAULT_PORT: int = int(os.getenv("SUZENT_PORT", "25314"))
DEFAULT_HOST: str = os.getenv("SUZENT_HOST", "localhost")


def get_project_root() -> Path:
    """Get source/project root, handling dev, bundled, and installed CLI scenarios."""

    current_file = Path(__file__).resolve()
    dev_root = current_file.parents[3]
    if (dev_root / "pyproject.toml").exists():
        return dev_root

    import platform

    system = platform.system()
    home = Path.home()

    canonical_path = None
    if system == "Windows":
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            canonical_path = Path(local_app_data) / "com.suzent.app"
    elif system == "Darwin":
        canonical_path = home / "Library/Application Support/com.suzent.app"
    else:
        xdg = os.getenv("XDG_DATA_HOME")
        if xdg:
            canonical_path = Path(xdg) / "com.suzent.app"
        else:
            canonical_path = home / ".local/share/com.suzent.app"

    if canonical_path and canonical_path.exists():
        return canonical_path

    if canonical_path:
        return canonical_path

    return dev_root


def get_data_dir() -> Path:
    """Get SUZENT's user data directory."""
    override = os.getenv("SUZENT_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".suzent").resolve()


def _is_effectively_empty(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        return not any(path.iterdir())
    except OSError:
        return False


def _migrate_legacy_data_dir(project_dir: Path, data_dir: Path) -> None:
    """Copy legacy repo-local .suzent data into the user data directory once."""
    legacy_dir = project_dir / ".suzent"
    if legacy_dir.resolve() == data_dir.resolve() or not legacy_dir.exists():
        return
    if not _is_effectively_empty(data_dir):
        return

    logger = get_logger(__name__)
    try:
        data_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(legacy_dir, data_dir, dirs_exist_ok=True)
        migrated_marker = legacy_dir / "MIGRATED.md"
        migrated_marker.write_text(
            f"SUZENT data has been migrated to the user data directory:\n{data_dir}\n",
            encoding="utf-8",
        )
        logger.info(
            "Migrated legacy data directory from {} to {}", legacy_dir, data_dir
        )
    except Exception as exc:
        logger.warning(
            "Failed to migrate legacy data directory from {} to {}: {}",
            legacy_dir,
            data_dir,
            exc,
        )


PROJECT_DIR = get_project_root()

DATA_DIR = get_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)
_migrate_legacy_data_dir(PROJECT_DIR, DATA_DIR)

RUNTIME_DIR = DATA_DIR / "runtime"
CACHE_DIR = DATA_DIR / "cache"
USER_CONFIG_DIR = DATA_DIR / "config"
SKILLS_ROOT_DIR = DATA_DIR / "skills"
OFFICIAL_SKILLS_DIR = SKILLS_ROOT_DIR / "official"
USER_SKILLS_DIR = SKILLS_ROOT_DIR / "user"
EXTERNAL_SKILLS_DIR = SKILLS_ROOT_DIR / "external"

for _dir in (
    RUNTIME_DIR,
    CACHE_DIR,
    USER_CONFIG_DIR,
    SKILLS_ROOT_DIR,
    OFFICIAL_SKILLS_DIR,
    USER_SKILLS_DIR,
    EXTERNAL_SKILLS_DIR,
):
    _dir.mkdir(parents=True, exist_ok=True)


def _copy_skill_tree(source: Path, target: Path) -> None:
    tmp_target = target.parent / f".{target.name}.tmp"
    if tmp_target.exists():
        shutil.rmtree(tmp_target)
    shutil.copytree(source, tmp_target)
    if target.exists():
        shutil.rmtree(target)
    tmp_target.replace(target)


def _sync_skills_root(source_root: Path, target_root: Path) -> None:
    """Mirror valid skill directories from one root into another root."""
    target_root.mkdir(parents=True, exist_ok=True)
    expected_skills: set[str] = set()

    if source_root.exists():
        for skill_dir in source_root.iterdir():
            if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").exists():
                continue
            expected_skills.add(skill_dir.name)
            _copy_skill_tree(skill_dir, target_root / skill_dir.name)

    for child in target_root.iterdir():
        if child.name.startswith(".") or child.name in expected_skills:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _external_source_id(path: Path) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", path.name.strip()).strip("-")
    if not slug:
        slug = "skills"
    digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}"


def get_external_skill_sources() -> list[tuple[Path, Path]]:
    """Return configured external skill roots and their managed mirror roots."""
    env_value = os.getenv("SKILLS_DIR", "").strip()
    if not env_value:
        return []

    sources: list[tuple[Path, Path]] = []
    seen: set[Path] = set()
    for raw_path in env_value.split(os.pathsep):
        if not raw_path.strip():
            continue
        source = Path(raw_path).expanduser().resolve()
        if source in seen:
            continue
        seen.add(source)
        sources.append((source, EXTERNAL_SKILLS_DIR / _external_source_id(source)))
    return sources


def migrate_legacy_user_skills_dir() -> None:
    """Move legacy flat ~/.suzent/skills/<skill> entries into the user bucket."""
    reserved = {"official", "user", "external"}
    for child in SKILLS_ROOT_DIR.iterdir():
        if (
            not child.is_dir()
            or child.name in reserved
            or not (child / "SKILL.md").exists()
        ):
            continue

        target = USER_SKILLS_DIR / child.name
        if target.exists():
            continue
        child.replace(target)


def sync_managed_skills_dirs() -> Path:
    """Sync official and external skills into the unified skills mount root."""
    migrate_legacy_user_skills_dir()
    _sync_skills_root(PROJECT_DIR / "skills", OFFICIAL_SKILLS_DIR)

    expected_external_roots: set[str] = set()
    for source, target in get_external_skill_sources():
        expected_external_roots.add(target.name)
        _sync_skills_root(source, target)

    for child in EXTERNAL_SKILLS_DIR.iterdir():
        if child.name.startswith(".") or child.name in expected_external_roots:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    return SKILLS_ROOT_DIR


def rebuild_merged_skills_dir() -> Path:
    """Backward-compatible alias for the unified skills sync."""
    return sync_managed_skills_dirs()


_skills_synced = False


def ensure_skills_synced() -> None:
    global _skills_synced
    if not _skills_synced:
        _skills_synced = True
        sync_managed_skills_dirs()


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
    from suzent.tools.registry import list_available_tools

    return list_available_tools()


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

    if not any(v.endswith(":/mnt/skills") for v in volumes):
        SKILLS_ROOT_DIR.mkdir(parents=True, exist_ok=True)
        skills_resolved = str(SKILLS_ROOT_DIR.resolve())
        volumes.append(f"{skills_resolved}:/mnt/skills")

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
        "BashTool",
        "ImageGenerationTool",
        "AgentTool",
    ]
    tool_options: Optional[List[str]] = None

    instructions: str = ""
    additional_authorized_imports: List[str] = []

    # Unified role → model mapping (new)
    role_models: Dict[str, Any] = {}

    tts_model: str = ""
    tts_voice: str = ""

    embedding_model: Optional[str] = None
    embedding_dimension: int = 0

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

    workspace_root: str = str(DATA_DIR)

    permission_policies: Dict[str, Dict[str, Any]] = {}

    nodes_enabled: bool = True
    node_auth_mode: str = "open"

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
