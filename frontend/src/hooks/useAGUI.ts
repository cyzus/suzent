/**
 * Custom React hook for AG-UI protocol streaming.
 *
 * Replaces Vercel AI SDK's useChat with a lightweight SSE client
 * that parses AG-UI events and builds up parts-based state.
 */
import { useState, useCallback, useRef } from 'react';

// ── Types ────────────────────────────────────────────────────────────

export interface AGUIPart {
  type: 'text' | 'reasoning' | 'tool';
  /** Text content (for text and reasoning parts) */
  text?: string;
  /** AG-UI message_id for correlating text deltas */
  messageId?: string;
  /** Tool call identifier */
  toolCallId?: string;
  /** Tool name */
  toolName?: string;
  /** Accumulated tool arguments (JSON string built from deltas) */
  args?: string;
  /** Tool result output */
  output?: string;
  /** Tool execution state */
  state?: 'running' | 'completed' | 'error' | 'approval-requested';
  /** HITL approval request identifier */
  approvalId?: string;
  /** Rich display data from CustomEvent (for future use) */
  displayData?: unknown;
}

export type AGUIStatus = 'idle' | 'submitted' | 'streaming' | 'error';

interface UseAGUIOptions {
  url: string;
  onFinish?: (parts: AGUIPart[]) => void;
  onCustomEvent?: (name: string, value: unknown) => void;
  onError?: (error: Error) => void;
}

interface UseAGUIReturn {
  parts: AGUIPart[];
  status: AGUIStatus;
  error: string | undefined;
  sendMessage: (body: Record<string, unknown>, opts?: { formData?: FormData }) => Promise<void>;
  stop: () => void;
  clearParts: () => void;
}

// ── SSE Parser ───────────────────────────────────────────────────────

interface ParsedSSEEvent {
  type: string;
  data: Record<string, unknown>;
}

/**
 * Parse AG-UI SSE chunks from a buffer.
 * AG-UI format: `data: {"type":"EVENT_TYPE",...}\n\n`
 */
function parseSSEBuffer(buffer: string): { events: ParsedSSEEvent[]; remainder: string } {
  const events: ParsedSSEEvent[] = [];
  const blocks = buffer.split('\n\n');
  const remainder = blocks.pop() || '';

  for (const block of blocks) {
    if (!block.trim()) continue;

    // Collect data lines (AG-UI uses single `data:` line per event)
    let dataStr = '';
    for (const line of block.split('\n')) {
      if (line.startsWith('data: ')) {
        dataStr += line.slice(6);
      } else if (line.startsWith('data:')) {
        dataStr += line.slice(5);
      }
    }

    if (!dataStr) continue;

    try {
      const parsed = JSON.parse(dataStr);
      if (parsed && typeof parsed.type === 'string') {
        events.push({ type: parsed.type, data: parsed });
      }
    } catch {
      // Skip malformed events
    }
  }

  return { events, remainder };
}

// ── Event Processor ──────────────────────────────────────────────────

