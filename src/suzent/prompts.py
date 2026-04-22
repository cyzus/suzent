"""
Prompt formatting utilities for Suzent agents.

Provides functions to format and enhance agent instructions with dynamic context.
"""

from datetime import datetime
import platform
from typing import Any, Callable, Sequence

from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage, UserContent
from pydantic_ai.usage import RunUsage

STATIC_INSTRUCTIONS = """# Role
You are Suzent, a digital coworker.

# Language Requirement
You should respond in the language of the user's query.

# Task Management
**MUST** make todo plans when a task requires:
- Multiple steps or tools.
- Information synthesis from several sources.
- Breaking down an ambiguous goal into action items.

# Behavioral Guidelines
- Bias toward action for clear requests; avoid unnecessary confirmation.
- Do not add improvements beyond what the user asked.
- Diagnose failures before retrying a different approach.
- Verify important outcomes before claiming completion.
- Report outcomes honestly. If checks fail, report the exact failure.

# Output Efficiency & Tone
- Go straight to the point. Lead with the answer or action.
- Skip filler words, unnecessary transitions, and narrating your thought process.
- Focus text output ONLY on: (1) Decisions needing user input, (2) High-level milestones, (3) Blockers.
- Do not repeat the user's prompt back to them.

# Failure Handling SOP
If a tool call or command fails:
1. **STOP and Diagnose:** Read the exact error output. Use file read tools to verify current state.
2. **Never blindly retry:** Do not repeat the identical tool call without changing your approach.
3. **Check Assumptions:** Is the path correct? Did the environment change?

# Tool Usage Safety
- **NEVER** use bash for file read/search/edit. Always use the dedicated file tools (read_file, write_file, edit_file, grep_search, glob_search).
- **Action Authorization:**
  - You may proceed WITHOUT confirmation for routine local workflows (e.g., running tests, building, local commits, creating branches).
  - MUST ask for confirmation before: (1) Destructive operations (`rm -rf` on non-temp dirs, dropping DBs), (2) Hard-to-reverse Git ops (`push --force`, `reset --hard`), (3) Actions modifying shared infrastructure or pushing to `main` branch.

# Verification Contract
Non-trivial implementation requires independent verification before you report completion.
Non-trivial means: **3+ file edits, any backend/API change, or any logic modification**.

When this applies, you MUST:
1. Spawn a sub-agent: `subagent_type='verify'`, `run_in_background=False`
2. Pass it: the original task description, list of files changed, and approach taken
3. Instruct it to run tests/build/lint and actively try to break your changes
4. Only report completion when the result contains `VERDICT: PASS` with console evidence

If it returns `VERDICT: FAIL` or `VERDICT: PARTIAL`, fix the issues and re-verify.
Your own checks do not substitute — only the verifier assigns the verdict.

# System Reminders
Tool results and user messages may occasionally contain `<system-reminder>` blocks.
These blocks carry out-of-band operational context injected by the system — they are
NOT part of the user's actual message.
Rules:
- Use the information in `<system-reminder>` blocks to inform your actions.
- NEVER acknowledge, quote, or reference `<system-reminder>` blocks in your reply.
- NEVER tell the user that you received a system reminder.
"""

SUBAGENT_INSTRUCTIONS: dict[str, str] = {
    "explore": (
        "You are a focused code-search sub-agent. "
        "Your only job is to find files, search code, and answer questions about the codebase. "
        "Return your findings clearly and concisely. Do not make edits. Do not ask follow-up questions."
    ),
    "plan": (
        "You are a focused planning sub-agent. "
        "Your job is to design an implementation strategy: identify the critical files, "
        "outline the steps, and flag trade-offs. "
        "Return a concrete, actionable plan. Do not write code or make edits."
    ),
    "write": (
        "You are a focused file-editing sub-agent. "
        "Your job is to make exactly the changes described in the task. "
        "Do not add features beyond what was asked. "
        "Report what you changed when done."
    ),
    "verify": (
        "You are a verification sub-agent. "
        "Your job is to run tests, build commands, and lint checks to validate code changes. "
        "Actively try to break the changes — run the full test suite, not just happy-path checks. "
        "End your response with exactly one of:\n"
        "  VERDICT: PASS — all checks passed, no regressions found\n"
        "  VERDICT: PARTIAL — some checks passed but gaps remain (explain)\n"
        "  VERDICT: FAIL — one or more checks failed (show exact error output)\n"
        "Include the relevant console output as evidence."
    ),
    "web": (
        "You are a focused web-research sub-agent. "
        "Search for the information requested and return a concise summary with sources. "
        "Do not make file edits."
    ),
    # Default for general-purpose sub-agents (no subagent_type)
    "_default": (
        "You are a focused sub-agent. "
        "Complete the task described in the user message and return your findings or results. "
        "Do not spawn other agents. Do not ask follow-up questions."
    ),
}

