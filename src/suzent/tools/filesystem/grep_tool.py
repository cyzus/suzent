"""
GrepTool - Search file contents with regex.
"""

import re
from pathlib import Path
from typing import Annotated, Optional, List, Tuple

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult

from suzent.logger import get_logger
from suzent.tools.filesystem.path_resolver import PathResolver

logger = get_logger(__name__)


class GrepTool(Tool):
    """
    Search file contents with regex.
    """

    name = "GrepTool"
    tool_name = "grep_search"
    group = ToolGroup.FILESYSTEM

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._resolver: Optional[PathResolver] = None

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        pattern: Annotated[
            str,
            Field(
                description="Regex pattern to search for. This must be valid regular expression syntax."
            ),
        ],
        path: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Optional file or directory search root. Leave empty to search the current workspace root.",
            ),
        ] = None,
        include: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Optional glob filter for files to include, such as '*.py' or '*.{js,ts}'.",
            ),
        ] = None,
        case_insensitive: Annotated[
            Optional[bool],
            Field(
                default=None,
                description="Set to true for case-insensitive regex matching.",
            ),
        ] = None,
        context_lines: Annotated[
            Optional[int],
            Field(
                default=None,
                ge=0,
                description="Number of surrounding lines to include around each match.",
            ),
        ] = None,
    ) -> ToolResult:
        """Search file contents using a regex pattern.

        Searches through files for lines matching the given regular expression. Supports
        filtering by file type, case-insensitive matching, and showing context lines around
        matches.

        Args:
            ctx: The run context with agent dependencies.
            pattern: Regex pattern to search for.
            path: File or directory to search in (default: working directory).
            include: Filter files by glob pattern (e.g., '*.py', '*.{js,ts}').
            case_insensitive: If True, perform case-insensitive search.
            context_lines: Number of lines to show before and after each match.

        Returns:
            Matching lines grouped by file, or a message if no matches found.
        """
        deps = ctx.deps
        if deps.path_resolver:
            self._resolver = deps.path_resolver
        else:
            from suzent.tools.filesystem.path_resolver import PathResolver
            from suzent.config import CONFIG

            self._resolver = PathResolver(
                deps.chat_id,
                deps.sandbox_enabled,
                sandbox_data_path=CONFIG.sandbox_data_path,
                custom_volumes=deps.custom_volumes,
                workspace_root=deps.workspace_root,
            )
            deps.path_resolver = self._resolver

        try:
            # Compile regex
            flags = re.IGNORECASE if case_insensitive else 0
            try:
                regex = re.compile(pattern, flags)
            except re.error as e:
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT,
                    f"Invalid regex pattern: {e}",
                    metadata={"pattern": pattern, "path": path, "include": include},
                )

            # Collect files to search
            glob_pattern = include or "**/*"

            # Use unified finder
            found_files = self._resolver.find_files(glob_pattern, path)

            # Search files
            results: List[Tuple[str, int, str]] = []  # (file, line_num, content)
            files_with_matches = 0
            ctx_lines = context_lines or 0

            for file_path, v_path in found_files:
                if len(results) >= 1000:  # Global safety limit
                    break

                if not file_path.is_file() or not self._is_text_file(file_path):
                    continue

                try:
                    matches = self._search_file(file_path, regex, ctx_lines)
                    if matches:
                        files_with_matches += 1
                        # Return host path in host mode, virtual path in sandbox mode
                        display_path = (
                            str(file_path)
                            if not self._resolver.sandbox_enabled
                            else v_path
                        )
                        for line_num, content in matches:
                            results.append((display_path, line_num, content))
                except Exception as e:
                    logger.debug(f"Could not search {file_path}: {e}")

            if not results:
                return ToolResult.success_result(
                    f"No matches for '{pattern}' in {path or 'working directory'}",
                    metadata={
                        "match_count": 0,
                        "file_count": 0,
                        "pattern": pattern,
                        "path": path,
                        "include": include,
                        "context_lines": ctx_lines,
                    },
                )

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

            return ToolResult.success_result(
                "\n".join(output_lines),
                metadata={
                    "match_count": len(results),
                    "file_count": files_with_matches,
                    "pattern": pattern,
                    "path": path,
                    "include": include,
                    "context_lines": ctx_lines,
                },
            )

        except ValueError as e:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                str(e),
                metadata={"pattern": pattern, "path": path, "include": include},
            )
        except Exception as e:
            logger.error(f"Error in grep: {e}")
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                str(e),
                metadata={"pattern": pattern, "path": path, "include": include},
            )

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
