/**
 * useSubAgentActivity — what a sub-agent is doing right now, for its parent's
 * transcript.
 *
 * Every sub-agent already streams its whole run onto the shared event bus under
 * its own chat_id, but until now only the sidebar read it. That was fine for a
 * background child, whose parent keeps talking meanwhile — and wrong for a
 * blocking one, where the parent's turn is suspended inside the tool call and
 * the transcript shows nothing at all until the child returns. This turns those
 * chunks into a short live feed the call's own card can show inline, so the
 * wait reads as work rather than as a hang.
 *
 * Tool arguments are accumulated, not just names: "Run" says far less than
 * "Run — npm test", and the whole point is to make the wait legible. The phase
 * between tool calls is tracked for the same reason — a child that spends half
 * a minute reasoning before its next call would otherwise look stalled.
 *
 * Still deliberately shallow: the newest few calls, no output. The sidebar
 * keeps the full log.
 */
import { useEffect, useState } from 'react';
import { subscribeToBusChunks } from './useEventBus';
import { StreamEventType } from '../lib/streamEvents';
import { markSteerAbsorbed } from './useSubAgentSteer';

/** Custom event a run emits once it has taken an injected message. */
const ABSORBED_EVENT = 'agent_absorbed_message';

export interface SubAgentActivityEntry {
  toolCallId: string;
  toolName: string;
  /** Raw accumulated argument JSON; may be partial while still streaming. */
  args: string;
  /** False while the call is still running, so the card can pulse it. */
  done: boolean;
  /**
   * Set when a replayed start has left stale args in place: the next delta
   * replaces them instead of appending. Mirrors useAGUI's own handling of the
   * approve-and-resume sequence, where the backend replays TOOL_CALL_START and
   * its deltas for a call already seen. Appending there would build
   * `{"x":1}{"x":1}`, which no longer parses, and the feed would silently lose
   * the detail it exists to show.
   */
  argsReplayPending?: boolean;
}

/** What the child is doing when it is not inside a tool call. */
export type SubAgentPhase = 'thinking' | 'responding' | null;

export interface SubAgentActivity {
  /** Newest tool calls, oldest first. */
  entries: SubAgentActivityEntry[];
  phase: SubAgentPhase;
}

/** A feed, not a log — enough to show movement without growing the card. */
const MAX_ENTRIES = 5;

const EMPTY: SubAgentActivity = { entries: [], phase: null };

function eventsFromText(text: string): Record<string, unknown>[] {
  const events: Record<string, unknown>[] = [];
  for (const line of text.split('\n')) {
    if (!line.startsWith('data:')) continue;
    const body = line.slice('data:'.length).trim();
    if (!body) continue;
    try {
      const parsed: unknown = JSON.parse(body);
      if (parsed && typeof parsed === 'object') {
        events.push(parsed as Record<string, unknown>);
      }
    } catch {
      // A partial or non-JSON frame is not worth breaking the feed over.
    }
  }
  return events;
}

/**
 * Pull the JSON events out of one bus chunk.
 *
 * The bus documents `data` as a raw SSE string, and a chunk normally holds one
 * encoded event; `push_custom_event` puts a ("chunk", payload) tuple on the
 * same queue, which arrives as an array. Handle both rather than trusting one.
 */
export function parseChunk(raw: unknown): Record<string, unknown>[] {
  if (typeof raw === 'string') return eventsFromText(raw);
  // Each element is scanned on its own: joining them first would glue the
  // ("chunk", payload) tag onto the payload's leading "data:" line.
  if (Array.isArray(raw)) {
    return raw.flatMap((part) => (typeof part === 'string' ? eventsFromText(part) : []));
  }
  return [];
}

// Content events count as starts, not just the explicit ones: under the
// protocol family that emits REASONING_MESSAGE_CHUNK, that single event carries
// combined start-and-content and no start ever arrives. Waiting for one would
// leave the card blank for the whole of a child's reasoning — the gap this feed
// exists to close.
const THINKING_START: string[] = [
  StreamEventType.THINKING_START,
  StreamEventType.THINKING_TEXT_MESSAGE_START,
  StreamEventType.THINKING_TEXT_MESSAGE_CONTENT,
  StreamEventType.REASONING_START,
  StreamEventType.REASONING_MESSAGE_START,
  StreamEventType.REASONING_MESSAGE_CONTENT,
  StreamEventType.REASONING_MESSAGE_CHUNK,
];
const THINKING_END: string[] = [
  StreamEventType.THINKING_END,
  StreamEventType.THINKING_TEXT_MESSAGE_END,
  StreamEventType.REASONING_END,
  StreamEventType.REASONING_MESSAGE_END,
];

