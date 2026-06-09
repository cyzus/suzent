"""Wiki vault bootstrap.

Seeds the always-on notebook vault: navigation files (schema.md, index.md,
log.md) and the zone folders defined by the schema. After bootstrap the agent
(and the dream consolidation agent) own the vault via file tools; the indexer
keeps its pages searchable in LanceDB.
"""

from pathlib import Path
from typing import Optional

from suzent.config import PROJECT_DIR, CONFIG
from suzent.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_SCHEMA_PATH = PROJECT_DIR / "skills" / "notebook" / "schema_example.md"

# Zone folders (mirrors skills/notebook/schema_example.md). 3_Personal holds the
# user-memory facts the dream consolidates from the daily logs.
_ZONES = [
    "0_Inbox",
    "1_Projects",
    "2_Wiki/Concepts",
    "2_Wiki/Literature",
    "2_Wiki/Syntheses",
    "2_Wiki/Entities",
    "3_Personal",
    "4_Assets",
    "5_Archives",
]


class WikiManager:
    """Bootstrap the notebook vault (nav files + zone folders)."""

    def __init__(self, notebook_path: Optional[str] = None):
        self._root = Path(notebook_path or CONFIG.notebook_dir)
        self._ensure_structure()

    def _ensure_structure(self) -> None:
        """Seed nav files + zone folders at the vault root if missing (idempotent)."""
        self._root.mkdir(parents=True, exist_ok=True)

        schema_path = self._root / "schema.md"
        if not schema_path.exists():
            try:
                schema_path.write_text(
                    _DEFAULT_SCHEMA_PATH.read_text(encoding="utf-8"), encoding="utf-8"
                )
            except Exception as e:
                logger.warning(f"Could not seed schema.md: {e}")

        index_path = self._root / "index.md"
        if not index_path.exists():
            index_path.write_text(
                "# Notebook Index\nLast updated: -\n\n"
                "_Populated by memory consolidation (the dream) and the ingest skill._\n",
                encoding="utf-8",
            )

        log_path = self._root / "log.md"
        if not log_path.exists():
            log_path.write_text("# Notebook Log\n\n", encoding="utf-8")

        for zone in _ZONES:
            (self._root / zone).mkdir(parents=True, exist_ok=True)

        logger.debug(f"Wiki vault ensured at {self._root}")
