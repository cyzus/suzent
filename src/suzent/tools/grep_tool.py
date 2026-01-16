"""
GrepTool - Search file contents with regex.
"""

import re
from pathlib import Path
from typing import Optional, List, Tuple

from smolagents.tools import Tool

from suzent.logger import get_logger
from suzent.tools.path_resolver import PathResolver

logger = get_logger(__name__)


class GrepTool(Tool):
    """
    Search file contents with regex.
    """

    name = "GrepTool"
    description = """Search file contents with regex patterns.

Examples:
- GrepTool(pattern="def.*:", path="/persistence") - Find function definitions
- GrepTool(pattern="TODO", include="*.py") - Find TODOs in Python files
- GrepTool(pattern="error", case_insensitive=True, context_lines=2)
"""

    inputs = {
        "pattern": {"type": "string", "description": "Regex pattern to search for"},
        "path": {
            "type": "string",
            "description": "File or directory to search (default: working directory)",
            "nullable": True,
        },
        "include": {
            "type": "string",
            "description": "Filter files by glob pattern (e.g., *.py, *.{js,ts})",
            "nullable": True,
        },
        "case_insensitive": {
            "type": "boolean",
            "description": "Case insensitive search",
            "nullable": True,
        },
        "context_lines": {
            "type": "integer",
            "description": "Number of lines to show before and after each match",
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

    def forward(
        self,
        pattern: str,
        path: Optional[str] = None,
        include: Optional[str] = None,
        case_insensitive: Optional[bool] = None,
        context_lines: Optional[int] = None,
    ) -> str:
        """
        Search file contents.

        Args:
            pattern: Regex pattern
            path: File or directory to search
            include: Filter files by glob pattern
            case_insensitive: Case insensitive search
            context_lines: Lines of context around matches

        Returns:
            Matching lines with file info, or error message
        """
        if not self._resolver:
            return "Error: GrepTool not initialized. No resolver context."

        try:
            # Compile regex
            flags = re.IGNORECASE if case_insensitive else 0
            try:
                regex = re.compile(pattern, flags)
            except re.error as e:
                return f"Error: Invalid regex pattern: {e}"

            # Collect files to search
            files_to_search: List[Path] = []
            
            # Case A: Searching from Root (/) - Virtual Union Search
            if path == "/":
                roots = self._resolver.get_virtual_roots()
                glob_pattern = include or "**/*"
                
                for v_root, h_root in roots:
                    if not h_root.exists():
                        continue
                        
                    # Recursively find text files in this root
                    for f in h_root.glob(glob_pattern):
                        if f.is_file() and self._is_text_file(f):
                            if self._resolver.is_path_allowed(f):
                                files_to_search.append(f)
            
            # Case B: Standard Path Search
            else:
                # Resolve path
                if path:
                    search_path = self._resolver.resolve(path)
                else:
                    search_path = self._resolver.get_working_dir()

                if not search_path.exists():
                    return f"Error: Path not found: {path or 'working directory'}"

                if search_path.is_file():
                    files_to_search = [search_path]
                else:
                    # Use include pattern or search all text files
                    glob_pattern = include or "**/*"
                    for f in search_path.glob(glob_pattern):
                        if f.is_file() and self._is_text_file(f):
                            if self._resolver.is_path_allowed(f):
                                files_to_search.append(f)

            # Search files
            results: List[Tuple[str, int, str]] = []  # (file, line_num, content)
            files_with_matches = 0
            ctx = context_lines or 0

            for file_path in files_to_search[:100]:  # Limit files searched
                try:
                    matches = self._search_file(file_path, regex, ctx)
                    if matches:
                        files_with_matches += 1
                        vpath = (
                            self._resolver.to_virtual_path(file_path) or file_path.name
                        )
                        for line_num, content in matches:
                            results.append((vpath, line_num, content))
                except Exception as e:
                    logger.debug(f"Could not search {file_path}: {e}")

            if not results:
                return f"No matches for '{pattern}' in {path or 'working directory'}"

            # Format output
            output_lines = [
                f"Found {len(results)} match(es) in {files_with_matches} file(s):"
            ]

            current_file = None
            for vpath, line_num, content in results[:50]:  # Limit output
                if vpath != current_file:
                    output_lines.append(f"\n{vpath}:")
                    current_file = vpath
                output_lines.append(f"  {line_num}: {content.rstrip()}")

            if len(results) > 50:
                output_lines.append(f"\n... and {len(results) - 50} more matches")

            return "\n".join(output_lines)

        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error in grep: {e}")
            return f"Error: {str(e)}"

    def _is_text_file(self, path: Path) -> bool:
        """Check if file is likely a text file."""
        text_extensions = {
            ".txt",
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".json",
            ".yaml",
            ".yml",
            ".md",
            ".csv",
            ".html",
            ".css",
            ".scss",
            ".sql",
            ".sh",
            ".bash",
            ".toml",
            ".ini",
            ".cfg",
            ".conf",
            ".log",
            ".xml",
            ".env",
            ".go",
            ".rs",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".rb",
            ".php",
        }
        return path.suffix.lower() in text_extensions

    def _search_file(
        self, path: Path, regex: re.Pattern, context_lines: int
    ) -> List[Tuple[int, str]]:
        """Search a file and return matching lines."""
        matches = []

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception:
            return []

        for i, line in enumerate(lines):
            if regex.search(line):
                if context_lines > 0:
                    # Include context
                    start = max(0, i - context_lines)
                    end = min(len(lines), i + context_lines + 1)
                    for j in range(start, end):
                        prefix = ">" if j == i else " "
                        matches.append((j + 1, f"{prefix} {lines[j]}"))
                    matches.append((0, "---"))  # Separator
                else:
                    matches.append((i + 1, line))

        # Remove trailing separator
        if matches and matches[-1][0] == 0:
            matches.pop()

        return matches