/**
 * Fold one stream event into the running activity state.
 *
 * Pure, so the reducer can be tested without a bus or a React tree.
 */
export function applyActivityEvent(
  state: SubAgentActivity,
  event: Record<string, unknown>
): SubAgentActivity {
  const type = typeof event.type === 'string' ? event.type : '';

  if (THINKING_START.includes(type)) return { ...state, phase: 'thinking' };
  if (THINKING_END.includes(type)) return { ...state, phase: null };
  if (type === StreamEventType.TEXT_MESSAGE_START) return { ...state, phase: 'responding' };
  if (type === StreamEventType.TEXT_MESSAGE_END) return { ...state, phase: null };
  if (type === StreamEventType.RUN_ERROR || type === StreamEventType.AGENT_FINISHED) {
    return { ...state, phase: null };
  }

  const toolCallId = typeof event.toolCallId === 'string' ? event.toolCallId : '';
  if (!toolCallId) return state;

  if (type === StreamEventType.TOOL_CALL_START) {
    const toolName = typeof event.toolCallName === 'string' ? event.toolCallName : '';
    const seen = state.entries.some((entry) => entry.toolCallId === toolCallId);
    // A tool call ends whatever the child was doing to produce it.
    if (seen) {
      // A replay after approval. Keep the args on screen, but arm the next
      // delta to replace rather than extend them.
      return {
        phase: null,
        entries: state.entries.map((entry) =>
          entry.toolCallId === toolCallId
            ? { ...entry, done: false, argsReplayPending: Boolean(entry.args) }
            : entry
        ),
      };
    }
    return {
      phase: null,
      entries: [...state.entries, { toolCallId, toolName, args: '', done: false }].slice(
        -MAX_ENTRIES
      ),
    };
  }

  if (type === StreamEventType.TOOL_CALL_ARGS) {
    const delta = typeof event.delta === 'string' ? event.delta : '';
    if (!delta) return state;
    return {
      ...state,
      entries: state.entries.map((entry) => {
        if (entry.toolCallId !== toolCallId) return entry;
        return entry.argsReplayPending
          ? { ...entry, args: delta, argsReplayPending: false }
          : { ...entry, args: entry.args + delta };
      }),
    };
  }

  // Only the result means finished. TOOL_CALL_END fires when the model has
  // finished writing the arguments, before the tool runs.
  if (type === StreamEventType.TOOL_CALL_RESULT) {
    let changed = false;
    const entries = state.entries.map((entry) => {
      if (entry.toolCallId !== toolCallId || entry.done) return entry;
      changed = true;
      return { ...entry, done: true, argsReplayPending: false };
    });
    return changed ? { ...state, entries } : state;
  }

  return state;
}

export function useSubAgentActivity(
  chatId: string | undefined,
  enabled: boolean
): SubAgentActivity {
  const [activity, setActivity] = useState<SubAgentActivity>(EMPTY);

  useEffect(() => {
    if (!chatId || !enabled) {
      setActivity((prev) => (prev === EMPTY ? prev : EMPTY));
      return;
    }
    return subscribeToBusChunks(chatId, (rawData) => {
      for (const event of parseChunk(rawData)) {
        if (event.type === StreamEventType.CUSTOM && event.name === ABSORBED_EVENT) {
          const value = event.value as { enqueue_id?: unknown } | null;
          const enqueueId = typeof value?.enqueue_id === 'string' ? value.enqueue_id : '';
          // Recorded against the redirect that was sent, not against this
          // component: whoever is showing that sub-agent should see it land.
          if (enqueueId) markSteerAbsorbed(enqueueId);
          continue;
        }
        setActivity((prev) => applyActivityEvent(prev, event));
      }
    });
  }, [chatId, enabled]);

  return activity;
}
