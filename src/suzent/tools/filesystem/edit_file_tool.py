"""
EditFileTool - Make precise string replacements in files.
"""

import re
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


# Matches the line-number prefix that read_file prepends to every line:
#   "<digits><tab>" at the very start of a line.
# Models sometimes copy this prefix verbatim into old_string / new_string,
# which breaks exact matching and corrupts indentation.
_LINE_NUMBER_PREFIX_RE = re.compile(r"^[ \t]*\d+\t", re.MULTILINE)


def _strip_line_number_prefixes(s: str) -> str:
    """Remove read_file line-number prefixes (e.g. '42\\t') from every line."""
    return _LINE_NUMBER_PREFIX_RE.sub("", s)


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
    return re.sub(r"[^\S\r\n]+(\r\n|\r|\n)", r"\1", s)


def _build_norm_index_map(original: str, normalized: str) -> list[int]:
    """
    Build a mapping from each character position in `normalized` back to the
    corresponding character position in `original`.

    Works for any normalization that only deletes characters (never inserts),
    which covers trailing-whitespace stripping and CRLF→LF conversion.

    Returns a list `m` such that `m[i]` is the index in `original` that
    produced `normalized[i]`.
    """
    mapping: list[int] = []
    ni = 0  # cursor in normalized
    for oi, ch in enumerate(original):
        if ni < len(normalized) and normalized[ni] == ch:
            mapping.append(oi)
            ni += 1
    return mapping


def _find_via_norm(
    content: str,
    search: str,
    norm_content: str,
    norm_search: str,
    index_map: list[int],
) -> str | None:
    """
    Find `norm_search` inside `norm_content`, then use `index_map` to recover
    the verbatim span from `content`.  Returns the original slice, or None.

    Safe only when `norm_content` was produced by purely-deleting `content`
    (i.e. `index_map` has exactly `len(norm_content)` entries).
    """
    idx = norm_content.find(norm_search)
    if idx == -1:
        return None
    end_idx = idx + len(norm_search)
    if end_idx > len(index_map):
        return None
    orig_start = index_map[idx]
    # end is the original position *after* the last matched char
    # index_map[end_idx - 1] is the last matched char; the char after it in
    # original is at index_map[end_idx - 1] + 1 ... unless the match ends at
    # the very last normalized char, in which case we scan forward.
    orig_end = index_map[end_idx - 1] + 1
    return content[orig_start:orig_end]


