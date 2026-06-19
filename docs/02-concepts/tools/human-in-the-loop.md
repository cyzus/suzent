# Tool Permissions and Human Approval

Suzent evaluates every deferred tool call through one backend permission engine. The engine decides whether to allow, deny, or ask, and it supplies the exact actions shown by the frontend. The client never constructs permission rules itself.

## Deferred Tools

| Tool | Function | Gated operation |
|------|----------|-----------------|
| BashTool | `bash_execute` | Command and code execution |
| WriteFileTool | `write_file` | File creation and overwrite |
| EditFileTool | `edit_file` | File edits |
| ProcessTool | `process_manage` | Mutating process operations |
| SocialMessageTool | `social_message` | Sending messages |
| ImageGenerationTool | `image_generate` | Image generation |

Read-only variants such as contact listing and process polling are allowed without prompting when the active mode permits read operations.

## Approval Actions

An approval prompt can offer:

- **Allow**: approve this call once.
- **Allow for session**: create a rule in this chat.
- **Allow globally**: create a rule in the user `permissions.yaml`.
- **Reject**: deny the call, optionally with guidance for the agent.

The available actions are backend-owned and can vary by tool. Bash persistence uses an exact-command matcher; it does not approve the entire Bash tool. Other tools currently use a tool-wide matcher unless a narrower matcher is supplied.

The complete pending decision is stored with the chat. On resume, the backend validates the selected action ID against that stored contract and ignores client-supplied arguments when applying permission updates.

## Approval Lifecycle

```text
Agent issues a deferred tool call
        │
        ▼
   PermissionEngine evaluates it against rules, mode, and safety checks
        │
        ├── allow ──► tool executes
        ├── deny  ──► call is rejected, agent is told
        │
        ▼ ask
   Decision (with its offered actions) is persisted as a pending approval,
   and a tool_approval_request event is streamed to the frontend
        │
        ▼
   Frontend renders the offered actions; user selects one:
   Allow · Allow for session · Allow globally · Reject (+ optional feedback)
        │
        ▼
   Backend validates the selected action against the stored decision,
   creates the session/global rule if the action calls for one,
   resolves the deferred call, and the run resumes
```

The pending decision is stored with the chat, so the same prompt is restored after a page refresh. The backend only honors actions that were part of the stored decision and ignores client-supplied arguments, so a client cannot widen a rule beyond what was offered. A resume that targets an approval that is no longer pending — a duplicate submission, a retry, or a click after the run already finished — is ignored rather than treated as an error.

## Permission Modes

| Mode | Behavior |
|------|----------|
| `default` | Allow read-only commands; ask before workspace edits and other state-changing operations |
| `accept_edits` | Allow verified workspace edits; continue asking for dangerous or external actions |
| `plan` | Allow read-only exploration and writes only to the project `plan.md` |
| `auto` | Allow deterministic low-risk operations and classify unresolved requests with a separate security model |
| `strict_readonly` | Deny every non-read-only deferred operation |

Entering Plan mode stores the previous mode. The mode API can restore it with `{"restorePrevious": true}`.

Auto mode is not blanket approval. Explicit denies, shell safety checks, path restrictions, and normalized deny rules run before the classifier. Interactive classifier failures fall back to asking; headless classifier failures deny.

## Rule Scopes

- `once`: no persisted rule.
- `session`: stored in `ChatConfig.permission_rules`.
- `global`: stored in the user configuration directory's `permissions.yaml`.

Rules contain a tool, behavior (`allow`, `ask`, or `deny`), matcher, source, ID, and creation time. Supported matchers are:

- `all`
- `exact_input`
- `command_prefix`
- `path_prefix`
- `destination`

For matching rules, precedence is `deny`, then `ask`, then `allow`. More specific matchers win within the same behavior.

## APIs

```text
GET    /permissions?chat_id={chat_id}
POST   /permissions/rules
DELETE /permissions/rules/{rule_id}?destination=session|global&chat_id={chat_id}
GET    /chats/{chat_id}/permission-state
GET    /chats/{chat_id}/permission-mode
PUT    /chats/{chat_id}/permission-mode
```

Resume a suspended call through `/chat` or `/chat/send`:

```json
{
  "chat_id": "chat-id",
  "message": "",
  "resume_approvals": [
    {
      "request_id": "tool-call-id",
      "tool_call_id": "tool-call-id",
      "action_id": "allow_session",
      "feedback": "Optional user guidance"
    }
  ]
}
```

Legacy binary approval payloads remain accepted as allow-once or deny-only decisions. They cannot create remembered policies.

## Streaming Contract

The `tool_approval_request` custom event contains:

```json
{
  "approvalId": "tool-call-id",
  "toolCallId": "tool-call-id",
  "toolName": "bash_execute",
  "args": {"content": "npm test"},
  "decision": {
    "behavior": "ask",
    "reason": "Git commands require approval",
    "reasonCode": "shell_policy_ask",
    "risk": "high",
    "actions": []
  }
}
```

The frontend renders `decision.actions` in order, including feedback inputs and rule explanations declared by the backend. Pending contracts are persisted in `_pending_approvals` so the same prompt can be restored after refresh.

## Audit Trail

Permission evaluations and user resolutions are appended to `permission-audit.jsonl` in the user configuration directory. Entries include chat, run, tool-call, mode, decision, reason, user action, and classifier or matched-rule metadata.

Arguments are bounded and recursively sanitized. Sensitive keys and common inline credential forms are redacted. The append is offloaded to a worker thread so audit logging never blocks the streaming event loop.

## Adding Approval to a Tool

Set `requires_approval = True` on the tool class:

```python
class MyTool(BaseTool):
    tool_name = "my_tool"
    requires_approval = True
```

The registry wraps it as a pydantic-ai deferred tool. Add deterministic read-only or mode-specific behavior to `PermissionEngine` when needed; otherwise the default decision asks before execution.

Keep execution-time validation inside the tool. Permission approval answers whether an operation may proceed, while the tool must still validate paths, symlinks, arguments, and current external state immediately before execution.

## Headless Runs

Cron, heartbeat, goals, dream jobs, and subagents use Auto mode with a non-interactive profile. They do not use blanket `auto_approve_tools` behavior. A headless action that cannot be classified safely is denied.
