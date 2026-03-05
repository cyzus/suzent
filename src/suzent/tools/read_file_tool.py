"""
ReadFileTool - Read files from the filesystem.

Supports reading text files directly and converting various file formats
(PDF, DOCX, XLSX, images, etc.) to markdown via MarkItDown.
"""

from pathlib import Path
from typing import Optional

from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool
from suzent.logger import get_logger

logger = get_logger(__name__)


class ReadFileTool(Tool):
    """
    Read file content from the filesystem.

    Supports:
    - Text files (txt, py, js, etc.)
    - Documents (PDF, DOCX, XLSX, PPTX)
    - Images (with text extraction)
    - HTML and other formats via MarkItDown
    """

    name = "ReadFileTool"
    tool_name = "read_file"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._converter = None

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        file_path: str,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> str:
        """Read file content from the filesystem.

        Supports various file formats including text files (.txt, .py, .js, .json, .md, .csv, etc.),
        documents (.pdf, .docx, .xlsx, .pptx converted to markdown), and images (.jpg, .png with
        OCR text extraction). Use 'offset' and 'limit' for reading portions of large files.

        Args:
            ctx: The run context with agent dependencies.
            file_path: Path to the file to read.
            offset: Line number to start from (0-indexed).
            limit: Number of lines to read (omit for all).

        Returns:
            File content as string, or error message.
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

            # Check if file exists
            if not resolved_path.exists():
                return f"Error: File not found: {file_path}"

            if not resolved_path.is_file():
                return f"Error: Path is not a file: {file_path}"

            # Get file extension
            ext = resolved_path.suffix.lower()

            # For text files, read directly with offset/limit support
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
            }

            if ext in text_extensions:
                return self._read_text_file(resolved_path, offset, limit)
            else:
                # Use MarkItDown for other formats
                return self._convert_file(resolved_path, offset, limit)

        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return f"Error reading file: {str(e)}"

    def _read_text_file(
        self, path: Path, offset: Optional[int], limit: Optional[int]
    ) -> str:
        """Read a text file with offset/limit support."""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)

            # Apply offset
            start = offset or 0
            if start < 0:
                start = 0
            if start >= total_lines:
                return f"(File has {total_lines} lines, offset {start} is beyond end)"

            # Apply limit
            if limit is not None and limit > 0:
                end = min(start + limit, total_lines)
            else:
                end = total_lines

            selected_lines = lines[start:end]
            content = "".join(selected_lines)

            # Add info header if using offset/limit
            if offset is not None or limit is not None:
                header = f"[Lines {start + 1}-{end} of {total_lines}]\n"
                return header + content

            return content

        except UnicodeDecodeError:
            return "Error: File appears to be binary, cannot read as text"

    def _convert_file(
        self, path: Path, offset: Optional[int], limit: Optional[int]
    ) -> str:
        """Convert file to markdown using MarkItDown."""
        try:
            if self._converter is None:
                from markitdown import MarkItDown

                logger.info("Initializing MarkItDown converter (lazy load)...")
                self._converter = MarkItDown()

            logger.info(f"Converting file to markdown: {path}")
            result = self._converter.convert(str(path))

            # Get content from result
            if hasattr(result, "text_content"):
                content = result.text_content
            else:
                content = str(result)

            if not content or not content.strip():
                return f"Warning: File converted but appears empty: {path.name}"

            # Apply offset/limit to converted content
            if offset is not None or limit is not None:
                lines = content.split("\n")
                start = offset or 0
                if limit:
                    lines = lines[start : start + limit]
                else:
                    lines = lines[start:]
                content = "\n".join(lines)

            logger.info(f"Successfully converted: {path.name} ({len(content)} chars)")
            return content

        except Exception as e:
            logger.error(f"Error converting file {path}: {e}")
            return f"Error converting file: {str(e)}"
