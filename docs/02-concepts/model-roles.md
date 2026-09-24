# Model roles

Settings → Model Roles assigns models by task. An empty task role inherits the
nearest configured parent, including its ordered model list:

```text
primary
├── cheap
│   ├── title
│   ├── memory_extraction
│   └── decision
│       ├── goal_judge
│       └── permission_review
└── dream
```

- `title`: conversation titles.
- `memory_extraction`: extract durable facts from conversations.
- `decision`: shared default for goal completion and automatic permission review.
- `goal_judge` / `permission_review`: optional overrides under Advanced decision roles.
- `dream`: memory consolidation and knowledge-vault lint passes.

Explicit assignments replace inheritance; clearing a task role restores it.
Inheritance selects configuration, not a second retry path after a model fails.
Individual callers retain their existing retry behavior. Context compaction still
uses the conversation model.

Existing `cheap` configurations continue to serve title, extraction, and decision
tasks. A saved role assignment takes precedence over YAML role defaults. The legacy
`memory_consolidation_model` setting supplies the initial Dream assignment when
no explicit `dream` role exists; Dream otherwise inherits Primary. Remove the legacy
setting when fully migrating to role settings, so it cannot seed the role again on
restart after the role is cleared.

Vision retains its capability-filtered inheritance from Primary. Embedding, image
generation, and TTS require explicit specialist models and have no parent role.
