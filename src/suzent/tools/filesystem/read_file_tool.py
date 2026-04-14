"""
ReadFileTool - Read files from the filesystem.

Supports reading text files directly and converting various file formats
(PDF, DOCX, XLSX, images, etc.) to markdown via MarkItDown.
"""

from pathlib import Path
from typing import Annotated, Optional

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult
from suzent.tools.filesystem.file_tool_utils import (
    detect_text_encoding,
    get_or_create_path_resolver,
    is_binary_content,
    is_windows_unc_path,
)
from suzent.logger import get_logger

logger = get_logger(__name__)


MAX_READ_FILE_SIZE = 50 * 1024 * 1024  # 50 MiB


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
    group = ToolGroup.FILESYSTEM
    session_guidance = (
        "Always use read_file to read files. Never use bash cat/head/tail/sed for this."
    )
    guidance_priority = 20

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._converter = None

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        file_path: Annotated[str, Field(description="Path to the file to read.")],
        offset: Annotated[
            Optional[int],
            Field(
                description=(
                    "1-based line number to start reading from. "
                    "Provide with `limit` to read a specific line range, "
                    "or alone when the file is too large to read at once."
                ),
                ge=1,
            ),
        ] = None,
        limit: Annotated[
            Optional[int],
            Field(
                description=(
                    "Maximum number of lines to read. "
                    "Omit to read the whole file (up to 2000 lines by default)."
                ),
                ge=1,
            ),
        ] = None,
    ) -> ToolResult:
        """Read a file from the filesystem. You can access any file directly with this tool.
        Assume this tool is able to read all files. If the user provides a path, assume it is valid.

        Reads up to 2000 lines by default. Results include line numbers (cat -n format).
        For large files use offset+limit to read in chunks.
        Supports text files, documents (PDF, DOCX, XLSX → markdown), and images.
        This tool reads files only; to list a directory use bash.

        Args:
            ctx: The run context with agent dependencies.
            file_path: Path to the file to read.
            offset: 1-based line number to start from.
            limit: Number of lines to read.

        Returns:
            ToolResult with file content (with line numbers) or error.
        """
        resolver = get_or_create_path_resolver(ctx.deps)

        try:
            if is_windows_unc_path(file_path):
                return ToolResult.error_result(
                    ToolErrorCode.UNC_PATH_NOT_SUPPORTED,
                    "UNC paths are not supported by read_file",
                )

            # Resolve the path
            resolved_path = resolver.resolve(file_path)

            # Check if file exists
            if not resolved_path.exists():
                return ToolResult.error_result(
                    ToolErrorCode.FILE_NOT_FOUND, f"File not found: {file_path}"
                )

            if not resolved_path.is_file():
                return ToolResult.error_result(
                    ToolErrorCode.FILE_REQUIRED, f"Path is not a file: {file_path}"
                )

            file_stat = resolved_path.stat()
            if file_stat.st_size > MAX_READ_FILE_SIZE:
                return ToolResult.error_result(
                    ToolErrorCode.FILE_TOO_LARGE,
                    f"File too large to read ({file_stat.st_size} bytes). "
                    f"Max size is {MAX_READ_FILE_SIZE} bytes",
                )

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
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT, f"Invalid argument: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED, f"Error reading file: {str(e)}"
            )

    def _read_text_file(
        self, path: Path, offset: Optional[int], limit: Optional[int]
    ) -> ToolResult:
        """Read a text file with offset/limit support."""
        try:
            raw = path.read_bytes()
            encoding = detect_text_encoding(raw)
            if is_binary_content(raw, encoding):
                return ToolResult.error_result(
                    ToolErrorCode.BINARY_FILE,
                    "File appears to be binary, cannot read as text",
                )

            try:
                content = raw.decode(encoding)
            except UnicodeDecodeError:
                return ToolResult.error_result(
                    ToolErrorCode.BINARY_FILE,
                    "File appears to be binary, cannot read as text",
                )

            lines = content.splitlines(keepends=True)

            total_lines = len(lines)

            # offset is 1-based; default to line 1
            start = max((offset or 1) - 1, 0)
            if start >= total_lines:
                return ToolResult.success_result(
                    f"(File has {total_lines} lines, offset {offset} is beyond end)",
                    metadata={"total_lines": total_lines},
                )

            # Apply limit; default to 2000 lines
            effective_limit = limit if limit is not None else 2000
            end = min(start + effective_limit, total_lines)

            selected_lines = lines[start:end]

            # Format with line numbers (cat -n style, 1-based)
            numbered = "".join(
                f"{start + i + 1}\t{line}" for i, line in enumerate(selected_lines)
            )

            truncated = end < total_lines
            header = f"[Lines {start + 1}-{end} of {total_lines}]"
            if truncated:
                header += f" — use offset={end + 1} to read more"
            header += "\n"

            return ToolResult.success_result(
                header + numbered,
                metadata={
                    "total_lines": total_lines,
                    "start_line": start + 1,
                    "end_line": end,
                    "truncated": truncated,
                },
            )

        except UnicodeDecodeError:
            return ToolResult.error_result(
                ToolErrorCode.BINARY_FILE,
                "File appears to be binary, cannot read as text",
            )

    def _convert_file(
        self, path: Path, offset: Optional[int], limit: Optional[int]
    ) -> ToolResult:
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
                return ToolResult.success_result(
                    f"Warning: File converted but appears empty: {path.name}"
                )

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
            return ToolResult.success_result(
                content,
                metadata={"format": path.suffix, "content_length": len(content)},
            )

        except Exception as e:
            logger.error(f"Error converting file {path}: {e}")
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED, f"Error converting file: {str(e)}"
            )
