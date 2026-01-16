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
            # Use unified finder from resolver
            # pattern in GlobTool is the glob pattern itself
            # path is the starting directory
            
            # Special case: if path is not provided but pattern is absolute (starts with /),
            # we treat pattern as relative to root and path as root.
            search_path = path
            search_pattern = pattern
            
            if search_path is None and search_pattern.startswith("/"):
                 # This mimics the logic we had: searching from root/virtual roots
                 # But standard glob pattern "/**/foo" from a root usually implies root search.
                 pass

            found_files = self._resolver.find_files(search_pattern, search_path)
            
            # Format results for GlobTool (needs host path for is_dir check)
            results = []
            for host_path, virtual_path in found_files:
                results.append((virtual_path, host_path.is_dir()))

            # Sort results: Files first, then alphabetical
            results.sort(key=lambda x: (not x[1], x[0].lower()))

            if not results:
                target_desc = path or "working directory"
                if path == "/" or (path is None and pattern.startswith("/")):
                    target_desc = "all virtual roots"
                return f"No files matching '{pattern}' found in {target_desc}"

            # Format output
            result_lines = [f"Found {len(results)} matches for '{pattern}':"]
            for vpath, is_dir in results[:100]:  # Limit to 100 results
                marker = "[DIR] " if is_dir else ""
                result_lines.append(f"  {marker}{vpath}")

            if len(results) > 100:
                result_lines.append(f"  ... and {len(results) - 100} more")

            return "\n".join(result_lines)

        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error in glob {pattern}: {e}")
            return f"Error: {str(e)}"
