"""
ReadFileTool - Read files from the filesystem.

Supports reading text files directly and converting documents (PDF, DOCX,
PPTX, XLSX, ...) to markdown via :mod:`suzent.tools.filesystem.doc_convert`.
"""

from pathlib import Path
from typing import Annotated, Optional, TypedDict

from pydantic import ConfigDict, Field, with_config
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult
from suzent.tools.filesystem import doc_convert
from suzent.tools.filesystem.file_tool_utils import (
    detect_text_encoding,
    get_or_create_path_resolver,
    is_binary_content,
    is_windows_unc_path,
)
from suzent.logger import get_logger

logger = get_logger(__name__)


MAX_READ_FILE_SIZE = 50 * 1024 * 1024  # 50 MiB


@with_config(ConfigDict(extra="allow", use_attribute_docstrings=True))
class ReadFileMetadata(TypedDict, total=False):
    total_lines: int
    start_line: int
    end_line: int
    truncated: bool
    """True when lines after end_line were not returned; read on with offset=end_line + 1."""
    format: str
    """The extension of a converted document, such as '.pdf'."""
    content_length: int
    abs_path: str
    """The resolved file, so the chat UI can open it in the file preview."""


class ReadFileResult(ToolResult):
    metadata: ReadFileMetadata = Field(default_factory=dict)


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
    model_excluded_metadata = frozenset({"abs_path"})
    group = ToolGroup.FILESYSTEM
    builtin = True
    session_guidance = (
        "Always use read_file to read files. Never use bash cat/head/tail/sed for this."
    )
    guidance_priority = 20

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
    ) -> ReadFileResult:
        """Read a file from the filesystem. You can access any file directly with this tool.
        Assume this tool is able to read all files. If the user provides a path, assume it is valid.

        Reads up to 2000 lines by default. Results include line numbers (cat -n format).
        For large files use offset+limit to read in chunks.
        Supports text files and documents (PDF, DOCX, PPTX, XLSX → markdown).
        This tool reads files only; to list a directory use glob_search.

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
                return ReadFileResult.error_result(
                    ToolErrorCode.UNC_PATH_NOT_SUPPORTED,
                    "UNC paths are not supported by read_file",
                )

            # Resolve the path
            resolved_path = resolver.resolve(file_path)

            # Check if file exists
            if not resolved_path.exists():
                return ReadFileResult.error_result(
                    ToolErrorCode.FILE_NOT_FOUND, f"File not found: {file_path}"
                )

            if not resolved_path.is_file():
                return ReadFileResult.error_result(
                    ToolErrorCode.FILE_REQUIRED, f"Path is not a file: {file_path}"
                )

            file_stat = resolved_path.stat()
            if file_stat.st_size > MAX_READ_FILE_SIZE:
                return ReadFileResult.error_result(
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

            if ext in doc_convert.CONVERTERS and ext not in text_extensions:
                result = self._convert_file(resolved_path, offset, limit)
            else:
                # Anything else (source code in other languages, dotfiles, ...)
                # is read as text when it is text; binary files get a clear error.
                result = self._read_text_file(resolved_path, offset, limit)
            if result.success:
                result.metadata["abs_path"] = str(resolved_path)
            return result

        except ValueError as e:
            return ReadFileResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT, f"Invalid argument: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return ReadFileResult.error_result(
                ToolErrorCode.EXECUTION_FAILED, f"Error reading file: {str(e)}"
            )

    def _read_text_file(
        self, path: Path, offset: Optional[int], limit: Optional[int]
    ) -> ReadFileResult:
        """Read a text file with offset/limit support."""
        try:
            raw = path.read_bytes()
            encoding = detect_text_encoding(raw)
            if is_binary_content(raw, encoding):
                return self._binary_error(path)

            try:
                content = raw.decode(encoding)
            except UnicodeDecodeError:
                return self._binary_error(path)

            return self._paginate(content, offset, limit)

        except UnicodeDecodeError:
            return self._binary_error(path)

    @staticmethod
    def _binary_error(path: Path) -> ReadFileResult:
        supported = ", ".join(sorted(doc_convert.CONVERTERS))
        return ReadFileResult.error_result(
            ToolErrorCode.BINARY_FILE,
            f"File appears to be binary, cannot read as text: {path.name}. "
            f"Documents read_file converts: {supported}. "
            "For images, use an image or vision tool.",
        )

    @staticmethod
    def _paginate(
        content: str,
        offset: Optional[int],
        limit: Optional[int],
        extra_metadata: Optional[dict] = None,
    ) -> ReadFileResult:
        """Return ``content`` as numbered lines (cat -n style, 1-based)."""
        lines = content.splitlines(keepends=True)
        total_lines = len(lines)

        # offset is 1-based; default to line 1
        start = max((offset or 1) - 1, 0)
        if start >= total_lines:
            return ReadFileResult.success_result(
                f"(File has {total_lines} lines, offset {offset} is beyond end)",
                metadata={"total_lines": total_lines, **(extra_metadata or {})},
            )

        # Apply limit; default to 2000 lines
        effective_limit = limit if limit is not None else 2000
        end = min(start + effective_limit, total_lines)

        numbered = "".join(
            f"{start + i + 1}\t{line}" for i, line in enumerate(lines[start:end])
        )

        truncated = end < total_lines
        header = f"[Lines {start + 1}-{end} of {total_lines}]"
        if truncated:
            header += f" — use offset={end + 1} to read more"
        header += "\n"

        return ReadFileResult.success_result(
            header + numbered,
            metadata={
                "total_lines": total_lines,
                "start_line": start + 1,
                "end_line": end,
                "truncated": truncated,
                **(extra_metadata or {}),
            },
        )

    def _convert_file(
        self, path: Path, offset: Optional[int], limit: Optional[int]
    ) -> ReadFileResult:
        """Convert a document (PDF, DOCX, XLSX, ...) to markdown, then paginate."""
        try:
            logger.info(f"Converting file to markdown: {path}")
            content = doc_convert.convert(path)
        except ImportError as e:
            return ReadFileResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"Cannot convert {path.suffix} files: missing library ({e.name}).",
            )
        except Exception as e:
            logger.error(f"Error converting file {path}: {e}")
            return ReadFileResult.error_result(
                ToolErrorCode.EXECUTION_FAILED, f"Error converting file: {str(e)}"
            )

        if not content or not content.strip():
            return ReadFileResult.success_result(
                f"Warning: File converted but appears empty: {path.name}",
                metadata={"format": path.suffix, "content_length": 0},
            )

        logger.info(f"Converted {path.name} ({len(content)} chars)")
        return self._paginate(
            content,
            offset,
            limit,
            extra_metadata={"format": path.suffix, "content_length": len(content)},
        )
