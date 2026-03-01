"""
pydantic-ai tool functions.

Each former smolagents Tool class is converted to a plain function (or
async function) that pydantic-ai can register on an Agent.

Tools that need per-request state (sandbox config, path resolver, memory
manager, etc.) receive it via ``RunContext[AgentDeps]`` as their first
parameter.  Tools that are stateless omit it.

Dangerous tools (bash_execute, write_file, edit_file, social_message)
support human-in-the-loop (HITL) approval via ``_require_approval()``.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Optional, Union

from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.logger import get_logger

logger = get_logger(__name__)

# Tools that require user approval before execution.
TOOLS_REQUIRING_APPROVAL = frozenset(
    {
        "bash_execute",
        "write_file",
        "edit_file",
        "social_message",
    }
)


# ---------------------------------------------------------------------------
# HITL: approval gate
# ---------------------------------------------------------------------------


async def _require_approval(
    ctx: RunContext[AgentDeps],
    tool_name: str,
    args: dict,
) -> bool:
    """Check session policy or ask the user for approval.

    Returns True if the tool should proceed, False if denied.
    """
    deps = ctx.deps

    # 1. Check session-level policy (set by "Always Allow" / "Always Deny")
    policy = deps.tool_approval_policy.get(tool_name)
    if policy == "always_allow":
        return True
    if policy == "always_deny":
        return False

    # 2. No queue → HITL not wired (e.g. non-streaming / social mode) — auto-approve
    if not deps.sse_queue:
        return True

    # 3. Push approval request to the SSE queue and wait
    request_id = str(uuid.uuid4())
    approval_event = asyncio.Event()
    deps.pending_approvals[request_id] = {
        "event": approval_event,
        "approved": None,
        "remember": None,
        "tool_name": tool_name,
    }

    await deps.sse_queue.put(
        (
            "approval",
            {
                "request_id": request_id,
                "tool_name": tool_name,
                "tool_call_id": ctx.tool_call_id,
                "args": _safe_args_preview(args),
            },
        )
    )

    # 4. Wait for user response or cancellation
    cancel_event = deps.cancel_event
    if cancel_event:
        cancel_task = asyncio.create_task(cancel_event.wait())
        approval_task = asyncio.create_task(approval_event.wait())
        done, pending = await asyncio.wait(
            [cancel_task, approval_task],
            timeout=300,  # 5 min timeout
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
        if cancel_event.is_set():
            deps.pending_approvals.pop(request_id, None)
            return False
    else:
        try:
            await asyncio.wait_for(approval_event.wait(), timeout=300)
        except asyncio.TimeoutError:
            deps.pending_approvals.pop(request_id, None)
            return False

    result = deps.pending_approvals.pop(request_id, {})
    return bool(result.get("approved"))


def _safe_args_preview(args: dict, max_len: int = 500) -> dict:
    """Truncate large arg values for the approval dialog."""
    preview = {}
    for k, v in args.items():
        if v is None:
            continue
        s = str(v)
        preview[k] = (s[:max_len] + "…") if len(s) > max_len else s
    return preview


# ---------------------------------------------------------------------------
# Helper: lazy PathResolver creation
# ---------------------------------------------------------------------------


def _get_resolver(ctx: RunContext[AgentDeps]):
    """Return the PathResolver from deps, or create one on the fly."""
    if ctx.deps.path_resolver is not None:
        return ctx.deps.path_resolver

    from suzent.tools.path_resolver import PathResolver
    from suzent.config import CONFIG

    resolver = PathResolver(
        ctx.deps.chat_id,
        ctx.deps.sandbox_enabled,
        sandbox_data_path=CONFIG.sandbox_data_path,
        custom_volumes=ctx.deps.custom_volumes,
        workspace_root=ctx.deps.workspace_root,
    )
    ctx.deps.path_resolver = resolver
    return resolver


# ═══════════════════════════════════════════════════════════════════════════
# 1. WebSearchTool → web_search  (no context needed)
# ═══════════════════════════════════════════════════════════════════════════
async def web_search(
    query: str,
    categories: Optional[str] = None,
    max_results: int = 10,
    time_range: Optional[str] = None,
    page: int = 1,
) -> str:
    """Perform a web search using SearXNG or DuckDuckGo.

    Args:
        query: The search query string.
        categories: Search category (general, news, images, videos).
        max_results: Maximum number of results to return (default 10, max 20).
        time_range: Time range filter (day, week, month, year).
        page: Page number for pagination (default 1).
    """
    from suzent.tools.websearch_tool import WebSearchTool

    tool = WebSearchTool()
    return await tool.forward(
        query=query,
        categories=categories,
        max_results=max_results,
        time_range=time_range,
        page=page,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. WebpageTool → webpage_fetch  (no context needed)
# ═══════════════════════════════════════════════════════════════════════════


def webpage_fetch(url: str) -> str:
    """Fetch and extract the main content of a webpage as markdown.

    Args:
        url: The URL of the webpage to fetch.
    """
    from suzent.tools.webpage_tool import WebpageTool

    tool = WebpageTool()
    return tool.forward(url=url)


# ═══════════════════════════════════════════════════════════════════════════
# 3. BashTool → bash_execute  (needs context + HITL)
# ═══════════════════════════════════════════════════════════════════════════


async def bash_execute(
    ctx: RunContext[AgentDeps],
    content: str,
    language: Optional[str] = None,
    timeout: Optional[int] = None,
) -> str:
    """Execute code in a secure environment (sandbox or host mode).

    Supported languages:
    - python: Execute Python code
    - nodejs: Execute Node.js code
    - command: Execute shell commands

    Storage paths (works in both modes):
    - /persistence: Private storage (persists across sessions, this chat only)
    - /shared: Shared storage (accessible by all chats)

    Args:
        content: The code or shell command to execute.
        language: Execution language: 'python', 'nodejs', or 'command'.
        timeout: Execution timeout in seconds (optional).
    """
    if not await _require_approval(
        ctx, "bash_execute", {"content": content, "language": language}
    ):
        return "[Tool execution denied by user.]"

    from suzent.tools.bash_tool import BashTool

    tool = BashTool()
    tool.chat_id = ctx.deps.chat_id
    tool.sandbox_enabled = ctx.deps.sandbox_enabled
    tool.workspace_root = ctx.deps.workspace_root
    if ctx.deps.custom_volumes:
        tool.set_custom_volumes(ctx.deps.custom_volumes)
    return tool.forward(content=content, language=language, timeout=timeout)


# ═══════════════════════════════════════════════════════════════════════════
# 4. ReadFileTool → read_file  (needs context)
# ═══════════════════════════════════════════════════════════════════════════


def read_file(
    ctx: RunContext[AgentDeps],
    file_path: str,
    offset: Optional[int] = None,
    limit: Optional[int] = None,
) -> str:
    """Read file content from the filesystem.

    Supports various file formats:
    - Text files: .txt, .py, .js, .json, .md, .csv, etc.
    - Documents: .pdf, .docx, .xlsx, .pptx (converted to markdown)
    - Images: .jpg, .png (OCR text extraction)

    Use 'offset' and 'limit' for reading portions of large files.

    Args:
        file_path: Path to the file to read.
        offset: Line number to start from (0-indexed).
        limit: Number of lines to read (omit for all).
    """
    from suzent.tools.read_file_tool import ReadFileTool

    tool = ReadFileTool()
    tool.set_context(_get_resolver(ctx))
    return tool.forward(file_path=file_path, offset=offset, limit=limit)


# ═══════════════════════════════════════════════════════════════════════════
# 5. WriteFileTool → write_file  (needs context + HITL)
# ═══════════════════════════════════════════════════════════════════════════


async def write_file(
    ctx: RunContext[AgentDeps],
    file_path: str,
    content: str,
) -> str:
    """Write content to a file.

    Creates the file and any necessary parent directories if they don't exist.
    Overwrites existing files.

    Args:
        file_path: Path to the file to write.
        content: The content to write to the file.
    """
    if not await _require_approval(
        ctx, "write_file", {"file_path": file_path, "content": content}
    ):
        return "[Tool execution denied by user.]"

    from suzent.tools.write_file_tool import WriteFileTool

    tool = WriteFileTool()
    tool.set_context(_get_resolver(ctx))
    return tool.forward(file_path=file_path, content=content)


# ═══════════════════════════════════════════════════════════════════════════
# 6. EditFileTool → edit_file  (needs context + HITL)
# ═══════════════════════════════════════════════════════════════════════════


async def edit_file(
    ctx: RunContext[AgentDeps],
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> str:
    """Edit a file by replacing text.

    Args:
        file_path: Path to the file to edit.
        old_string: The exact text to find and replace.
        new_string: The replacement text.
        replace_all: If True, replace all occurrences (default False).
    """
    if not await _require_approval(
        ctx,
        "edit_file",
        {"file_path": file_path, "old_string": old_string, "new_string": new_string},
    ):
        return "[Tool execution denied by user.]"

    from suzent.tools.edit_file_tool import EditFileTool

    tool = EditFileTool()
    tool.set_context(_get_resolver(ctx))
    return tool.forward(
        file_path=file_path,
        old_string=old_string,
        new_string=new_string,
        replace_all=replace_all,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 7. GlobTool → glob_search  (needs context)
# ═══════════════════════════════════════════════════════════════════════════


def glob_search(
    ctx: RunContext[AgentDeps],
    pattern: str,
    path: Optional[str] = None,
) -> str:
    """Find files matching a glob pattern.

    Args:
        pattern: Glob pattern (e.g. '**/*.py', 'src/*.ts').
        path: Directory to search in (default: workspace root).
    """
    from suzent.tools.glob_tool import GlobTool

    tool = GlobTool()
    tool.set_context(_get_resolver(ctx))
    return tool.forward(pattern=pattern, path=path)


# ═══════════════════════════════════════════════════════════════════════════
# 8. GrepTool → grep_search  (needs context)
# ═══════════════════════════════════════════════════════════════════════════


def grep_search(
    ctx: RunContext[AgentDeps],
    pattern: str,
    path: Optional[str] = None,
    include: Optional[str] = None,
    case_insensitive: bool = False,
    context_lines: int = 0,
) -> str:
    """Search file contents using regular expressions.

    Args:
        pattern: Regular expression pattern to search for.
        path: Directory to search in (default: workspace root).
        include: File glob filter (e.g. '*.py').
        case_insensitive: If True, ignore case when matching.
        context_lines: Number of context lines to show around matches.
    """
    from suzent.tools.grep_tool import GrepTool

    tool = GrepTool()
    tool.set_context(_get_resolver(ctx))
    return tool.forward(
        pattern=pattern,
        path=path,
        include=include,
        case_insensitive=case_insensitive,
        context_lines=context_lines,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 9. PlanningTool → planning_update  (needs context)
# ═══════════════════════════════════════════════════════════════════════════


def planning_update(
    ctx: RunContext[AgentDeps],
    action: str,
    goal: Optional[str] = None,
    phases: Optional[Union[str, list]] = None,
    current_phase_id: Optional[str] = None,
    next_phase_id: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> str:
    """Create or update a structured plan for the current task.

    Args:
        action: Action to perform ('update' to create/replace plan, 'advance' to move to next phase).
        goal: The overall goal or objective (for 'update' action).
        phases: JSON array of phase objects with id, title, tasks (for 'update' action).
        current_phase_id: ID of the current phase (for 'advance' action).
        next_phase_id: ID of the next phase to activate (for 'advance' action).
        chat_id: Override chat ID (optional, uses session chat_id by default).
    """
    import json as _json

    from suzent.tools.planning_tool import PlanningTool

    parsed_phases = None
    if phases is not None:
        if isinstance(phases, str):
            try:
                parsed_phases = _json.loads(phases)
            except (ValueError, TypeError):
                return f"**Error: Invalid phases**\n\nCould not parse phases JSON: {phases[:200]}"
        elif isinstance(phases, list):
            parsed_phases = phases
        else:
            parsed_phases = phases

    try:
        parsed_current = int(current_phase_id) if current_phase_id is not None else None
    except (ValueError, TypeError):
        return f"**Error: Invalid current_phase_id**\n\nExpected integer, got '{current_phase_id}'"

    try:
        parsed_next = int(next_phase_id) if next_phase_id is not None else None
    except (ValueError, TypeError):
        return f"**Error: Invalid next_phase_id**\n\nExpected integer, got '{next_phase_id}'"

    tool = PlanningTool()
    tool.set_chat_context(ctx.deps.chat_id)
    return tool.forward(
        action=action,
        goal=goal,
        phases=parsed_phases,
        current_phase_id=parsed_current,
        next_phase_id=parsed_next,
        chat_id=chat_id,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 10. BrowsingTool → browser_action  (no context needed)
# ═══════════════════════════════════════════════════════════════════════════


def browser_action(
    command: str,
    arguments: Optional[list] = None,
) -> str:
    """Control a browser to interact with web pages.

    Supported commands: open, snapshot, click, fill, scroll, back,
    forward, reload, press, screenshot, click_coords.

    Args:
        command: Browser command to execute.
        arguments: Command arguments as a list of strings.
    """
    from suzent.tools.browsing_tool import BrowsingTool

    tool = BrowsingTool()
    return tool.forward(command=command, arguments=arguments or [])


# ═══════════════════════════════════════════════════════════════════════════
# 11. SkillTool → skill_execute  (needs context)
# ═══════════════════════════════════════════════════════════════════════════


def skill_execute(
    ctx: RunContext[AgentDeps],
    skill_name: str,
) -> str:
    """Execute a user-defined skill by name.

    Args:
        skill_name: Name of the skill to execute.
    """
    from suzent.tools.skill_tool import SkillTool

    sm = ctx.deps.skill_manager
    if not sm:
        from suzent.skills import get_skill_manager

        sm = get_skill_manager()

    tool = SkillTool(skill_manager=sm)
    return tool.forward(skill_name=skill_name)


# ═══════════════════════════════════════════════════════════════════════════
# 12. SocialMessageTool → social_message  (needs context + HITL)
# ═══════════════════════════════════════════════════════════════════════════


async def social_message(
    ctx: RunContext[AgentDeps],
    message: Optional[str] = None,
    channel: Optional[str] = None,
    recipient: Optional[str] = None,
    list_contacts: bool = False,
) -> str:
    """Send a message to social platforms or list available contacts.

    Args:
        message: The message text to send.
        channel: Target platform (telegram, discord, slack, feishu).
        recipient: Recipient identifier (chat/channel ID).
        list_contacts: If True, list available contacts instead of sending.
    """
    # Only require approval for actual sends, not listing contacts
    if not list_contacts and message:
        if not await _require_approval(
            ctx,
            "social_message",
            {"message": message, "channel": channel, "recipient": recipient},
        ):
            return "[Tool execution denied by user.]"

    from suzent.tools.social_message_tool import SocialMessageTool

    tool = SocialMessageTool()

    cm = ctx.deps.channel_manager
    loop = ctx.deps.event_loop
    social_ctx = ctx.deps.social_context

    if not cm:
        import asyncio
        from suzent.core.social_brain import get_active_social_brain

        brain = get_active_social_brain()
        if brain:
            cm = brain.channel_manager
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

    if cm and loop:
        tool.set_social_context(
            channel_manager=cm,
            event_loop=loop,
            default_platform=social_ctx.get("platform"),
            default_target=social_ctx.get("target_id"),
        )

    return tool.forward(
        message=message,
        channel=channel,
        recipient=recipient,
        list_contacts=list_contacts,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 13. SpeakTool → speak  (no context needed)
# ═══════════════════════════════════════════════════════════════════════════


def speak(
    text: str,
    prompt: Optional[str] = None,
) -> str:
    """Convert text to speech and play it.

    Args:
        text: The text to speak aloud.
        prompt: Optional voice prompt/style.
    """
    from suzent.tools.voice_tool import SpeakTool

    tool = SpeakTool()
    return tool.forward(text=text, prompt=prompt)


# ═══════════════════════════════════════════════════════════════════════════
# 14. MemorySearchTool → memory_search  (needs context)
# ═══════════════════════════════════════════════════════════════════════════


async def memory_search(
    ctx: RunContext[AgentDeps],
    query: str,
    limit: int = 10,
) -> str:
    """Search long-term archival memory for relevant information.

    Uses semantic similarity to find relevant memories even if the exact
    words differ.

    Args:
        query: What to search for in memory (use natural language).
        limit: Maximum number of results to return (default 10).
    """
    mm = ctx.deps.memory_manager
    if not mm:
        return "Memory system not available."

    from suzent.memory.tools import MemorySearchTool

    tool = MemorySearchTool(memory_manager=mm)
    tool.set_context(chat_id=ctx.deps.chat_id, user_id=ctx.deps.user_id)
    return await tool.forward_async(query=query, limit=limit)


# ═══════════════════════════════════════════════════════════════════════════
# 15. MemoryBlockUpdateTool → memory_block_update  (needs context)
# ═══════════════════════════════════════════════════════════════════════════


async def memory_block_update(
    ctx: RunContext[AgentDeps],
    block: str,
    operation: str,
    content: str,
    search_pattern: Optional[str] = None,
) -> str:
    """Update core memory blocks that are always visible in context.

    Core memory blocks:
    - persona: Your identity, role, capabilities, and preferences
    - user: Information about the current user
    - facts: Key facts you should always remember
    - context: Current session context (active tasks, goals)

    Args:
        block: Which block to update ('persona', 'user', 'facts', or 'context').
        operation: Operation to perform ('replace', 'append', or 'search_replace').
        content: New content or content to append.
        search_pattern: For search_replace: the text to find and replace.
    """
    mm = ctx.deps.memory_manager
    if not mm:
        return "Memory system not available."

    from suzent.memory.tools import MemoryBlockUpdateTool

    tool = MemoryBlockUpdateTool(memory_manager=mm)
    tool.set_context(chat_id=ctx.deps.chat_id, user_id=ctx.deps.user_id)
    return await tool.forward_async(
        block=block,
        operation=operation,
        content=content,
        search_pattern=search_pattern,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Registry mapping: tool class name → tool function
# ═══════════════════════════════════════════════════════════════════════════

TOOL_FUNCTIONS: dict[str, callable] = {
    "WebSearchTool": web_search,
    "WebpageTool": webpage_fetch,
    "BashTool": bash_execute,
    "ReadFileTool": read_file,
    "WriteFileTool": write_file,
    "EditFileTool": edit_file,
    "GlobTool": glob_search,
    "GrepTool": grep_search,
    "PlanningTool": planning_update,
    "BrowsingTool": browser_action,
    "SkillTool": skill_execute,
    "SocialMessageTool": social_message,
    "SpeakTool": speak,
    "MemorySearchTool": memory_search,
    "MemoryBlockUpdateTool": memory_block_update,
}
