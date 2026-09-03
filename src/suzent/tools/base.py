"""
Lightweight Tool base class and result model for pydantic-ai integration.

Each Tool subclass defines a ``forward()`` method with typed parameters
that pydantic-ai uses directly for JSON schema generation. The registry
auto-wraps ``forward()`` as a pydantic-ai tool function.

ToolResult provides a structured envelope for tool responses, including
success/failure indicators, machine-readable error codes, user-friendly
messages, and optional metadata for advanced retry and recovery logic.
"""

from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, Field, model_validator

from suzent.logger import get_logger

logger = get_logger(__name__)

OUTPUT_CHAR_LIMIT = 30_000


def truncate_tool_output(
    text: str,
    limit: int = OUTPUT_CHAR_LIMIT,
    *,
    keep_tail: bool = False,
    full_output_path: Optional[str] = None,
) -> str:
    """Truncate output to *limit* chars while reporting the omitted section.

    *full_output_path* names a file holding the whole output. The part a cap
    removes is often the part that was wanted — the failing assertion at the end
    of a test run, the last of a build log — so the marker says where the rest
    is rather than only that it is gone.
    """
    if not text or len(text) <= limit:
        return text

    def _marker(omitted: str) -> str:
        lines = omitted.count(chr(10)) + 1
        if full_output_path:
            return f"... [{lines} lines truncated — full output: {full_output_path}]"
        return f"... [{lines} lines truncated]"

    if keep_tail:
        omitted = text[:-limit]
        return _marker(omitted) + "\n" + text[-limit:]

    omitted = text[limit:]
    return text[:limit] + "\n" + _marker(omitted)


class ToolCapability(str, Enum):
    """Capability that owns and presents a related set of tools."""

    FILESYSTEM = "Filesystem"
    SHELL = "Shell"
    WEB = "Web"
    TASKS = "Tasks & goals"
    AGENT = "Agent"
    CREATIVE = "Creative"
    MEMORY = "Memory & recall"


# Compatibility alias for existing tool implementations and third-party tools.
ToolGroup = ToolCapability


class ToolErrorCode(Enum):
    """Standard error codes for tool failures, enabling meaningful recovery strategies."""

    # File operation errors
    FILE_NOT_FOUND = "file_not_found"
    FILE_TOO_LARGE = "file_too_large"
    DIRECTORY_REQUIRED = "directory_required"
    FILE_REQUIRED = "file_required"
    BINARY_FILE = "binary_file"
    ENCODING_ERROR = "encoding_error"

    # Edit-specific errors
    AMBIGUOUS_MATCH = "ambiguous_match"
    NO_MATCH = "no_match"
    NO_OP_CHANGE = "no_op_change"
    STALE_WRITE = "stale_write"

    # Permission and path errors
    PERMISSION_DENIED = "permission_denied"
    UNC_PATH_NOT_SUPPORTED = "unc_path_not_supported"
    INVALID_PATH = "invalid_path"

    # Execution errors
    EXECUTION_FAILED = "execution_failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"

    # Input validation errors
    INVALID_ARGUMENT = "invalid_argument"
    MISSING_REQUIRED_PARAM = "missing_required_param"

    # Generic fallback
    UNKNOWN_ERROR = "unknown_error"


class ToolResult(BaseModel):
    """Structured result envelope for tool execution outcomes.

    Attributes:
        success: Whether the tool executed successfully.
        message: User-friendly message describing the result or error.
        error_code: Machine-readable error code for routing recovery logic (None if success=True).
        metadata: Optional dict with additional context (e.g., match count, file size, elapsed time).
    """

    success: bool
    message: str
    error_code: Optional[ToolErrorCode] = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_error_code(self) -> "ToolResult":
        if self.success and self.error_code is not None:
            raise ValueError("error_code should be None when success=True")
        if not self.success and self.error_code is None:
            raise ValueError("error_code is required when success=False")
        return self

    def __str__(self) -> str:
        """Return the user-friendly message for LLM context."""
        return self.message

    @classmethod
    def success_result(
        cls, message: str, metadata: Optional[dict[str, Any]] = None
    ) -> "ToolResult":
        """Create a successful result."""
        return cls(success=True, message=message, metadata=metadata or {})

    @classmethod
    def error_result(
        cls,
        error_code: ToolErrorCode,
        message: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> "ToolResult":
        """Create a failure result with error code."""
        return cls(
            success=False,
            message=message,
            error_code=error_code,
            metadata=metadata or {},
        )


class Tool:
    """Base class for tool implementations.

    Subclasses set class attributes and implement ``forward()``.
    The registry reads ``name``, ``tool_name``, and ``requires_approval``
    to build the pydantic-ai tool list.
    """

    name: str = ""  # Registry key (e.g., "ReadFileTool")
    tool_name: str = ""  # pydantic-ai function name (e.g., "read_file")
    group: Union[ToolCapability, str] = ""  # empty = not user-configurable
    display_name: Optional[str] = None
    description: Optional[str] = None
    requires_approval: bool = False
    deferrable: bool = True  # False = never goes into the activatable pool
    session_guidance: Optional[str] = None
    guidance_priority: int = 100
    output_char_limit: int = OUTPUT_CHAR_LIMIT
    keep_output_tail: bool = False

    def __init__(self, *args, **kwargs):
        pass

    def forward(self, **kwargs):
        raise NotImplementedError("Subclasses must implement forward()")

    @staticmethod
    def is_tool_denied(deps: Any, tool_name: str) -> Optional[str]:
        """Return a denial reason when policy explicitly blocks a tool."""
        policy = getattr(deps, "tool_approval_policy", {}) or {}
        aliases = [tool_name]
        if tool_name == "run_command":
            aliases.extend(["RunCommandTool", "ShellTool"])
        elif tool_name == "start_command":
            aliases.extend(["StartCommandTool", "ShellTool"])
        elif tool_name == "check_command":
            aliases.append("CheckCommandTool")
        elif tool_name == "stop_command":
            aliases.append("StopCommandTool")
        if any(policy.get(name) == "always_deny" for name in aliases):
            return f"Tool '{tool_name}' is denied by policy"
        return None

    @staticmethod
    def audit_operation(
        tool_name: str, operation: str, outcome: str, **metadata
    ) -> None:
        """Emit a structured audit log entry for a tool operation."""
        details = ", ".join(
            f"{key}={value!r}" for key, value in metadata.items() if value is not None
        )
        message = f"[audit] tool={tool_name} operation={operation} outcome={outcome}"
        if details:
            message = f"{message} {details}"
        logger.info(message)