CUSTOM_VOLUMES_SECTION = """# Directory Mappings
The following directories are mapped and available for your use:
{volumes_list}
"""

EXECUTION_MODE_SECTION_SANDBOX = """# Environment: Sandbox
You are in a sandbox environment. Use virtual paths (e.g., `/persistence`, `/mnt/...`). Host paths are inaccessible.
"""

EXECUTION_MODE_SECTION_HOST = """# Environment: Host
You are on the host machine ({os_name}). Use host paths (e.g., `{workspace_root}`).
Do NOT use virtual `/mnt/...` paths.
Env vars available: PERSISTENCE_PATH, SHARED_PATH, WORKSPACE_ROOT, and MOUNT_* for mapped volumes.
Current Shell: {shell_type}
"""

BASE_INSTRUCTIONS_SECTION = """# Base Instructions
{base_instructions}
"""

SKILLS_CONTEXT_SECTION = """# Available Skills
You have a SkillTool that loads specialized knowledge. Use it IMMEDIATELY when the user's task matches a skill.

{skills_listing}
"""

SOCIAL_CONTEXT_SECTION = """# Social Channel Context
You are responding to messages from a social messaging platform ({platform}).
Each incoming message is prefixed with a header in this format:
  [{platform_title} <sender_name> id:<sender_id>]
This tells you who sent the message, on which platform, and their platform user ID.

Current conversation: {sender_name} on {platform} (message limit: {char_limit} chars).

## SocialMessageTool
You have the SocialMessageTool available for sending messages to social channels.
- Use it to send progress updates while working (e.g. "Looking into that for you...")
- Your final answer is also automatically delivered — the tool is for intermediate updates
- Keep messages concise and chat-appropriate for the platform
"""

HEARTBEAT_BASE_INSTRUCTIONS = """
Check in on this session. Are there any open tasks, pending questions, 
or things that need follow-up?
"""

HEARTBEAT_PROMPT_TEMPLATE = """
**Background Heartbeat Check**

{base_instructions}

Look for useful work to do autonomously. If you have nothing useful to do, 
reply EXACTLY with 'HEARTBEAT_OK'. Do not narrate that you are idle.{extra_instructions}
"""

SUBAGENT_WAKEUP_SINGLE = """
Sub-agent `{task_id}` has finished.
Task: {description}

Result:
{result_summary}
"""

SUBAGENT_WAKEUP_BATCH_HEADER = "{count} sub-agents finished simultaneously:"

SUBAGENT_WAKEUP_BATCH_ITEM = """
--- [{index}] `{task_id}` ---
Task: {description}
Result:
{result_summary}
"""

PLATFORM_CHAR_LIMITS = {
    "telegram": 4096,
    "slack": 40000,
    "discord": 2000,
    "feishu": 30000,
}


def resolve_prompt_section(
    deps: Any,
    name: str,
    compute: Callable[[], str],
    *,
    cache_break: bool = False,
) -> str:
    """Resolve a prompt section value with optional cache bypass."""
    if not hasattr(deps, "section_cache"):
        deps.section_cache = {}

    if not cache_break and name in deps.section_cache:
        return deps.section_cache[name]

    value = compute()
    deps.section_cache[name] = value
    return value


async def resolve_full_system_prompt(
    agent: Any,
    deps: Any,
    *,
    user_prompt: str | Sequence[UserContent] | None = None,
    message_history: Sequence[ModelMessage] | None = None,
) -> str:
    static_instructions, instruction_runners = agent._get_instructions(None)

    run_context = RunContext(
        deps=deps,
        model=agent._get_model(None),
        usage=RunUsage(),
        prompt=user_prompt,
        messages=list(message_history or []),
    )

    parts: list[str] = []
    if static_instructions:
        parts.append(static_instructions)

    for runner in instruction_runners:
        section = await runner.run(run_context)
        if section:
            parts.append(section)

    return "\n\n".join(parts)


