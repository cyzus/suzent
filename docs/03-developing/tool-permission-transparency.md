# Tool Permission Transparency

## Goal

Make every deferred tool call explain how it was authorized without turning the
tool timeline into a security log.

The UI must distinguish these cases:

- allowed by deterministic policy;
- allowed by the Auto security classifier;
- escalated by the Auto security classifier for user review;
- denied by policy or classifier;
- executed because Full Access was enabled;
- approved or denied by the user after escalation.

Full Access must never look like a successful security review. Its label is
**Full Access · Not reviewed**.

## User Experience

### Collapsed tool call

Show one compact decision badge beside the tool status.

```text
✓ Bash                 AUTO ALLOWED · HIGH CONF
✓ Edit file            POLICY ALLOWED
● Deploy               REVIEW REQUIRED · HIGH
✓ Write file           FULL ACCESS · NOT REVIEWED
✕ Shell command        DENIED · CRITICAL
```

Badge colors are supplementary:

| Decision | Label | Color |
|---|---|---|
| Auto classifier allowed | `Auto allowed · {confidence} conf` | green |
| User review required | `Review required · {risk}` | amber |
| Policy allowed | `Policy allowed` | neutral |
| Full Access allowed | `Full Access · Not reviewed` | violet |
| Denied | `Denied · {risk}` | red |
| User approved escalation | `User approved` | blue |
| User denied escalation | `User denied` | red |

Do not show a collapsed badge for routine read-only policy decisions unless the
user has enabled a future verbose security view.

### Expanded tool call

Add a **Permission decision** section after the tool input and before its output.

```text
PERMISSION DECISION

Outcome       Auto allowed
Evaluator     Security reviewer
Reviewer      openai/gpt-4.1-mini
Confidence    High
Risk          Low
Categories    None
Reason        This is a local workspace edit requested by the user.
```

For Full Access:

```text
PERMISSION DECISION

Outcome       Allowed without review
Evaluator     Full Access
Reason        Approval prompts are disabled by the active permission mode.
```

For an escalation resolved by the user, retain both stages:

```text
REVIEW

Recommendation  Review required
Reason          The action modifies an external system.
Resolution      User allowed once
```

### Approval dock

The existing approval dock already shows risk and reason. Extend it with:

- evaluator (`Auto reviewer`, `Policy`, or `Rule`);
- classifier confidence;
- risk categories;
- reviewer model;
- a clear `AI recommendation` label when the decision came from the classifier.

The dock remains action-oriented. Detailed metadata should be one secondary
line and must not push the approval actions below the initial viewport.

## Decision Data Model

Add first-class provenance instead of asking the frontend to infer it from
`reasonCode`.

```ts
type PermissionDecisionSource =
  | 'policy'
  | 'rule'
  | 'auto_classifier'
  | 'full_access';

interface ToolPermissionDecision {
  toolCallId: string;
  behavior: 'allow' | 'ask' | 'deny';
  source: PermissionDecisionSource;
  reason: string;
  reasonCode: string;
  risk: 'safe' | 'low' | 'medium' | 'high' | 'critical';
  confidence?: 'low' | 'medium' | 'high';
  riskCategories?: string[];
  reviewerModel?: string;
}

interface ToolPermissionResolution {
  toolCallId: string;
  behavior: 'allow' | 'deny';
  source: 'user';
  actionId: string;
  scope: 'once' | 'session' | 'global';
}
```

`risk` is the engine's policy rating. `confidence` is the classifier's
self-reported confidence. The UI must not present confidence as a risk score.

## Streaming Contract

Emit a decision event for every deferred permission evaluation, including
automatic allows and denies:

```json
{
  "name": "tool_permission_decision",
  "value": {
    "toolCallId": "call-123",
    "behavior": "allow",
    "source": "auto_classifier",
    "reason": "This is a local workspace edit requested by the user.",
    "reasonCode": "auto_classifier_allow",
    "risk": "low",
    "confidence": "high",
    "riskCategories": [],
    "reviewerModel": "openai/gpt-4.1-mini"
  }
}
```

