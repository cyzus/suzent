# Pydantic AI native capability migration

This note records which Pydantic AI v2 capabilities Suzent uses directly and
which migrations should wait until their surrounding product behavior can move
with them.

## Migrated now

- **Streaming lifecycle:** `Agent.run_stream_events()` is entered as an async
  context manager. This matches the v2 API and guarantees provider streams are
  closed when a run completes, times out, or is cancelled.
- **History processing:** context compaction is registered through
  `ProcessHistory`.
- **Tool discovery:** Suzent tools that are not explicitly equipped are
  registered with `defer_loading=True` and discovered through `ToolSearch`.
  Anthropic and OpenAI Responses models can use provider-native discovery;
  other providers transparently use Pydantic AI's local keyword fallback.
  Existing approval flags remain attached to the discovered tool.

## Keep on the current implementation for now

- **Skills as deferred capabilities:** promising, but a skill carries dynamic
  instructions, assets, enablement state, and session guidance rather than only
  a function schema. Migrate after those lifecycle rules have capability-level
  tests.
- **High-level MCP capability:** current `MCPToolset` integration owns
  credentials, prefixes, connection probing, and UI configuration. A migration
  must preserve those trust boundaries and server lifecycle behavior.
- **Native WebSearch and WebFetch:** Suzent's tools populate its citation
  manager and frontend source events. Native provider results need a common
  citation/event adapter before replacement.
- **Native ImageGeneration:** the current tool includes approval, file
  persistence, and frontend media behavior. Provider-native generation alone
  is not feature-equivalent.
- **Provider compaction / harness compaction:** Suzent persists checkpoints and
  partially completed tool batches. Adopt only after compaction is proven to
  preserve replayable tool-call pairs across every supported provider.
- **ThreadExecutor:** this offers limited value until blocking synchronous
  hooks or tools are identified in profiling.

## Migration criteria

A deferred item is ready when it preserves cross-provider fallback, permission
policy, persisted message replay, cancellation, frontend events, and the
existing integration tests. Provider-native support should be an optimization,
not a requirement for using the capability.
