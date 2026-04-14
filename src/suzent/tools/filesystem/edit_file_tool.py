"""
EditFileTool - Make precise string replacements in files.
"""

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


MAX_EDIT_FILE_SIZE = 50 * 1024 * 1024  # 50 MiB


_CURLY_QUOTE_MAP = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",  # left/right single curly quotes
        "\u201c": '"',
        "\u201d": '"',  # left/right double curly quotes
    }
)


def _normalize_quotes(s: str) -> str:
    return s.translate(_CURLY_QUOTE_MAP)


def _strip_trailing_whitespace(s: str) -> str:
    """Strip trailing whitespace from each line, preserving line endings."""
    import re

    return re.sub(r"[^\S\r\n]+(\r\n|\r|\n)", r"\1", s)


def _find_actual_string(content: str, search: str) -> str | None:
    """
    Locate `search` in `content` using a normalization cascade.

    Returns the verbatim slice from `content` that should be replaced,
    or None if no match is found.

    Normalization steps (each tried in order, stopping on first hit):
      1. Exact match
      2. Trailing-whitespace normalization on both sides
      3. CRLF → LF normalization on both sides
      4. Curly-quote normalization on both sides
      5. All of the above combined
    """
    # Step 1: exact
    if search in content:
        return search

    def _try(norm_content: str, norm_search: str) -> str | None:
        idx = norm_content.find(norm_search)
        if idx == -1:
            return None
        return content[idx : idx + len(norm_search)]

    stripped_content = _strip_trailing_whitespace(content)
    stripped_search = _strip_trailing_whitespace(search)

    # Step 2: trailing whitespace
    result = _try(stripped_content, stripped_search)
    if result is not None:
        return result

    lf_content = content.replace("\r\n", "\n")
    lf_search = search.replace("\r\n", "\n")

    # Step 3: CRLF → LF
    result = _try(lf_content, lf_search)
    if result is not None:
        return result

    # Step 4: curly quotes
    result = _try(_normalize_quotes(content), _normalize_quotes(search))
    if result is not None:
        return result

    # Step 5: all combined
    result = _try(
        _normalize_quotes(_strip_trailing_whitespace(lf_content)),
        _normalize_quotes(_strip_trailing_whitespace(lf_search)),
    )
    return result


def _normalize_newlines_for_file(new_string: str, content: str) -> str:
    """Preserve dominant file newline style when inserted text contains line breaks."""
    has_crlf = "\r\n" in content
    has_lone_lf = "\n" in content.replace("\r\n", "")

    if has_crlf and has_lone_lf:
        # Mixed endings already exist; avoid rewriting user-provided newlines.
        return new_string
    if has_crlf:
        return new_string.replace("\r\n", "\n").replace("\n", "\r\n")
    return new_string


