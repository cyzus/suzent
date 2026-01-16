"""
GlobTool - Find files matching a pattern.
"""

from pathlib import Path
from typing import Optional, List

from smolagents.tools import Tool

from suzent.logger import get_logger
from suzent.tools.path_resolver import PathResolver

logger = get_logger(__name__)


class GlobTool(Tool):
    """
    Find files matching a glob pattern.
    """

    name = "GlobTool"
    description = """Find files matching a glob pattern.

Patterns:
- *.py - All Python files in current directory
- **/*.py - All Python files recursively
- data/*.csv - CSV files in data/ folder
- **/*.{js,ts} - All JS and TS files (use multiple patterns)

Examples:
- GlobTool(pattern="**/*.py")
- GlobTool(pattern="*.csv", path="/persistence/data")
"""

    inputs = {
        "pattern": {
            "type": "string",
            "description": "Glob pattern (e.g., **/*.py, *.csv)",
        },
        "path": {
            "type": "string",
            "description": "Directory to search in (default: working directory)",
            "nullable": True,
        },
    }
    output_type = "string"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._resolver: Optional[PathResolver] = None

    def set_context(self, resolver: PathResolver) -> None:
        """Set the path resolver context."""
        self._resolver = resolver

    def forward(self, pattern: str, path: Optional[str] = None) -> str:
        """
        Find files matching a pattern.

        Args:
            pattern: Glob pattern
            path: Base directory to search

        Returns:
            List of matching files, or error message
        """
        if not self._resolver:
            return "Error: GlobTool not initialized. No resolver context."

        try:
            # Resolve base path
            if path:
                base_path = self._resolver.resolve(path)
            else:
                base_path = self._resolver.get_working_dir()

            # Check if base path exists
            if not base_path.exists():
                return f"Error: Directory not found: {path or 'working directory'}"

            if not base_path.is_dir():
                return f"Error: Path is not a directory: {path}"

            # Find matching files
            matches: List[Path] = list(base_path.glob(pattern))

            # Filter to only allowed paths and sort
            valid_matches = []
            for match in matches:
                if self._resolver.is_path_allowed(match):
                    # Convert to virtual path for display
                    virtual = self._resolver.to_virtual_path(match)
                    if virtual:
                        valid_matches.append((virtual, match.is_dir()))
                    else:
                        valid_matches.append((str(match.name), match.is_dir()))

            valid_matches.sort(key=lambda x: (not x[1], x[0].lower()))

            if not valid_matches:
                return f"No files matching '{pattern}' found in {path or 'working directory'}"

            # Format output
            result_lines = [f"Found {len(valid_matches)} matches for '{pattern}':"]
            for vpath, is_dir in valid_matches[:100]:  # Limit to 100 results
                marker = "[DIR] " if is_dir else ""
                result_lines.append(f"  {marker}{vpath}")

            if len(valid_matches) > 100:
                result_lines.append(f"  ... and {len(valid_matches) - 100} more")

            return "\n".join(result_lines)

        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error in glob {pattern}: {e}")
            return f"Error: {str(e)}"
