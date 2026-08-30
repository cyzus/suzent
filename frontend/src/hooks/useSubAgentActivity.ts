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
 * Deliberately shallow: the newest few tool calls, no arguments, no output. The
 * sidebar still owns the full log; this only has to answer "is it moving?".
 */
import { useEffect, useState } from 'react';
import { subscribeToBusChunks } from './useEventBus';
import { StreamEventType } from '../lib/streamEvents';

/** Custom event a run emits once it has taken an injected message. */
const ABSORBED_EVENT = 'agent_absorbed_message';

export interface SubAgentActivityEntry {
  toolCallId: string;
  toolName: string;
  /** False while the call is still running, so the card can pulse it. */
  done: boolean;
}

/** A feed, not a log — enough to show movement without growing the card. */
const MAX_ENTRIES = 5;

/**
 * Pull the JSON events out of one bus chunk.
 *
 * The bus documents `data` as a raw SSE string, and a chunk normally holds one
 * encoded event; `push_custom_event` puts a ("chunk", payload) tuple on the
 * same queue, which arrives as an array. Handle both rather than trusting one.
 */
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

export function parseChunk(raw: unknown): Record<string, unknown>[] {
  if (typeof raw === 'string') return eventsFromText(raw);
  // Each element is scanned on its own: joining them first would glue the
  // ("chunk", payload) tag onto the payload's leading "data:" line.
  if (Array.isArray(raw)) {
    return raw.flatMap((part) => (typeof part === 'string' ? eventsFromText(part) : []));
  }
  return [];
}

export interface SubAgentActivity {
  /** Newest tool calls, oldest first. */
  entries: SubAgentActivityEntry[];
  /**
   * Enqueue ids the run has actually taken into its history. A redirect is
   * "sent" the moment the POST returns, but only picked up at the child's next
   * model request — often a whole tool call later — and showing those as the
   * same thing would be a lie the user cannot check.
   */
  absorbed: Set<string>;
}

export function useSubAgentActivity(
  chatId: string | undefined,
  enabled: boolean
): SubAgentActivity {
  const [entries, setEntries] = useState<SubAgentActivityEntry[]>([]);
  const [absorbed, setAbsorbed] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    if (!chatId || !enabled) {
      setEntries((prev) => (prev.length ? [] : prev));
      setAbsorbed((prev) => (prev.size ? new Set() : prev));
      return;
    }
    return subscribeToBusChunks(chatId, (rawData) => {
      for (const event of parseChunk(rawData)) {
        const type = event.type;

        if (type === StreamEventType.CUSTOM && event.name === ABSORBED_EVENT) {
          const value = event.value as { enqueue_id?: unknown } | null;
          const enqueueId = typeof value?.enqueue_id === 'string' ? value.enqueue_id : '';
          if (enqueueId) {
            setAbsorbed((prev) => {
              if (prev.has(enqueueId)) return prev;
              const next = new Set(prev);
              next.add(enqueueId);
              return next;
            });
          }
          continue;
        }

        const toolCallId = typeof event.toolCallId === 'string' ? event.toolCallId : '';
        if (!toolCallId) continue;

        if (type === StreamEventType.TOOL_CALL_START) {
          const toolName = typeof event.toolCallName === 'string' ? event.toolCallName : '';
          setEntries((prev) => {
            if (prev.some((entry) => entry.toolCallId === toolCallId)) return prev;
            return [...prev, { toolCallId, toolName, done: false }].slice(-MAX_ENTRIES);
          });
        } else if (type === StreamEventType.TOOL_CALL_RESULT) {
          // Only the result means finished. TOOL_CALL_END fires when the
          // model has finished writing the arguments, before the tool runs.
          setEntries((prev) => {
            let changed = false;
            const next = prev.map((entry) => {
              if (entry.toolCallId !== toolCallId || entry.done) return entry;
              changed = true;
              return { ...entry, done: true };
            });
            return changed ? next : prev;
          });
        }
      }
    });
  }, [chatId, enabled]);

  return { entries, absorbed };
}
