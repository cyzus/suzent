/**
 * Custom React hook for AG-UI protocol streaming.
 *
 * Replaces Vercel AI SDK's useChat with a lightweight SSE client
 * that parses AG-UI events and builds up parts-based state.
 */
import { useState, useCallback, useRef } from 'react';
import type { A2UISurface } from '../types/a2ui';
import type { AGUIPart, ApprovalRememberScope } from '../types/agui';

// ── Types ────────────────────────────────────────────────────────────
export type AGUIStatus = 'idle' | 'submitted' | 'streaming' | 'error';
export type { AGUIPart, ApprovalRememberScope };

interface UseAGUIOptions {
  url: string;
  onFinish?: (parts: AGUIPart[]) => void;
  onCustomEvent?: (name: string, value: unknown) => void;
  onMarkDeferred?: (surfaceId: string) => void;
  onError?: (error: Error, parts: AGUIPart[]) => void;
}

interface UseAGUIReturn {
  parts: AGUIPart[];
  status: AGUIStatus;
  error: string | undefined;
  sendMessage: (body: Record<string, unknown>, opts?: { formData?: FormData; urlOverride?: string; onStreamStart?: () => void; seedParts?: AGUIPart[] }) => Promise<boolean>;
  /** Resume a stream after approval without clearing existing parts */
  resumeStream: (body: Record<string, unknown>) => Promise<void>;
  /** Interrupt the current stream and redirect the agent with a new message */
  steerStream: (body: Record<string, unknown>) => Promise<void>;
  stop: () => void;
  /** Abort the active stream without triggering onFinish (used on chat switch) */
  stopSilently: () => void;
  /** Read the current parts synchronously (e.g. to snapshot before switching chats) */
  getParts: () => AGUIPart[];
  clearParts: () => void;
  /**
   * Restore saved parts directly (e.g. after a page refresh) without starting a
   * new stream. Used to re-display pending tool-approval dialogs from sessionStorage.
   */
  restorePartsFromSeed: (seed: AGUIPart[]) => void;
  /** Remove an inline A2UI surface part by surface id (e.g. after ask_question is answered) */
  removeInlineSurface: (surfaceId: string) => void;
  /** Optimistically resolve a tool approval (instantly updates UI before backend responds) */
  resolveApproval: (approvalId: string, approved: boolean) => void;
  /** Number of tool approvals still awaiting user decision */
  pendingApprovalCount: number;
  /** Record a user's approval decision; returns true when all pending approvals are decided */
  addApprovalDecision: (
    approvalId: string,
    toolCallId: string,
    approved: boolean,
    remember?: ApprovalRememberScope,
    toolName?: string,
    args?: Record<string, unknown> | null,
  ) => boolean;
  /** Get accumulated approval decisions and clear the buffer */
  consumeApprovalDecisions: () => Array<{
    approvalId: string;
    toolCallId: string;
    approved: boolean;
    remember?: ApprovalRememberScope;
    toolName?: string;
    args?: Record<string, unknown> | null;
  }>;
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

function stringifyContent(raw: unknown): string {
  if (typeof raw === 'string') return raw;
  if (raw == null) return '';
  try {
    return JSON.stringify(raw, null, 2);
  } catch {
    // Fallback for circular or non-serializable values.
    return String(raw);
  }
}

function processEvent(
  event: ParsedSSEEvent,
  parts: AGUIPart[],
  onCustomEvent?: (name: string, value: unknown) => void,
  onMarkDeferred?: (surfaceId: string) => void,
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
      const tcStartId = data.toolCallId as string;
      // On resume after approval the backend replays TOOL_CALL_START for the
      // same toolCallId.  Update the existing part in-place so we don't create
      // a duplicate that ends up receiving the result while the original stays
      // in a perpetual "running" state with no output.
      let existingStartIdx = -1;
      for (let i = next.length - 1; i >= 0; i--) {
        if (next[i].type === 'tool' && next[i].toolCallId === tcStartId) {
          existingStartIdx = i;
          break;
        }
      }
      if (existingStartIdx >= 0) {
        const existingOutput = next[existingStartIdx].output;
        next[existingStartIdx] = {
          ...next[existingStartIdx],
          // Keep existing args visible during approval/resume. If the backend
          // replays TOOL_CALL_ARGS, the first replay delta replaces these args
          // below; if it only sends the result, file renderers still have path/content.
          args: next[existingStartIdx].args || '',
          argsReplayPending: Boolean(next[existingStartIdx].args),
          state: 'running',
          // Keep any already-received output to avoid losing it on replayed starts.
          output: existingOutput,
          approvalId: undefined,
        };
      } else {
        next.push({
          type: 'tool',
          toolCallId: tcStartId,
          toolName: data.toolCallName as string,
          args: '',
          state: 'running',
        });
      }
      break;
    }

