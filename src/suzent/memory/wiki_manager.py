"""Wiki memory management utilities.

The wiki IS the notebook. No subfolder — schema.md, index.md, and log.md live at the
notebook root alongside the user's own notes. WikiManager only bootstraps these three
navigation files on first init; the agent reads and writes the vault via file tools.
"""

from pathlib import Path

from suzent.config import PROJECT_DIR
from suzent.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_SCHEMA_PATH = PROJECT_DIR / "skills" / "notebook" / "schema_example.md"


class WikiManager:
    """Bootstrap wiki navigation files at the notebook root."""

    def __init__(self, notebook_path: str):
        self._root = Path(notebook_path)
        self._ensure_structure()

    def _ensure_structure(self) -> None:
        """Seed schema.md, index.md, and log.md at the notebook root if missing."""
        self._root.mkdir(parents=True, exist_ok=True)

        schema_path = self._root / "schema.md"
        if not schema_path.exists():
            schema_path.write_text(
                _DEFAULT_SCHEMA_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

        index_path = self._root / "index.md"
        if not index_path.exists():
            index_path.write_text(
                "# Notebook Index\nLast updated: -\n\n"
                "_Run the ingest skill to populate._\n",
                encoding="utf-8",
            )

        log_path = self._root / "log.md"
        if not log_path.exists():
            log_path.write_text("# Notebook Log\n\n", encoding="utf-8")

        logger.debug(f"Wiki structure ensured at {self._root}")
