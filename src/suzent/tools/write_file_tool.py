"""
WriteFileTool - Create or overwrite files.
"""

from typing import Optional

from smolagents.tools import Tool

from suzent.logger import get_logger
from suzent.tools.path_resolver import PathResolver

logger = get_logger(__name__)


class WriteFileTool(Tool):
    """
    Create or overwrite a file with given content.
    """

    name = "WriteFileTool"
    description = """Create or overwrite a file with the specified content.

WARNING: This will completely overwrite existing files. For precise edits, use EditFileTool.

Examples:
- WriteFileTool(file_path="/persistence/output.txt", content="Hello World")
- WriteFileTool(file_path="script.py", content="print('hello')")
"""

    inputs = {
        "file_path": {"type": "string", "description": "Path to the file to write"},
        "content": {"type": "string", "description": "Content to write to the file"},
    }
    output_type = "string"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._resolver: Optional[PathResolver] = None

    def set_context(self, resolver: PathResolver) -> None:
        """Set the path resolver context."""
        self._resolver = resolver

    def forward(self, file_path: str, content: str) -> str:
        """
        Write content to a file.

        Args:
            file_path: Path to the file
            content: Content to write

        Returns:
            Success message or error
        """
        if not self._resolver:
            return "Error: WriteFileTool not initialized. No resolver context."

        try:
            # Resolve the path
            resolved_path = self._resolver.resolve(file_path)

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
