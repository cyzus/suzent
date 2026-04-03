"""
GlobTool - Find files matching a pattern.
"""

from typing import Optional

from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool

from suzent.logger import get_logger
from suzent.tools.filesystem.path_resolver import PathResolver

logger = get_logger(__name__)


class GlobTool(Tool):
    """
    Find files matching a glob pattern.
    """

    name = "GlobTool"
    tool_name = "glob_search"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._resolver: Optional[PathResolver] = None

    def forward(
        self, ctx: RunContext[AgentDeps], pattern: str, path: Optional[str] = None
    ) -> str:
        """Find files matching a glob pattern.

        Searches for files matching the given glob pattern in the specified directory
        (or working directory if not specified). Supports patterns like *.py, **/*.py,
        data/*.csv, etc.

        Args:
            ctx: The run context with agent dependencies.
            pattern: Glob pattern to match (e.g., '**/*.py', '*.csv').
            path: Directory to search in (default: working directory).

        Returns:
            List of matching file paths, or a message if no matches found.
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
            # Use unified finder from resolver
            # pattern in GlobTool is the glob pattern itself
            # path is the starting directory

            # Merge path and pattern for unified root-relative search
            search_path = path
            search_pattern = pattern

            if search_path:
                # Normalize path
                search_path = search_path.replace("\\", "/").rstrip("/")
                if not search_path.startswith("/"):
                    search_path = "/" + search_path

                # Combine
                search_pattern = f"{search_path}/{search_pattern}"
                # Reset search_path to None (or "/" to trigger root search in find_files)
                search_path = None

            found_files = self._resolver.find_files(search_pattern, search_path)

            # Format results for GlobTool (needs host path for is_dir check)
            results = []
            for host_path, virtual_path in found_files:
                # Return host path in host mode, virtual path in sandbox mode
                display_path = (
                    str(host_path)
                    if not self._resolver.sandbox_enabled
                    else virtual_path
                )
                results.append((display_path, host_path.is_dir()))

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
