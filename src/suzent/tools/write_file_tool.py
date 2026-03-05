"""
WriteFileTool - Create or overwrite files.
"""

from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool

from suzent.logger import get_logger

logger = get_logger(__name__)


class WriteFileTool(Tool):
    """
    Create or overwrite a file with given content.
    """

    name = "WriteFileTool"
    tool_name = "write_file"
    requires_approval = True

    def forward(self, ctx: RunContext[AgentDeps], file_path: str, content: str) -> str:
        """Create or overwrite a file with the specified content.

        WARNING: This will completely overwrite existing files. For precise edits, use the
        edit_file tool instead.

        Args:
            ctx: The run context with agent dependencies.
            file_path: Path to the file to write.
            content: Content to write to the file.

        Returns:
            Success message or error.
        """
        deps = ctx.deps
        if deps.path_resolver:
            resolver = deps.path_resolver
        else:
            from suzent.tools.path_resolver import PathResolver
            from suzent.config import CONFIG

            resolver = PathResolver(
                deps.chat_id,
                deps.sandbox_enabled,
                sandbox_data_path=CONFIG.sandbox_data_path,
                custom_volumes=deps.custom_volumes,
                workspace_root=deps.workspace_root,
            )
            deps.path_resolver = resolver

        try:
            # Resolve the path
            resolved_path = resolver.resolve(file_path)

            # Create parent directories if needed
            resolved_path.parent.mkdir(parents=True, exist_ok=True)

            # Check if file exists (for logging)
            existed = resolved_path.exists()

            # Write the content
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(content)

            action = "Overwrote" if existed else "Created"
            size = len(content)
            logger.info(f"{action} file: {file_path} ({size} bytes)")

            return f"{action} file: {file_path} ({size} bytes written)"

        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error writing file {file_path}: {e}")
            return f"Error writing file: {str(e)}"
