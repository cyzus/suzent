"""Filesystem locations and network defaults for a Suzent installation.

Deliberately free of pydantic and of the configuration model. Roughly half the
module-level imports of ``suzent.config`` want nothing but these constants, and
making them pay for the model meant every CLI invocation imported pydantic and
the permissions schema to learn a port number.
"""

import hashlib
import os
import re
import shutil
from pathlib import Path

from suzent.logger import get_logger

DEFAULT_PORT: int = int(os.getenv("SUZENT_PORT", "25314"))
MESH_PORT: int = 25314
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
# Bundled skills are read directly from the installation/repository. These
# aliases remain public for compatibility, but no managed copy is created.
OFFICIAL_SKILLS_DIR = PROJECT_DIR / "skills"
USER_SKILLS_DIR = SKILLS_ROOT_DIR
EXTERNAL_SKILLS_DIR = SKILLS_ROOT_DIR / "external"
LEGACY_USER_SKILLS_DIR = SKILLS_ROOT_DIR / "user"

for _dir in (
    RUNTIME_DIR,
    CACHE_DIR,
    USER_CONFIG_DIR,
    SKILLS_ROOT_DIR,
):
    _dir.mkdir(parents=True, exist_ok=True)


def _external_source_id(path: Path) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", path.name.strip()).strip("-")
    if not slug:
        slug = "skills"
    digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}"


def get_external_skill_sources() -> list[tuple[Path, Path]]:
    """Return configured external roots and stable legacy identity paths."""
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
    """Move skills from the former ``skills/user`` bucket into the flat root."""
    if not LEGACY_USER_SKILLS_DIR.is_dir():
        return
    for child in LEGACY_USER_SKILLS_DIR.iterdir():
        if not child.is_dir() or not (child / "SKILL.md").exists():
            continue
        target = SKILLS_ROOT_DIR / child.name
        if not target.exists():
            child.replace(target)


def sync_managed_skills_dirs() -> Path:
    """Run the one-way user-skill migration without copying source libraries."""
    migrate_legacy_user_skills_dir()
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
