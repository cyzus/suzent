"""
WriteFileTool - Create or overwrite files.
"""

from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool, ToolErrorCode, ToolResult
from suzent.tools.filesystem.file_tool_utils import (
    detect_text_encoding,
    get_or_create_path_resolver,
    is_binary_content,
    is_windows_unc_path,
)

from suzent.logger import get_logger

logger = get_logger(__name__)


MAX_WRITE_FILE_SIZE = 50 * 1024 * 1024  # 50 MiB


class WriteFileTool(Tool):
    """
    Create or overwrite a file with given content.
    """

    name = "WriteFileTool"
    tool_name = "write_file"
    requires_approval = True

    def forward(
        self, ctx: RunContext[AgentDeps], file_path: str, content: str
    ) -> ToolResult:
        """Create or overwrite a file with the specified content.

        WARNING: This will completely overwrite existing files. For precise edits, use the
        edit_file tool instead.

        Args:
            ctx: The run context with agent dependencies.
            file_path: Path to the file to write.
            content: Content to write to the file.

        Returns:
            ToolResult indicating success or failure.
        """
        denied_reason = self.is_tool_denied(ctx.deps, self.tool_name)
        if denied_reason:
            self.audit_operation(
                self.tool_name,
                "write",
                "denied",
                file_path=file_path,
                reason=denied_reason,
            )
            return ToolResult.error_result(
                ToolErrorCode.PERMISSION_DENIED, denied_reason
            )

        resolver = get_or_create_path_resolver(ctx.deps)

        try:
            if is_windows_unc_path(file_path):
                self.audit_operation(
                    self.tool_name,
                    "write",
                    "rejected",
                    file_path=file_path,
                    reason="unc",
                )
                return ToolResult.error_result(
                    ToolErrorCode.UNC_PATH_NOT_SUPPORTED,
                    "UNC paths are not supported by write_file",
                )

            # Resolve the path
            resolved_path = resolver.resolve(file_path)

            existed = resolved_path.exists()
            encoding = "utf-8"

            if existed:
                if not resolved_path.is_file():
                    self.audit_operation(
                        self.tool_name,
                        "write",
                        "rejected",
                        file_path=file_path,
                        reason="not_a_file",
                    )
                    return ToolResult.error_result(
                        ToolErrorCode.FILE_REQUIRED, f"Path is not a file: {file_path}"
                    )

                file_stat = resolved_path.stat()
                if file_stat.st_size > MAX_WRITE_FILE_SIZE:
                    self.audit_operation(
                        self.tool_name,
                        "write",
                        "rejected",
                        file_path=file_path,
                        reason="too_large",
                    )
                    return ToolResult.error_result(
                        ToolErrorCode.FILE_TOO_LARGE,
                        f"File too large to overwrite ({file_stat.st_size} bytes). "
                        f"Max size is {MAX_WRITE_FILE_SIZE} bytes",
                    )

                raw = resolved_path.read_bytes()
                encoding = detect_text_encoding(raw)

                if is_binary_content(raw, encoding):
                    self.audit_operation(
                        self.tool_name,
                        "write",
                        "rejected",
                        file_path=file_path,
                        reason="binary",
                    )
                    return ToolResult.error_result(
                        ToolErrorCode.BINARY_FILE,
                        "Refusing to overwrite binary file with write_file",
                    )

                try:
                    old_content = raw.decode(encoding)
                except UnicodeDecodeError:
                    self.audit_operation(
                        self.tool_name,
                        "write",
                        "rejected",
                        file_path=file_path,
                        reason="decode_error",
                    )
                    return ToolResult.error_result(
                        ToolErrorCode.BINARY_FILE,
                        "Refusing to overwrite non-text file with write_file",
                    )

                if old_content == content:
                    self.audit_operation(
                        self.tool_name,
                        "write",
                        "noop",
                        file_path=file_path,
                        bytes_written=0,
                    )
                    return ToolResult.success_result(
                        f"No changes: {file_path} already has the requested content"
                    )

            # Create parent directories if needed
            resolved_path.parent.mkdir(parents=True, exist_ok=True)

            # Write the content
            with open(resolved_path, "w", encoding=encoding, newline="") as f:
                f.write(content)

            action = "Overwrote" if existed else "Created"
            size = len(content.encode(encoding, errors="replace"))
            logger.info(f"{action} file: {file_path} ({size} bytes)")
            self.audit_operation(
                self.tool_name,
                "write",
                "success",
                file_path=file_path,
                action=action.lower(),
                bytes_written=size,
            )

            return ToolResult.success_result(
                f"{action} file: {file_path} ({size} bytes written)",
                metadata={
                    "action": "overwrite" if existed else "create",
                    "bytes_written": size,
                },
            )

        except ValueError as e:
            self.audit_operation(
                self.tool_name, "write", "invalid_argument", file_path=file_path
            )
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT, f"Invalid argument: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Error writing file {file_path}: {e}")
            self.audit_operation(
                self.tool_name, "write", "error", file_path=file_path, error=str(e)
            )
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED, f"Error writing file: {str(e)}"
            )
