"""
EditFileTool - Make precise string replacements in files.
"""

from typing import Optional

from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool

from suzent.logger import get_logger

logger = get_logger(__name__)


class EditFileTool(Tool):
    """
    Make exact string replacements in files.
    """

    name = "EditFileTool"
    tool_name = "edit_file"
    requires_approval = True

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: Optional[bool] = None,
    ) -> str:
        """Make exact string replacements in a file.

        Use this for precise edits. The old_string must match exactly (including whitespace
        and indentation). For complete file rewrites, use the write_file tool instead.

        Args:
            ctx: The run context with agent dependencies.
            file_path: Path to the file to edit.
            old_string: Exact text to find and replace (must match exactly).
            new_string: Replacement text.
            replace_all: If True, replace all occurrences. Default is False (replaces first only).

        Returns:
            Success message with replacement count, or error.
        """
        deps = ctx.deps
        if deps.path_resolver:
            resolver = deps.path_resolver
        else:
            from suzent.tools.path_resolver import PathResolver
            from suzent.config import CONFIG
            resolver = PathResolver(
                deps.chat_id, deps.sandbox_enabled,
                sandbox_data_path=CONFIG.sandbox_data_path,
                custom_volumes=deps.custom_volumes,
                workspace_root=deps.workspace_root,
            )
            deps.path_resolver = resolver

        replace_all = replace_all or False

        try:
            # Resolve the path
            resolved_path = resolver.resolve(file_path)

            # Check if file exists
            if not resolved_path.exists():
                return f"Error: File not found: {file_path}"

            if not resolved_path.is_file():
                return f"Error: Path is not a file: {file_path}"

            # Read current content
            try:
                content = resolved_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return "Error: Cannot edit binary files"

            # Check if old_string exists
            if old_string not in content:
                return f"Error: String not found in file: {repr(old_string[:50])}..."

            # Count occurrences
            count = content.count(old_string)

            # Perform replacement
            if replace_all:
                new_content = content.replace(old_string, new_string)
                replaced = count
            else:
                new_content = content.replace(old_string, new_string, 1)
                replaced = 1

            # Write back
            resolved_path.write_text(new_content, encoding="utf-8")

            logger.info(f"Edited {file_path}: {replaced} replacement(s)")

            if count > 1 and not replace_all:
                return f"Replaced 1 of {count} occurrences in {file_path}. Use replace_all=True for all."
            else:
                return f"Replaced {replaced} occurrence(s) in {file_path}"

        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error editing file {file_path}: {e}")
            return f"Error editing file: {str(e)}"
