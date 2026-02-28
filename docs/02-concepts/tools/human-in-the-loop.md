# Human-in-the-Loop (HITL) Tool Approval

Dangerous tools require explicit user approval before execution. This prevents the agent from running destructive commands, overwriting files, or sending messages without the user's consent.

## Gated Tools

| Tool | Function | What's gated |
|------|----------|-------------|
| BashTool | `bash_execute` | All executions |
| WriteFileTool | `write_file` | All writes |
| EditFileTool | `edit_file` | All edits |
| SocialMessageTool | `social_message` | Sending messages (listing contacts is ungated) |

## User Experience

When a gated tool is invoked, the chat UI pauses and shows an approval dialog:

- **Allow** — approve this single execution, resume the tool
- **Always Allow** — approve and remember for this session (no further prompts for this tool)
- **Deny** — block execution, the tool returns `[Tool execution denied by user.]`

The agent sees the denial message and can adjust its approach (e.g. ask the user for an alternative).

## Session Memory

Clicking **"Always Allow"** sets a session-level policy:

```
tool_approval_policy["bash_execute"] = "always_allow"
```

This persists for the lifetime of the current streaming session. Subsequent calls to the same tool skip the approval dialog entirely. The policy resets when:

- The user starts a new message (new streaming session)
- The page is refreshed
- The stream is stopped

This mirrors the behavior of Claude Code and AI IDE tools where you can grant persistent permission within a session.

## How It Works

### Architecture

The HITL system uses a queue-based streaming architecture:

```
Agent Task (background)
    │
    ├── Tool calls _require_approval()
    │       │
    │       ├── Check session policy → auto-approve/deny if set
    │       ├── Push "tool_approval_required" to SSE queue
    │       └── await asyncio.Event (blocks tool execution)
    │
SSE Generator (drains queue)
    │
    ├── Yields regular stream events
    └── Yields tool_approval_required event → Frontend
                                                │
                                          User clicks
                                                │
                                    POST /chat/approve-tool
                                                │
                                    asyncio.Event.set() → Tool resumes
```

The agent runs in a background `asyncio.Task`. When a tool needs approval, it pushes a request to the SSE queue and waits on an `asyncio.Event`. The SSE generator delivers the approval request to the frontend. When the user responds, the HTTP endpoint sets the event, unblocking the tool.

### SSE Event

```json
{
  "type": "tool_approval_required",
  "data": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "tool_name": "bash_execute",
    "args_preview": {
      "content": "rm -rf /tmp/old-data",
      "language": "command"
    }
  }
}
```

### API Endpoint

```
POST /chat/approve-tool

{
  "chat_id": "...",
  "request_id": "...",
  "approved": true,
  "remember": "session"   // or null for one-time approval
}
```

### Timeout & Cancellation

- **Timeout**: If the user doesn't respond within 5 minutes, the tool is auto-denied.
- **Cancel**: If the user stops the stream while approval is pending, all pending approvals are auto-denied.
- **Cleanup**: On stream end, the `active_deps` registry is cleared.

## Adding HITL to a New Tool

To gate a new tool behind approval:

1. Add the tool name to `TOOLS_REQUIRING_APPROVAL` in `tool_functions.py`:

```python
TOOLS_REQUIRING_APPROVAL = frozenset({
    "bash_execute",
    "write_file",
    "edit_file",
    "social_message",
    "my_new_tool",       # ← add here
})
```

2. Make the tool function `async` and call `_require_approval()`:

```python
async def my_new_tool(ctx: RunContext[AgentDeps], param: str) -> str:
    """Tool description."""
    if not await _require_approval(ctx, "my_new_tool", {"param": param}):
        return "[Tool execution denied by user.]"

    # ... proceed with tool logic ...
```

The frontend automatically handles the approval UI for any tool that emits a `tool_approval_required` event — no frontend changes needed.

## Non-Streaming Mode

In contexts where HITL is not available (cron jobs, social messaging responses, headless mode), tools auto-approve. This is detected by the absence of `sse_queue` on `AgentDeps`.
