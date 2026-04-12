/**
 * Stream event type constants for AG-UI protocol.
 *
 * Matches the Python definitions in src/suzent/core/stream_events.py
 * to ensure consistency between backend and frontend.
 */

/**
 * Standard AG-UI stream event types.
 */
export enum StreamEventType {
  // Text message events
  TEXT_MESSAGE_START = 'TEXT_MESSAGE_START',
  TEXT_MESSAGE_CONTENT = 'TEXT_MESSAGE_CONTENT',
  TEXT_MESSAGE_END = 'TEXT_MESSAGE_END',

  // Thinking/reasoning events
  THINKING_START = 'THINKING_START',
  THINKING_TEXT_MESSAGE_START = 'THINKING_TEXT_MESSAGE_START',
  THINKING_TEXT_MESSAGE_CONTENT = 'THINKING_TEXT_MESSAGE_CONTENT',
  THINKING_TEXT_MESSAGE_END = 'THINKING_TEXT_MESSAGE_END',
  THINKING_END = 'THINKING_END',

  // Tool call events
  TOOL_CALL_START = 'TOOL_CALL_START',
  TOOL_CALL_ARGS = 'TOOL_CALL_ARGS',
  TOOL_CALL_END = 'TOOL_CALL_END',
  TOOL_CALL_RESULT = 'TOOL_CALL_RESULT',

  // Custom events
  CUSTOM = 'CUSTOM',
  CUSTOM_EVENT = 'CUSTOM_EVENT',

  // Error and completion events
  RUN_ERROR = 'RUN_ERROR',
  RUN_STARTED = 'RUN_STARTED',
  AGENT_FINISHED = 'AGENT_FINISHED',
}

/**
 * Custom event names used by Suzent.
 */
export enum CustomEventName {
  TOOL_APPROVAL_REQUEST = 'tool_approval_request',
  TOOL_DISPLAY = 'tool_display',
  PLAN_REFRESH = 'plan_refresh',
  USAGE_UPDATE = 'usage_update',
  // Sub-agent lifecycle events (S2O Phase 3)
  SUBAGENT_SPAWNED = 'subagent_spawned',
  SUBAGENT_PROGRESS = 'subagent_progress',
  SUBAGENT_COMPLETED = 'subagent_completed',
  SUBAGENT_FAILED = 'subagent_failed',
}

// ─── Sub-agent event payloads ──────────────────────────────────────────────

export interface SubAgentSpawnedPayload {
  task_id: string;
  chat_id: string;
  description: string;
  tools_allowed: string[];
}

export interface SubAgentProgressPayload {
  task_id: string;
  step_summary: string;
}

export interface SubAgentCompletedPayload {
  task_id: string;
  result_summary: string;
}

export interface SubAgentFailedPayload {
  task_id: string;
  error: string;
}

/**
 * Type guard: Check if event is a text message event.
 */
export function isTextEvent(eventType: string): boolean {
  return [
    StreamEventType.TEXT_MESSAGE_START,
    StreamEventType.TEXT_MESSAGE_CONTENT,
    StreamEventType.TEXT_MESSAGE_END,
  ].includes(eventType as StreamEventType);
}

/**
 * Type guard: Check if event is a thinking event.
 */
export function isThinkingEvent(eventType: string): boolean {
  return [
    StreamEventType.THINKING_START,
    StreamEventType.THINKING_TEXT_MESSAGE_START,
    StreamEventType.THINKING_TEXT_MESSAGE_CONTENT,
    StreamEventType.THINKING_TEXT_MESSAGE_END,
    StreamEventType.THINKING_END,
  ].includes(eventType as StreamEventType);
}

/**
 * Type guard: Check if event is a tool call event.
 */
export function isToolEvent(eventType: string): boolean {
  return [
    StreamEventType.TOOL_CALL_START,
    StreamEventType.TOOL_CALL_ARGS,
    StreamEventType.TOOL_CALL_END,
    StreamEventType.TOOL_CALL_RESULT,
  ].includes(eventType as StreamEventType);
}