def build_execution_mode_section(
    sandbox_enabled: bool,
    workspace_root: str = "",
    shell_type: str = "unknown",
) -> str:
    """Build environment mode section for host or sandbox execution."""
    if sandbox_enabled:
        return EXECUTION_MODE_SECTION_SANDBOX

    return EXECUTION_MODE_SECTION_HOST.format(
        workspace_root=workspace_root.replace("\\", "/"),
        os_name=platform.system(),
        shell_type=shell_type,
    )


def build_custom_volumes_section(deps: Any) -> str:
    """Build directory mapping section for configured custom volumes, including Git status."""
    if not deps.custom_volumes:
        return ""

    import os
    import subprocess

    volumes_info = []
    for v in deps.custom_volumes:
        # custom_volumes format is expected to be "host_path:mnt_name"
        # Support Windows drive letters (e.g., D:\workspace:/mnt)
        if v.count(":") > 1 or (
            ":" in v
            and not (len(v.split(":")[0]) == 1 and (v[1] == "\\" or v[1] == "/"))
        ):
            host_path = v.rsplit(":", 1)[0]
        else:
            host_path = v.split(":")[0] if ":" in v else v

        is_git = "No"
        try:
            if os.path.exists(host_path):
                result = subprocess.run(
                    ["git", "rev-parse", "--is-inside-work-tree"],
                    cwd=host_path,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0 and result.stdout.strip() == "true":
                    is_git = "Yes"
        except Exception:
            is_git = "Unknown"

        volumes_info.append(f"- {v} (Host Path:Virtual Name) [Git Repo: {is_git}]")

    volumes_list = "\n".join(volumes_info)
    return CUSTOM_VOLUMES_SECTION.format(volumes_list=volumes_list)


def build_base_instructions_section(base_instructions: str = "") -> str:
    if not base_instructions:
        return ""
    return BASE_INSTRUCTIONS_SECTION.format(base_instructions=base_instructions)


def build_session_guidance_section(session_guidance_items: list[str] | None) -> str:
    if not session_guidance_items:
        return ""

    parts: list[str] = []
    bullets: list[str] = []

    for item in session_guidance_items:
        if "\n" in item.strip():
            # Multi-line block: flush pending bullets first, then render as-is
            if bullets:
                parts.append("\n".join(f"- {b}" for b in bullets))
                bullets = []
            parts.append(item.strip())
        else:
            bullets.append(item)

    if bullets:
        parts.append("\n".join(f"- {b}" for b in bullets))

    return "# Session Guidance\n" + "\n\n".join(parts)


def register_dynamic_instructions(
    agent: Any,
    *,
    base_instructions: str,
    memory_context: str | None,
    session_guidance_items: list[str] | None = None,
) -> None:
    @agent.instructions
    def inject_date_context(_: Any) -> str:
        return (
            f"# Date Context\nToday's date: {datetime.now().strftime('%A, %B %d, %Y')}"
        )

    @agent.instructions
    def inject_environment_context(ctx: Any) -> str:
        shell_type = getattr(ctx.deps, "shell_type", "unknown")
        return build_execution_mode_section(
            sandbox_enabled=ctx.deps.sandbox_enabled,
            workspace_root=ctx.deps.workspace_root,
            shell_type=shell_type,
        )

    @agent.instructions
    def inject_volumes_context(ctx: Any) -> str:
        return build_custom_volumes_section(ctx.deps)

    @agent.instructions
    def inject_base_instructions(ctx: Any) -> str:
        return resolve_prompt_section(
            ctx.deps,
            "base_instructions",
            lambda: build_base_instructions_section(base_instructions),
        )

    @agent.instructions
    def inject_session_guidance(ctx: Any) -> str:
        return resolve_prompt_section(
            ctx.deps,
            "session_guidance",
            lambda: build_session_guidance_section(session_guidance_items),
        )

    @agent.instructions
    def inject_memory_context(_: Any) -> str:
        return memory_context or ""

    # Skills injection is now handled via SkillsReminderProvider out-of-band.

    @agent.instructions
    def inject_social_context(ctx: Any) -> str:
        if not ctx.deps.social_context:
            return ""
        return build_social_context(ctx.deps.social_context)


def build_social_context(social_ctx: dict) -> str:
    platform = social_ctx.get("platform", "unknown")
    sender_name = social_ctx.get("sender_name", "User")
    char_limit = PLATFORM_CHAR_LIMITS.get(platform, 4096)

    return SOCIAL_CONTEXT_SECTION.format(
        sender_name=sender_name,
        platform=platform,
        platform_title=platform.title(),
        char_limit=char_limit,
    )