    case 'TOOL_CALL_ARGS': {
      const tcId = data.toolCallId as string;
      const delta = (data.delta as string) || '';
      for (let i = next.length - 1; i >= 0; i--) {
        if (next[i].type === 'tool' && next[i].toolCallId === tcId) {
          next[i] = next[i].argsReplayPending
            ? { ...next[i], args: delta, argsReplayPending: false }
            : { ...next[i], args: (next[i].args || '') + delta };
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
      const raw = data.content ?? data.output ?? data.result ?? '';
      const content = stringifyContent(raw);
      for (let i = next.length - 1; i >= 0; i--) {
        if (next[i].type === 'tool' && next[i].toolCallId === tcId) {
          next[i] = { ...next[i], output: content, state: 'completed', argsReplayPending: false };
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
      } else if (name === 'tool_approval_result') {
        const resultData = value as Record<string, unknown>;
        const tcId = resultData.toolCallId as string;
        const toolName = (resultData.toolName as string) || 'unknown';
        const raw = resultData.output ?? resultData.content ?? resultData.result ?? '';
        const output = stringifyContent(raw);
        let found = false;
        for (let i = next.length - 1; i >= 0; i--) {
          if (next[i].type === 'tool' && next[i].toolCallId === tcId) {
            next[i] = {
              ...next[i],
              state: resultData.status === 'executed' ? 'completed' : 'error',
              output,
              argsReplayPending: false,
              approvalId: undefined // clear approval badge
            };
            found = true;
            break;
          }
        }
        if (!found) {
          // Fallback: attach to the most recent unfinished tool of the same name.
          // The toolCallId can differ between the streamed TOOL_CALL_START and the
          // deferred recovery result (auto-approved bash runs through the deferred
          // path), so match by name on any tool still awaiting a result —
          // 'approval-requested' OR 'running' with no output yet.
          for (let i = next.length - 1; i >= 0; i--) {
            const p = next[i];
            if (
              p.type === 'tool' &&
              (p.toolName || 'unknown') === toolName &&
              (p.state === 'approval-requested' ||
                (p.state === 'running' && !p.output))
            ) {
              next[i] = {
                ...p,
                toolCallId: p.toolCallId || tcId,
                state: resultData.status === 'executed' ? 'completed' : 'error',
                output,
                argsReplayPending: false,
                approvalId: undefined,
              };
              found = true;
              break;
            }
          }
        }
        if (!found) {
          // Recovery event may arrive even when the original tool part is missing.
          next.push({
            type: 'tool',
            toolCallId: tcId,
            toolName,
            output,
            state: resultData.status === 'executed' ? 'completed' : 'error',
            approvalId: undefined,
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
      } else if (name === 'a2ui.render') {
        const surface = value as A2UISurface & { target?: string; deferred?: boolean };
        if (surface?.target === 'inline') {
          // Inline: embed as a part inside the current message
          next.push({ type: 'a2ui', surface });
          if (surface.deferred && surface.id) {
            onMarkDeferred?.(surface.id as string);
          }
        } else {
          // Canvas: forward to ChatWindow's onCustomEvent handler
          onCustomEvent?.(name, value);
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
  // Set to true while steerStream is running so abort-triggered onFinish is suppressed
  const isSteeringRef = useRef(false);
  // Set to true by stopSilently() so the next abort skips onFinish entirely.
  // Used when abandoning a live background stream on chat switch — the backend
  // persists the content, so the frontend must NOT addMessage (which would
  // misroute the parts to whatever chat is now being viewed).
  const suppressFinishRef = useRef(false);
  // Keep a ref to latest parts so onFinish gets the final value
  const partsRef = useRef<AGUIPart[]>([]);
  partsRef.current = parts;

  // Pending approval tracking
  const [pendingApprovalCount, setPendingApprovalCount] = useState(0);
  const pendingApprovalCountRef = useRef(0);
  const approvalDecisionsRef = useRef<Array<{
    approvalId: string;
    toolCallId: string;
    approved: boolean;
    remember?: ApprovalRememberScope;
    toolName?: string;
    args?: Record<string, unknown> | null;
  }>>([]);

  // Stable refs for callbacks to avoid re-creating sendMessage
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const clearParts = useCallback(() => {
    setParts([]);
    partsRef.current = [];
  }, []);

  const setPendingApprovalCountSync = useCallback((count: number) => {
    pendingApprovalCountRef.current = count;
    setPendingApprovalCount(prev => (prev === count ? prev : count));
  }, []);

  const resetApprovalTracking = useCallback(() => {
    setPendingApprovalCountSync(0);
    approvalDecisionsRef.current = [];
  }, [setPendingApprovalCountSync]);

  const removeInlineSurface = useCallback((surfaceId: string) => {
    setParts(prev => {
      const next = prev.filter(
        p => !(p.type === 'a2ui' && (p.surface as A2UISurface)?.id === surfaceId)
      );
      partsRef.current = next;
      return next;
    });
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  // Abort the active stream WITHOUT triggering onFinish. Used when navigating
  // away from a live background stream — the backend keeps producing and
  // persists the result, so the frontend discards its transient parts instead
  // of finalizing them into the (now different) currently-viewed chat.
  const stopSilently = useCallback(() => {
    suppressFinishRef.current = true;
    abortRef.current?.abort();
  }, []);

  const getParts = useCallback(() => partsRef.current, []);

  const restorePartsFromSeed = useCallback((seed: AGUIPart[]) => {
    setParts(seed);
    partsRef.current = seed;
    setStatus('idle');
    const approvalCount = seed.filter(p => p.type === 'tool' && p.state === 'approval-requested').length;
    setPendingApprovalCountSync(approvalCount);
  }, [setPendingApprovalCountSync]);

  // Optimistically update a tool part's state when user approves/denies
  // so buttons disappear instantly (no waiting for backend round-trip)
  const resolveApproval = useCallback((approvalId: string, approved: boolean) => {
    setParts(prev => {
      const next = prev.map(p => {
        if (p.type === 'tool' && p.approvalId === approvalId) {
          return {
            ...p,
            state: approved ? 'running' as const : 'error' as const,
            approvalId: undefined,
          };
        }
        return p;
      });
      partsRef.current = next;
      return next;
    });
  }, []);

  // Track pending approval count from parts
  const addApprovalDecision = useCallback((
    approvalId: string,
    toolCallId: string,
    approved: boolean,
    remember?: ApprovalRememberScope,
    toolName?: string,
    args?: Record<string, unknown> | null,
  ): boolean => {
    const nextDecision = { approvalId, toolCallId, approved, remember, toolName, args };
    const existingIdx = approvalDecisionsRef.current.findIndex(
      d => d.approvalId === approvalId
    );
    if (existingIdx >= 0) {
      approvalDecisionsRef.current[existingIdx] = nextDecision;
    } else {
      approvalDecisionsRef.current.push(nextDecision);
    }
    const requiredDecisions = pendingApprovalCountRef.current;
    return requiredDecisions > 0 && approvalDecisionsRef.current.length >= requiredDecisions;
  }, []);

  const consumeApprovalDecisions = useCallback(() => {
    const decisions = [...approvalDecisionsRef.current];
    resetApprovalTracking();
    return decisions;
  }, [resetApprovalTracking]);

  /**
   * Resume a stream after tool approval without clearing existing parts.
   * Merges new events (tool results, text) into the existing parts array.
   */
  const resumeStream = useCallback(async (body: Record<string, unknown>) => {
    const { url, onFinish, onCustomEvent, onMarkDeferred, onError } = optionsRef.current;

    // DON'T clear parts — keep existing tool parts from first stream
    setError(undefined);
    setStatus('streaming');
    resetApprovalTracking();

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok) {
        const text = await response.text().catch(() => response.statusText);
        throw new Error(`HTTP ${response.status}: ${text}`);
      }

      if (!response.body) {
        throw new Error('Response body is null');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      // Start from existing parts instead of empty array
      let currentParts = [...partsRef.current];
      const pendingApprovalIds = new Set<string>();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // Sync with any out-of-band part mutations (e.g. removeInlineSurface)
        currentParts = [...partsRef.current];

        buffer += decoder.decode(value, { stream: true });
        const { events, remainder } = parseSSEBuffer(buffer);
        buffer = remainder;

        for (const event of events) {
          // Track unique approval requests in this paused stream segment.
          if (event.type === 'CUSTOM' && (event.data.name as string) === 'tool_approval_request') {
            const approval = event.data.value as Record<string, unknown> | undefined;
            const approvalId = approval?.approvalId;
            if (typeof approvalId === 'string' && approvalId.length > 0) {
              pendingApprovalIds.add(approvalId);
            }
          }
          const result = processEvent(event, currentParts, onCustomEvent, onMarkDeferred);
          currentParts = result.parts;

          if (result.error) {
            setError(result.error);
            setStatus('error');
            setParts(currentParts);
            partsRef.current = currentParts;
            onError?.(new Error(result.error), currentParts);
            return;
          }
        }

        if (events.length > 0) {
          setParts(currentParts);
          partsRef.current = currentParts;
          setPendingApprovalCountSync(pendingApprovalIds.size);
        }
      }

      setStatus('idle');
      onFinish?.(currentParts);

    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        // If the abort was triggered by steerStream, do nothing here —
        // steerStream owns the status and will call onFinish when done.
        if (!isSteeringRef.current) {
          setStatus('idle');
          onFinish?.(partsRef.current);
        }
      } else {
        const errorMsg = (err as Error).message;
        setError(errorMsg);
        setStatus('error');
        onError?.(err as Error, partsRef.current);
      }
    }
  }, []);

  /**
   * Interrupt the current stream and redirect the agent.
   * Aborts the active fetch, inserts a visual divider, then starts a new
   * stream from /chat/steer preserving existing parts.
   */
  const steerStream = useCallback(async (body: Record<string, unknown>) => {
    const { onFinish, onCustomEvent, onMarkDeferred, onError } = optionsRef.current;
    // Derive steer URL from the base chat URL
    const steerUrl = optionsRef.current.url.replace(/\/chat$/, '/chat/steer');
    const previousParts = [...partsRef.current];

    // Mark any pending approvals as cancelled before aborting,
    // so they won't show approval buttons after being saved to the store
    const hasApprovals = partsRef.current.some(
      p => p.type === 'tool' && p.state === 'approval-requested'
    );
    if (hasApprovals) {
      const resolved = partsRef.current.map(p =>
        p.type === 'tool' && p.state === 'approval-requested'
          ? { ...p, state: 'error' as const, approvalId: undefined }
          : p
      );
      partsRef.current = resolved;
      setParts(resolved);
    }

    // 1. Abort the current fetch — set flag so the AbortError handler is a no-op
    isSteeringRef.current = true;
    abortRef.current?.abort();

    // Keep existing parts visible until the steer response is confirmed.
    // This prevents a blank UI when steering fails before the first chunk.
    setError(undefined);
    setStatus('submitted');
    resetApprovalTracking();

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch(steerUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok) {
        const text = await response.text().catch(() => response.statusText);
        throw new Error(`HTTP ${response.status}: ${text}`);
      }

      if (!response.body) {
        throw new Error('Response body is null');
      }

      // Steer stream is confirmed active; start with a fresh transient message.
      setParts([]);
      partsRef.current = [];
      setStatus('streaming');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentParts = [...partsRef.current];
      const pendingApprovalIds = new Set<string>();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // Sync with any out-of-band part mutations (e.g. removeInlineSurface)
        currentParts = [...partsRef.current];

        buffer += decoder.decode(value, { stream: true });
        const { events, remainder } = parseSSEBuffer(buffer);
        buffer = remainder;

        for (const event of events) {
          if (event.type === 'CUSTOM' && (event.data.name as string) === 'tool_approval_request') {
            const approval = event.data.value as Record<string, unknown> | undefined;
            const approvalId = approval?.approvalId;
            if (typeof approvalId === 'string' && approvalId.length > 0) {
              pendingApprovalIds.add(approvalId);
            }
          }
          const result = processEvent(event, currentParts, onCustomEvent, onMarkDeferred);
          currentParts = result.parts;

          if (result.error) {
            isSteeringRef.current = false;
            setError(result.error);
            setStatus('error');
            setParts(currentParts);
            partsRef.current = currentParts;
            onError?.(new Error(result.error), currentParts);
            return;
          }
        }

        if (events.length > 0) {
          setParts(currentParts);
          partsRef.current = currentParts;
          setPendingApprovalCountSync(pendingApprovalIds.size);
        }
      }

      isSteeringRef.current = false;
      setStatus('idle');
      onFinish?.(currentParts);

    } catch (err) {
      isSteeringRef.current = false;
      if ((err as Error).name === 'AbortError') {
        setStatus('idle');
        onFinish?.(partsRef.current);
      } else {
        // Restore previous parts if steer failed before the replacement stream started.
        if (partsRef.current.length === 0 && previousParts.length > 0) {
          partsRef.current = previousParts;
          setParts(previousParts);
        }
        const errorMsg = (err as Error).message;
        setError(errorMsg);
        setStatus('error');
        onError?.(err as Error, partsRef.current);
      }
    }
  }, []);

  const sendMessage = useCallback(async (
    body: Record<string, unknown>,
    opts?: { formData?: FormData; urlOverride?: string; onStreamStart?: () => void; seedParts?: AGUIPart[] },
  ): Promise<boolean> => {
    const { url, onFinish, onCustomEvent, onMarkDeferred, onError } = optionsRef.current;
    const targetUrl = opts?.urlOverride ?? url;
    // For live-stream probes (urlOverride) we defer the state reset until we know
    // there is actually an active stream — this prevents every 204 probe from
    // clearing streaming parts that should stay visible.
    const isProbe = !!opts?.urlOverride;

    if (!isProbe) {
      // Normal send: reset immediately so the UI shows "submitted" while waiting.
      setParts([]);
      partsRef.current = [];
      setError(undefined);
      setStatus('submitted');
      resetApprovalTracking();
    }

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const fetchBody = opts?.formData || JSON.stringify(body);
      const headers: Record<string, string> = opts?.formData
        ? {} // Let browser set Content-Type for FormData
        : { 'Content-Type': 'application/json' };

      const response = await fetch(targetUrl, {
        method: 'POST',
        headers,
        body: fetchBody,
        signal: controller.signal,
      });

      // 204: no active stream (e.g. /chat/live when no background run is in progress)
      if (response.status === 204) {
        if (!isProbe) setStatus('idle');
        return false;
      }

      if (!response.ok) {
        const text = await response.text().catch(() => response.statusText);
        throw new Error(`HTTP ${response.status}: ${text}`);
      }

      if (!response.body) {
        throw new Error('Response body is null');
      }

      if (isProbe) {
        // Stream confirmed active — reset state now (not on every silent 204 probe).
        // Seed with prior parts when reconnecting to a stream we abandoned on a
        // chat switch, so previously-shown steps (and in-flight tool states)
        // are preserved instead of resetting. The background queue is
        // consume-once, so it only replays chunks from the reconnect point —
        // the seed supplies everything before it.
        const seed = opts?.seedParts ?? [];
        setParts(seed);
        partsRef.current = seed;
        setError(undefined);
        setStatus('submitted');
        resetApprovalTracking();
      }

      // Notify caller (e.g. set isLiveStreamRef) before entering the read loop.
      opts?.onStreamStart?.();
      setStatus('streaming');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentParts: AGUIPart[] = [];
      const pendingApprovalIds = new Set<string>();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // Sync with any out-of-band part mutations (e.g. removeInlineSurface)
        // that may have updated partsRef.current between read() calls.
        currentParts = [...partsRef.current];

        buffer += decoder.decode(value, { stream: true });
        const { events, remainder } = parseSSEBuffer(buffer);
        buffer = remainder;

        for (const event of events) {
          // Track approval requests
          if (event.type === 'CUSTOM' && (event.data.name as string) === 'tool_approval_request') {
            const approval = event.data.value as Record<string, unknown> | undefined;
            const approvalId = approval?.approvalId;
            if (typeof approvalId === 'string' && approvalId.length > 0) {
              pendingApprovalIds.add(approvalId);
            }
          }
          const result = processEvent(event, currentParts, onCustomEvent, onMarkDeferred);
          currentParts = result.parts;

          if (result.error) {
            setError(result.error);
            setStatus('error');
            setParts(currentParts);
            partsRef.current = currentParts;
            onError?.(new Error(result.error), currentParts);
            return true;
          }
        }

        if (events.length > 0) {
          setParts(currentParts);
          partsRef.current = currentParts;
          setPendingApprovalCountSync(pendingApprovalIds.size);
        }
      }

      setStatus('idle');
      onFinish?.(currentParts);
      return true;

    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        // Silent stop (chat switch): discard parts, never finalize.
        if (suppressFinishRef.current) {
          suppressFinishRef.current = false;
          setStatus('idle');
        } else if (!isSteeringRef.current) {
          // If the abort was triggered by steerStream, do nothing here —
          // steerStream owns the status and will call onFinish when done.
          setStatus('idle');
          onFinish?.(partsRef.current);
        }
      } else {
        const errorMsg = (err as Error).message;
        setError(errorMsg);
        setStatus('error');
        onError?.(err as Error, partsRef.current);
      }
      return false;
    }
  }, [resetApprovalTracking, setPendingApprovalCountSync]);

  return { parts, status, error, sendMessage, resumeStream, steerStream, stop, stopSilently, getParts, clearParts, restorePartsFromSeed, removeInlineSurface, resolveApproval, pendingApprovalCount, addApprovalDecision, consumeApprovalDecisions };
}