Continue emitting `tool_approval_request` for `ask` decisions because it owns
the available approval actions. Both events reference the same `toolCallId`.

After the user acts, emit:

```json
{
  "name": "tool_permission_resolution",
  "value": {
    "toolCallId": "call-123",
    "behavior": "allow",
    "source": "user",
    "actionId": "allow_once",
    "scope": "once"
  }
}
```

Event order:

```text
TOOL_CALL_START
tool_permission_decision
├─ allow/deny -> tool continues or returns denial
└─ ask       -> tool_approval_request
                └─ tool_permission_resolution
TOOL_CALL_RESULT
```

Older clients safely ignore the new custom events. New clients continue to work
with older servers because all new fields and events are optional.

## Backend Changes

1. Add `source` to `PermissionDecision`.
2. Include the selected classifier model ID in Auto decision metadata.
3. Emit `tool_permission_decision` immediately after permission evaluation and
   audit recording.
4. Emit `tool_permission_resolution` when an approval response is accepted.
5. Keep the existing audit log as the authoritative diagnostic record.
6. Sanitize bounded display metadata before streaming or persistence.

Recommended source mapping:

| Reason family | Source |
|---|---|
| `auto_classifier_*` | `auto_classifier` |
| `normalized_rule_*`, `explicit_tool_*` | `rule` |
| `mode_full_access` | `full_access` |
| shell, filesystem, read-only and validation decisions | `policy` |

The engine should set the source directly. This table is for migration and
tests, not frontend inference.

## Frontend Changes

Extend `AGUIPart` with optional fields:

```ts
permissionDecision?: ToolPermissionDecision;
permissionResolution?: ToolPermissionResolution;
```

When either custom event arrives:

1. locate the tool part by `toolCallId`;
2. merge the decision or resolution without changing execution state;
3. retain the metadata when the part transitions from running to completed;
4. render the compact badge in the tool header;
5. render full details only in the expanded tool view.

The approval dock should continue reading the approval contract from
`part.permission`; it may use `part.permissionDecision` for provenance details.

## Persistence

Permission display metadata must survive navigation and reload.

For the first implementation, persist the optional decision and resolution
fields with the structured frontend tool parts using the existing message
persistence path. The backend audit log remains the fallback diagnostic record.

Do not store completed decisions in `_pending_approvals`; that collection is
only for unresolved approval contracts.

If structured tool parts cannot be reliably restored from all interfaces, add a
bounded per-message permission-decision map rather than growing chat config
indefinitely.

## Privacy and Safety

- Never include API keys, authorization headers, environment secrets, or raw
  credentials in decision metadata.
- Reviewer reasons are untrusted model output and must render as plain text.
- Truncate reasons for the collapsed tooltip; show the bounded full reason only
  in the expanded view.
- Do not claim an action was reviewed when it was allowed by Full Access.
- Do not let display metadata affect the actual permission result.

## Rollout

### Phase 1

- Add decision and resolution events.
- Store them on tool parts.
- Add collapsed badges and the expanded decision section.
- Enhance the approval dock with Auto confidence and categories.

### Phase 2

- Add a dedicated Security Reviewer model role.
- Add an optional permission-decision history view backed by the audit log.
- Add a verbose toggle for deterministic read-only decisions.

## Acceptance Criteria

- An Auto-allowed tool call shows its classifier confidence and reason.
- An escalated call shows the recommendation before the user acts.
- A resolved escalation shows both the recommendation and user resolution.
- A Full Access call is labeled `Not reviewed`.
- Explicit policy/rule allows are distinguishable from classifier allows.
- Metadata remains attached after tool completion and chat reload.
- Old clients and old persisted chats continue to render without errors.
- No permission metadata can approve, deny, or widen a tool call by itself.
