"""
ReadFileTool - Read files from the filesystem.

Supports reading text files directly and converting various file formats
(PDF, DOCX, XLSX, images, etc.) to markdown via MarkItDown.
"""

from pathlib import Path
from typing import Optional

from markitdown import MarkItDown
from smolagents.tools import Tool

from suzent.logger import get_logger
from suzent.tools.path_resolver import PathResolver

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
    description = """Read file content from the filesystem.

Supports various file formats:
- Text files: .txt, .py, .js, .json, .md, .csv, etc.
- Documents: .pdf, .docx, .xlsx, .pptx (converted to markdown)
- Images: .jpg, .png (OCR text extraction)

Use 'offset' and 'limit' for reading portions of large files.

Examples:
- ReadFileTool(file_path="/persistence/data.csv")
- ReadFileTool(file_path="report.pdf", offset=10, limit=50)
"""

    inputs = {
        "file_path": {"type": "string", "description": "Path to the file to read"},
        "offset": {
            "type": "integer",
            "description": "Line number to start from (0-indexed)",
            "nullable": True,
        },
        "limit": {
            "type": "integer",
            "description": "Number of lines to read (omit for all)",
            "nullable": True,
        },
    }
    output_type = "string"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._resolver: Optional[PathResolver] = None
        self._converter = MarkItDown()

    def set_context(self, resolver: PathResolver) -> None:
        """Set the path resolver context."""
        self._resolver = resolver

    def forward(
        self, file_path: str, offset: Optional[int] = None, limit: Optional[int] = None
    ) -> str:
        """
        Read file contents.

        Args:
            file_path: Path to the file
            offset: Starting line number (0-indexed)
            limit: Number of lines to read

        Returns:
            File content as string, or error message
        """
        if not self._resolver:
            return "Error: ReadFileTool not initialized. No resolver context."

        try:
            # Resolve the path
            resolved_path = self._resolver.resolve(file_path)

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