def _find_actual_string(content: str, search: str) -> str | None:
    """
    Locate `search` in `content` using a normalization cascade.

    Returns the verbatim slice from `content` that should be replaced,
    or None if no match is found.

    Normalization steps (each tried in order, stopping on first hit):
      1. Exact match
      2. Trailing-whitespace normalization on both sides
      3. CRLF -> LF normalization on both sides
      4. Curly-quote normalization on both sides (length-preserving, safe)
      5. All of the above combined

    Steps 2, 3, 5 use an index map to recover the original span after
    searching in the shorter normalized string, avoiding the off-by-N bug
    that arises from using normalized offsets directly on the original.
    """
    # Step 1: exact
    if search in content:
        return search

    # Step 2: trailing whitespace (deletes chars → need index map)
    stripped_content = _strip_trailing_whitespace(content)
    stripped_search = _strip_trailing_whitespace(search)
    if stripped_search in stripped_content:
        index_map = _build_norm_index_map(content, stripped_content)
        result = _find_via_norm(
            content, search, stripped_content, stripped_search, index_map
        )
        if result is not None:
            return result

    # Step 3: CRLF -> LF (deletes chars → need index map)
    lf_content = content.replace("\r\n", "\n")
    lf_search = search.replace("\r\n", "\n")
    if lf_search in lf_content:
        index_map = _build_norm_index_map(content, lf_content)
        result = _find_via_norm(content, search, lf_content, lf_search, index_map)
        if result is not None:
            return result

    # Step 4: curly quotes only (length-preserving: each quote char → same-width
    # ASCII char, so normalized idx == original idx; direct slice is safe)
    norm_content4 = _normalize_quotes(content)
    norm_search4 = _normalize_quotes(search)
    idx4 = norm_content4.find(norm_search4)
    if idx4 != -1:
        return content[idx4 : idx4 + len(norm_search4)]

    # Step 5: all combined (trailing-ws + CRLF + quotes; use index map for
    # the length-changing parts, apply quote norm on top)
    lf_stripped_content = _strip_trailing_whitespace(lf_content)
    lf_stripped_search = _strip_trailing_whitespace(lf_search)
    norm_content5 = _normalize_quotes(lf_stripped_content)
    norm_search5 = _normalize_quotes(lf_stripped_search)
    if norm_search5 in norm_content5:
        # index_map5: lf_content → lf_stripped_content (deletion only)
        # lf_map:     content   → lf_content             (deletion only)
        # quote normalization is length-preserving, so idx in norm_content5
        # equals idx in lf_stripped_content.
        index_map5 = _build_norm_index_map(lf_content, lf_stripped_content)
        lf_map = _build_norm_index_map(content, lf_content)
        idx5 = norm_content5.find(norm_search5)
        end5 = idx5 + len(norm_search5)
        if end5 <= len(index_map5) and end5 > 0:
            orig_start_lf = index_map5[idx5]
            # index_map5[end5-1] is the lf_content position of the last matched
            # char; +1 gives the exclusive end in lf_content.
            last_lf_pos = index_map5[end5 - 1]
            orig_end_lf = last_lf_pos + 1
            if orig_start_lf < len(lf_map) and orig_end_lf - 1 < len(lf_map):
                orig_start = lf_map[orig_start_lf]
                orig_end = lf_map[orig_end_lf - 1] + 1
                return content[orig_start:orig_end]

    return None


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
            str,
            Field(
                description=(
                    "Exact text to find and replace. "
                    "Must NOT include the line-number prefix from read_file output "
                    "(e.g. '42\\t'). Include only the actual file content after the tab."
                )
            ),
        ],
        new_string: Annotated[
            str,
            Field(
                description=(
                    "Replacement text. "
                    "Must NOT include line-number prefixes. "
                    "Preserve the same indentation style as the surrounding code."
                )
            ),
        ],
        replace_all: Annotated[
            Optional[bool],
            Field(description="Replace all matches instead of the first match."),
        ] = None,
    ) -> ToolResult:
        """Make exact string replacements in a file.

        Use this for precise edits. The old_string must match exactly (including whitespace
        and indentation). For complete file rewrites, use the write_file tool instead.

        IMPORTANT — read_file output format: each line is prefixed with a line number and
        a tab character (e.g. "42\tsome code here"). When constructing old_string or
        new_string from read_file output, include ONLY the content after the tab — never
        include the line number or the tab separator. Copying the prefix into old_string
        will cause the match to fail or corrupt indentation.

        Args:
            ctx: The run context with agent dependencies.
            file_path: Path to the file to edit.
            old_string: Exact text to find and replace (must match exactly, without line-number prefixes).
            new_string: Replacement text (without line-number prefixes).
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

        # Strip read_file line-number prefixes that the model may have copied
        # verbatim (e.g. "42\tsome code"). Do this before any other check so
        # that the identical-strings guard and all downstream logic see clean text.
        old_string = _strip_line_number_prefixes(old_string)
        new_string = _strip_line_number_prefixes(new_string)

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

            time_diff_ns = abs(latest_mtime_ns - file_stat.st_mtime_ns)
            if time_diff_ns > 0:
                self.audit_operation(
                    self.tool_name,
                    "edit",
                    "rejected",
                    file_path=file_path,
                    reason="stale_write",
                )
                return ToolResult.error_result(
                    ToolErrorCode.STALE_WRITE,
                    "File changed by another process while editing. Read the file again and retry "
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