function processEvent(
  event: ParsedSSEEvent,
  parts: AGUIPart[],
  onCustomEvent?: (name: string, value: unknown) => void,
): { parts: AGUIPart[]; error?: string } {
  const { type, data } = event;
  // Clone parts array for immutable update
  const next = [...parts];

  switch (type) {
    case 'TEXT_MESSAGE_START': {
      next.push({
        type: 'text',
        text: '',
        messageId: data.messageId as string,
      });
      break;
    }

    case 'TEXT_MESSAGE_CONTENT': {
      const msgId = data.messageId as string;
      const delta = (data.delta as string) || '';
      // Find last text part with matching messageId
      for (let i = next.length - 1; i >= 0; i--) {
        if (next[i].type === 'text' && next[i].messageId === msgId) {
          next[i] = { ...next[i], text: (next[i].text || '') + delta };
          break;
        }
      }
      break;
    }

    case 'TEXT_MESSAGE_END':
      // No-op: text already accumulated
      break;

    case 'THINKING_START':
    case 'THINKING_TEXT_MESSAGE_START': {
      // Only push a new reasoning part if the last one isn't an empty reasoning part
      const lastPart = next[next.length - 1];
      if (!lastPart || lastPart.type !== 'reasoning' || (lastPart.text && lastPart.text.length > 0)) {
        next.push({ type: 'reasoning', text: '' });
      }
      break;
    }

    case 'THINKING_TEXT_MESSAGE_CONTENT': {
      const delta = (data.delta as string) || '';
      for (let i = next.length - 1; i >= 0; i--) {
        if (next[i].type === 'reasoning') {
          next[i] = { ...next[i], text: (next[i].text || '') + delta };
          break;
        }
      }
      break;
    }

    case 'THINKING_TEXT_MESSAGE_END':
    case 'THINKING_END':
      // No-op
      break;

    case 'TOOL_CALL_START': {
      next.push({
        type: 'tool',
        toolCallId: data.toolCallId as string,
        toolName: data.toolCallName as string,
        args: '',
        state: 'running',
      });
      break;
    }

    case 'TOOL_CALL_ARGS': {
      const tcId = data.toolCallId as string;
      const delta = (data.delta as string) || '';
      for (let i = next.length - 1; i >= 0; i--) {
        if (next[i].type === 'tool' && next[i].toolCallId === tcId) {
          next[i] = { ...next[i], args: (next[i].args || '') + delta };
          break;
        }
      }
      break;
    }

    case 'TOOL_CALL_END':
      // No-op: args are complete
      break;

    case 'TOOL_CALL_RESULT': {
      const tcId = data.toolCallId as string;
      const content = (data.content as string) || '';
      for (let i = next.length - 1; i >= 0; i--) {
        if (next[i].type === 'tool' && next[i].toolCallId === tcId) {
          next[i] = { ...next[i], output: content, state: 'completed' };
          break;
        }
      }
      break;
    }

    case 'CUSTOM': {
      const name = data.name as string;
      const value = data.value;

      if (name === 'tool_approval_request') {
        const approval = value as Record<string, unknown>;
        const tcId = approval.toolCallId as string;
        const approvalId = approval.approvalId as string;
        let found = false;
        for (let i = next.length - 1; i >= 0; i--) {
          if (next[i].type === 'tool' && next[i].toolCallId === tcId) {
            next[i] = {
              ...next[i],
              state: 'approval-requested',
              approvalId,
              // Fill in name/args if not yet present (approval may arrive before tool_call_start)
              toolName: next[i].toolName || (approval.toolName as string) || 'unknown',
              args: next[i].args || (
                approval.args
                  ? (typeof approval.args === 'string' ? approval.args : JSON.stringify(approval.args, null, 2))
                  : ''
              ),
            };
            found = true;
            break;
          }
        }
        if (!found) {
          // Tool call part not yet seen; create one
          next.push({
            type: 'tool',
            toolCallId: tcId,
            toolName: (approval.toolName as string) || 'unknown',
            args: approval.args
              ? (typeof approval.args === 'string' ? approval.args as string : JSON.stringify(approval.args, null, 2))
              : '',
            state: 'approval-requested',
            approvalId,
          });
        }
      } else if (name === 'tool_display') {
        // Rich display data for a tool result
        const display = value as Record<string, unknown>;
        const tcId = display.toolCallId as string;
        for (let i = next.length - 1; i >= 0; i--) {
          if (next[i].type === 'tool' && next[i].toolCallId === tcId) {
            next[i] = { ...next[i], displayData: display };
            break;
          }
        }
      } else {
        // Forward other custom events (plan_refresh, usage_update, etc.)
        onCustomEvent?.(name, value);
      }
      break;
    }

    case 'RUN_ERROR': {
      return { parts: next, error: (data.message as string) || 'Unknown error' };
    }

    case 'RUN_STARTED':
    case 'RUN_FINISHED':
      // No-op: status managed by fetch lifecycle
      break;

    default:
      // Ignore unknown event types (forward-compatible)
      break;
  }

  return { parts: next };
}

// ── Hook ─────────────────────────────────────────────────────────────

export function useAGUI(options: UseAGUIOptions): UseAGUIReturn {
  const [parts, setParts] = useState<AGUIPart[]>([]);
  const [status, setStatus] = useState<AGUIStatus>('idle');
  const [error, setError] = useState<string | undefined>();
  const abortRef = useRef<AbortController | null>(null);
  // Keep a ref to latest parts so onFinish gets the final value
  const partsRef = useRef<AGUIPart[]>([]);
  partsRef.current = parts;

  // Stable refs for callbacks to avoid re-creating sendMessage
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const clearParts = useCallback(() => {
    setParts([]);
    partsRef.current = [];
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const sendMessage = useCallback(async (
    body: Record<string, unknown>,
    opts?: { formData?: FormData },
  ) => {
    const { url, onFinish, onCustomEvent, onError } = optionsRef.current;

    // Reset state
    setParts([]);
    partsRef.current = [];
    setError(undefined);
    setStatus('submitted');

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const fetchBody = opts?.formData || JSON.stringify(body);
      const headers: Record<string, string> = opts?.formData
        ? {} // Let browser set Content-Type for FormData
        : { 'Content-Type': 'application/json' };

      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: fetchBody,
        signal: controller.signal,
      });

      if (!response.ok) {
        const text = await response.text().catch(() => response.statusText);
        throw new Error(`HTTP ${response.status}: ${text}`);
      }

      if (!response.body) {
        throw new Error('Response body is null');
      }

      setStatus('streaming');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentParts: AGUIPart[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const { events, remainder } = parseSSEBuffer(buffer);
        buffer = remainder;

        for (const event of events) {
          const result = processEvent(event, currentParts, onCustomEvent);
          currentParts = result.parts;

          if (result.error) {
            setError(result.error);
            setStatus('error');
            setParts(currentParts);
            partsRef.current = currentParts;
            onError?.(new Error(result.error));
            return;
          }
        }

        if (events.length > 0) {
          setParts(currentParts);
          partsRef.current = currentParts;
        }
      }

      setStatus('idle');
      onFinish?.(currentParts);

    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        setStatus('idle');
        // Still call onFinish with whatever parts we have
        onFinish?.(partsRef.current);
      } else {
        const errorMsg = (err as Error).message;
        setError(errorMsg);
        setStatus('error');
        onError?.(err as Error);
      }
    }
  }, []);

  return { parts, status, error, sendMessage, stop, clearParts };
}