class EditFileTool(Tool):
    """
    Make exact string replacements in files.
    """

    name = "EditFileTool"
    tool_name = "edit_file"
    group = ToolGroup.FILESYSTEM
    requires_approval = True

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        file_path: Annotated[str, Field(description="Path to the file to edit.")],
        old_string: Annotated[
            str, Field(description="Exact text to find and replace.")
        ],
        new_string: Annotated[str, Field(description="Replacement text.")],
        replace_all: Annotated[
            Optional[bool],
            Field(description="Replace all matches instead of the first match."),
        ] = None,
    ) -> ToolResult:
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
            ToolResult indicating success or failure with error code.
        """
        denied_reason = self.is_tool_denied(ctx.deps, self.tool_name)
        if denied_reason:
            self.audit_operation(
                self.tool_name,
                "edit",
                "denied",
                file_path=file_path,
                reason=denied_reason,
            )
            return ToolResult.error_result(
                ToolErrorCode.PERMISSION_DENIED, denied_reason
            )

        resolver = get_or_create_path_resolver(ctx.deps)

        replace_all = replace_all or False

        try:
            if old_string == new_string:
                self.audit_operation(
                    self.tool_name,
                    "edit",
                    "noop",
                    file_path=file_path,
                    reason="identical_strings",
                )
                return ToolResult.error_result(
                    ToolErrorCode.NO_OP_CHANGE,
                    "Cannot replace: old_string and new_string are identical",
                )

            if is_windows_unc_path(file_path):
                self.audit_operation(
                    self.tool_name,
                    "edit",
                    "rejected",
                    file_path=file_path,
                    reason="unc",
                )
                return ToolResult.error_result(
                    ToolErrorCode.UNC_PATH_NOT_SUPPORTED,
                    "UNC paths are not supported by edit_file",
                )

            # Resolve the path
            resolved_path = resolver.resolve(file_path)

            # Check if file exists
            if not resolved_path.exists():
                self.audit_operation(
                    self.tool_name,
                    "edit",
                    "rejected",
                    file_path=file_path,
                    reason="not_found",
                )
                return ToolResult.error_result(
                    ToolErrorCode.FILE_NOT_FOUND, f"File not found: {file_path}"
                )

            if not resolved_path.is_file():
                self.audit_operation(
                    self.tool_name,
                    "edit",
                    "rejected",
                    file_path=file_path,
                    reason="not_a_file",
                )
                return ToolResult.error_result(
                    ToolErrorCode.FILE_REQUIRED, f"Path is not a file: {file_path}"
                )

            file_stat = resolved_path.stat()
            if file_stat.st_size > MAX_EDIT_FILE_SIZE:
                self.audit_operation(
                    self.tool_name,
                    "edit",
                    "rejected",
                    file_path=file_path,
                    reason="too_large",
                )
                return ToolResult.error_result(
                    ToolErrorCode.FILE_TOO_LARGE,
                    f"File too large to edit ({file_stat.st_size} bytes). "
                    f"Max size is {MAX_EDIT_FILE_SIZE} bytes",
                )

            # Read current content
            try:
                raw = resolved_path.read_bytes()
                encoding = detect_text_encoding(raw)
                if is_binary_content(raw, encoding):
                    self.audit_operation(
                        self.tool_name,
                        "edit",
                        "rejected",
                        file_path=file_path,
                        reason="binary",
                    )
                    return ToolResult.error_result(
                        ToolErrorCode.BINARY_FILE, "Cannot edit binary files"
                    )
                content = raw.decode(encoding)
            except UnicodeDecodeError:
                self.audit_operation(
                    self.tool_name,
                    "edit",
                    "rejected",
                    file_path=file_path,
                    reason="decode_error",
                )
                return ToolResult.error_result(
                    ToolErrorCode.BINARY_FILE, "Cannot edit binary files"
                )

            # Locate old_string with normalization fallback
            actual_old_string = _find_actual_string(content, old_string)
            if actual_old_string is None:
                self.audit_operation(
                    self.tool_name,
                    "edit",
                    "rejected",
                    file_path=file_path,
                    reason="no_match",
                )
                return ToolResult.error_result(
                    ToolErrorCode.NO_MATCH,
                    f"String not found in file: {repr(old_string[:50])}...",
                )

            # Count occurrences of the resolved string
            count = content.count(actual_old_string)

            if count > 1 and not replace_all:
                self.audit_operation(
                    self.tool_name,
                    "edit",
                    "rejected",
                    file_path=file_path,
                    reason="ambiguous_match",
                    match_count=count,
                )
                return ToolResult.error_result(
                    ToolErrorCode.AMBIGUOUS_MATCH,
                    f"Found {count} matches in {file_path}. "
                    "Set replace_all=True or provide a more specific old_string",
                    metadata={"match_count": count},
                )

            normalized_new_string = _normalize_newlines_for_file(new_string, content)

            # Perform replacement using the resolved actual string
            if replace_all:
                new_content = content.replace(actual_old_string, normalized_new_string)
                replaced = count
            else:
                new_content = content.replace(
                    actual_old_string, normalized_new_string, 1
                )
                replaced = 1

            # Abort if file changed during read/compute window.
            latest_mtime_ns = resolved_path.stat().st_mtime_ns
            if latest_mtime_ns != file_stat.st_mtime_ns:
                self.audit_operation(
                    self.tool_name,
                    "edit",
                    "rejected",
                    file_path=file_path,
                    reason="stale_write",
                )
                return ToolResult.error_result(
                    ToolErrorCode.STALE_WRITE,
                    "File changed while editing. Read the file again and retry "
                    "to avoid overwriting newer content",
                )

            # Write back
            with open(resolved_path, "w", encoding=encoding, newline="") as handle:
                handle.write(new_content)

            logger.info(f"Edited {file_path}: {replaced} replacement(s)")
            self.audit_operation(
                self.tool_name,
                "edit",
                "success",
                file_path=file_path,
                replaced_count=replaced,
            )
            return ToolResult.success_result(
                f"Replaced {replaced} occurrence(s) in {file_path}",
                metadata={"replaced_count": replaced, "file_path": file_path},
            )

        except ValueError as e:
            self.audit_operation(
                self.tool_name, "edit", "invalid_argument", file_path=file_path
            )
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT, f"Invalid argument: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Error editing file {file_path}: {e}")
            self.audit_operation(
                self.tool_name, "edit", "error", file_path=file_path, error=str(e)
            )
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED, f"Error editing file: {str(e)}"
            )
