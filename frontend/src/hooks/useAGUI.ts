/**
 * Custom React hook for AG-UI protocol streaming.
 *
 * Replaces Vercel AI SDK's useChat with a lightweight SSE client
 * that parses AG-UI events and builds up parts-based state.
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import type { A2UISurface } from '../types/a2ui';
import type { AGUIPart, AcpPermissionRequest, ApprovalRememberScope } from '../types/agui';
import type { CitationSource } from '../lib/streamEvents';
import { recoverableStream } from '../lib/recoverableStream';

// ── Types ────────────────────────────────────────────────────────────
export type AGUIStatus = 'idle' | 'submitted' | 'streaming' | 'error';
export type { AGUIPart, AcpPermissionRequest, ApprovalRememberScope };

interface UseAGUIOptions {
  url: string;
  onFinish?: (parts: AGUIPart[], persistence?: { confirmed: boolean }) => void | Promise<void>;
  onCustomEvent?: (name: string, value: unknown) => void;
  onMarkDeferred?: (surfaceId: string) => void;
  onError?: (error: Error, parts: AGUIPart[]) => void;
}

interface UseAGUIReturn {
  parts: AGUIPart[];
  status: AGUIStatus;
  error: string | undefined;
  sendMessage: (
    body: Record<string, unknown>,
    opts?: {
      urlOverride?: string;
      onStreamStart?: () => void;
      seedParts?: AGUIPart[];
    }
  ) => Promise<boolean>;
  stop: () => void;
  /** Abort the active stream without triggering onFinish (used on chat switch) */
  stopSilently: () => void;
  /** Read the current parts synchronously (e.g. to snapshot before switching chats) */
  getParts: () => AGUIPart[];
  /**
   * The run the live stream is on, so a caller can name it back to the backend
   * (a stop that names its run cannot cancel the turn that replaced it). Falls
   * back to the token this client minted for the turn, which is all there is
   * between asking for a turn and seeing its first protocol frame.
   */
  getRunId: () => string | undefined;
  /**
   * Name the turn about to be asked for, and return that name to put in the
   * request body. Callers that POST a turn themselves (/chat/send and friends)
   * must call this, or a stop raised before the first frame has no run to name.
   */
  mintRunToken: () => string;
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
    actionId?: string,
    feedback?: string
  ) => boolean;
  /** Get accumulated approval decisions and clear the buffer */
  consumeApprovalDecisions: () => Array<{
    approvalId: string;
    toolCallId: string;
    approved: boolean;
    remember?: ApprovalRememberScope;
    toolName?: string;
    args?: Record<string, unknown> | null;
    actionId?: string;
    feedback?: string;
  }>;
}

// ── SSE Parser ───────────────────────────────────────────────────────

interface ParsedSSEEvent {
  type: string;
  data: Record<string, unknown>;
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

function findLastToolPartIndex(parts: AGUIPart[], toolCallId: string): number {
  for (let index = parts.length - 1; index >= 0; index -= 1) {
    if (parts[index].type === 'tool' && parts[index].toolCallId === toolCallId) {
      return index;
    }
  }
  return -1;
}

export function processEvent(
  event: ParsedSSEEvent,
  parts: AGUIPart[],
  onCustomEvent?: (name: string, value: unknown) => void,
  onMarkDeferred?: (surfaceId: string) => void
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

    // AG-UI renamed the thinking family to REASONING_* in ag-ui-protocol
    // 0.1.13. pydantic-ai emits whichever family the negotiated version calls
    // for, so both have to map onto the same reasoning part -- when only the
    // legacy names were handled, every reasoning event from the new family was
    // dropped and the message sat in its "thinking" state, hiding the whole
    // stream, until the first answer token arrived.
    case 'THINKING_START':
    case 'THINKING_TEXT_MESSAGE_START':
    case 'REASONING_START':
    case 'REASONING_MESSAGE_START': {
      // Only push a new reasoning part if the last one isn't an empty reasoning part
      const lastPart = next[next.length - 1];
      if (
        !lastPart ||
        lastPart.type !== 'reasoning' ||
        (lastPart.text && lastPart.text.length > 0)
      ) {
        next.push({ type: 'reasoning', text: '' });
      }
      break;
    }

    // REASONING_MESSAGE_CHUNK is the new family's combined start+content
    // event, so it has to open a part when none is streaming yet.
    case 'THINKING_TEXT_MESSAGE_CONTENT':
    case 'REASONING_MESSAGE_CONTENT':
    case 'REASONING_MESSAGE_CHUNK': {
      const delta = (data.delta as string) || '';
      let appended = false;
      for (let i = next.length - 1; i >= 0; i--) {
        if (next[i].type === 'reasoning') {
          next[i] = { ...next[i], text: (next[i].text || '') + delta };
          appended = true;
          break;
        }
      }
      if (!appended) next.push({ type: 'reasoning', text: delta });
      break;
    }

    // REASONING_ENCRYPTED_VALUE carries the provider's opaque reasoning blob
    // for history replay, so it has nothing displayable either.
    case 'THINKING_TEXT_MESSAGE_END':
    case 'THINKING_END':
    case 'REASONING_MESSAGE_END':
    case 'REASONING_END':
    case 'REASONING_ENCRYPTED_VALUE':
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

      if (name === 'tool_permission_decision') {
        const decision = value as NonNullable<AGUIPart['permissionDecision']>;
        const tcId = decision.toolCallId;
        const existingIndex = findLastToolPartIndex(next, tcId);
        if (existingIndex >= 0) {
          next[existingIndex] = {
            ...next[existingIndex],
            toolName: decision.toolName || next[existingIndex].toolName,
            permissionDecision: decision,
          };
        } else {
          next.push({
            type: 'tool',
            toolCallId: tcId,
            toolName: decision.toolName || 'unknown',
            args: '',
            state: 'running',
            permissionDecision: decision,
          });
        }
      } else if (name === 'tool_permission_resolution') {
        const resolution = value as NonNullable<AGUIPart['permissionResolution']>;
        const tcId = resolution.toolCallId;
        const existingIndex = findLastToolPartIndex(next, tcId);
        if (existingIndex >= 0) {
          next[existingIndex] = {
            ...next[existingIndex],
            permissionResolution: resolution,
          };
        } else {
          next.push({
            type: 'tool',
            toolCallId: tcId,
            toolName: 'unknown',
            args: '',
            state: 'running',
            permissionResolution: resolution,
          });
        }
      } else if (name === 'acp.permission_request') {
        // An external ACP agent is blocked waiting for a decision. Surface it
        // as its own part; it is answered via the ACP endpoint, not the native
        // resume_approvals flow.
        const req = value as AcpPermissionRequest;
        if (req?.requestId) {
          const existing = next.findIndex((p) => p.acpPermission?.requestId === req.requestId);
          if (existing >= 0) next[existing] = { ...next[existing], acpPermission: req };
          else next.push({ type: 'acp-permission', acpPermission: req });
        }
      } else if (name === 'acp.session_reset') {
        const notice = value as Record<string, unknown>;
        next.push({
          type: 'acp-notice',
          acpNotice: {
            kind: 'session_reset',
            agentId: notice.agentId as string | undefined,
            requestedSessionId: notice.requestedSessionId as string | undefined,
            sessionId: notice.sessionId as string | undefined,
            reason: notice.reason as string | undefined,
          },
        });
      } else if (name === 'tool_approval_request') {
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
              permission: approval.decision as AGUIPart['permission'],
              // Fill in name/args if not yet present (approval may arrive before tool_call_start)
              toolName: next[i].toolName || (approval.toolName as string) || 'unknown',
              args:
                next[i].args ||
                (approval.args
                  ? typeof approval.args === 'string'
                    ? approval.args
                    : JSON.stringify(approval.args, null, 2)
                  : ''),
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
              ? typeof approval.args === 'string'
                ? (approval.args as string)
                : JSON.stringify(approval.args, null, 2)
              : '',
            state: 'approval-requested',
            approvalId,
            permission: approval.decision as AGUIPart['permission'],
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
              approvalId: undefined, // clear approval badge
            };
            found = true;
            break;
          }
        }
        if (!found) {
          // Fallback: the toolCallId can differ between the streamed
          // TOOL_CALL_START and the deferred recovery result (auto-approved tools
          // run through the deferred path), so match by name on a tool still
          // awaiting a result — 'approval-requested' OR 'running' with no output.
          // Only do this when there is exactly ONE such candidate: with multiple
          // parallel same-name tools, name-matching is ambiguous and could attach
          // this result to the wrong tool's part. When ambiguous, fall through to
          // pushing a new part — a correct extra block beats a corrupted one.
          const candidateIdxs: number[] = [];
          for (let i = next.length - 1; i >= 0; i--) {
            const p = next[i];
            if (
              p.type === 'tool' &&
              (p.toolName || 'unknown') === toolName &&
              (p.state === 'approval-requested' || (p.state === 'running' && !p.output))
            ) {
              candidateIdxs.push(i);
            }
          }
          if (candidateIdxs.length === 1) {
            const i = candidateIdxs[0];
            const p = next[i];
            next[i] = {
              ...p,
              toolCallId: p.toolCallId || tcId,
              state: resultData.status === 'executed' ? 'completed' : 'error',
              output,
              argsReplayPending: false,
              approvalId: undefined,
            };
            found = true;
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
      } else if (name === 'citation_sources') {
        // Citable sources registered during this run. Stored as a single part so
        // they travel with the message (persist + reload) and so badges can
        // resolve src ids to titles/urls. Merge in case the event fires twice.
        const payload = value as { sources?: CitationSource[] };
        const incoming = Array.isArray(payload?.sources) ? payload.sources : [];
        if (incoming.length > 0) {
          const idx = next.findIndex((p) => p.type === 'citation-sources');
          if (idx >= 0) {
            const existing = next[idx].citationSources || [];
            const byId = new Map(existing.map((s) => [s.id, s]));
            for (const s of incoming) byId.set(s.id, s);
            next[idx] = { ...next[idx], citationSources: Array.from(byId.values()) };
          } else {
            next.push({ type: 'citation-sources', citationSources: incoming });
          }
        }
      } else if (name === 'a2ui.resolved') {
        const resolved = value as { surfaceId?: string };
        return {
          parts: next.filter(
            (part) => part.type !== 'a2ui' || part.surface?.id !== resolved.surfaceId
          ),
        };
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
      // A user stop arrives on this frame, but it is an expected ending: the
      // backend keeps the partial reply and persists it, then closes the
      // stream with STREAM_END{persisted:true}. Reporting it as an error
      // would abandon the stream just short of that confirmation.
      if (data.code === 'stream_stopped') break;
      return { parts: next, error: (data.message as string) || 'Unknown error' };
    }

    case 'error': {
      const message = data.message ?? data.data ?? data.error;
      return {
        parts: next,
        error: typeof message === 'string' && message ? message : 'Unknown error',
      };
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
  // Set to true by stopSilently() so the next abort skips onFinish entirely.
  // Used when abandoning a live background stream on chat switch — the backend
  // persists the content, so the frontend must NOT addMessage (which would
  // misroute the parts to whatever chat is now being viewed).
  const suppressFinishRef = useRef(false);
  // Keep a ref to latest parts so onFinish gets the final value
  const partsRef = useRef<AGUIPart[]>([]);
  // The run the live stream is on; cleared when a new one starts.
  const runIdRef = useRef<string | undefined>(undefined);
  // The name this client gave the turn it last asked for. The backend stores it
  // on the run's replay, so a stop can name the run before the stream has told
  // us the run_id the backend assigned it.
  const clientRunTokenRef = useRef<string | undefined>(undefined);
  // Publishing a token delta straight to React state re-renders the whole chat
  // view; at streaming rates that starves the main thread and scrolling crawls.
  // `publishParts` keeps `partsRef` exact and synchronous but coalesces the
  // render into one update per frame. While a flush is queued the ref is ahead
  // of `parts`, so it must not be rewound to the state value here.
  const flushFrameRef = useRef<number | null>(null);
  if (flushFrameRef.current === null) {
    partsRef.current = parts;
  }

  const cancelPartsFlush = useCallback(() => {
    if (flushFrameRef.current !== null) {
      cancelAnimationFrame(flushFrameRef.current);
      flushFrameRef.current = null;
    }
  }, []);

  /**
   * Record the newest parts. Renders are batched to the next animation frame
   * unless `immediate`, which every terminal path (error, finish, abort) uses so
   * the last state of a turn is never left sitting in a cancelled frame.
   */
  const publishParts = useCallback(
    (next: AGUIPart[], immediate = false) => {
      partsRef.current = next;
      if (immediate) {
        cancelPartsFlush();
        setParts(next);
        return;
      }
      if (flushFrameRef.current !== null) return;
      flushFrameRef.current = requestAnimationFrame(() => {
        flushFrameRef.current = null;
        setParts(partsRef.current);
      });
    },
    [cancelPartsFlush]
  );

  useEffect(() => cancelPartsFlush, [cancelPartsFlush]);

  // Pending approval tracking
  const [pendingApprovalCount, setPendingApprovalCount] = useState(0);
  const pendingApprovalCountRef = useRef(0);
  const approvalDecisionsRef = useRef<
    Array<{
      approvalId: string;
      toolCallId: string;
      approved: boolean;
      remember?: ApprovalRememberScope;
      toolName?: string;
      args?: Record<string, unknown> | null;
      actionId?: string;
      feedback?: string;
    }>
  >([]);

  // Stable refs for callbacks to avoid re-creating sendMessage
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const clearParts = useCallback(() => {
    publishParts([], true);
  }, [publishParts]);

  const setPendingApprovalCountSync = useCallback((count: number) => {
    pendingApprovalCountRef.current = count;
    setPendingApprovalCount((prev) => (prev === count ? prev : count));
  }, []);

  const resetApprovalTracking = useCallback(() => {
    setPendingApprovalCountSync(0);
    approvalDecisionsRef.current = [];
  }, [setPendingApprovalCountSync]);

  const removeInlineSurface = useCallback(
    (surfaceId: string) => {
      publishParts(
        partsRef.current.filter(
          (p) => !(p.type === 'a2ui' && (p.surface as A2UISurface)?.id === surfaceId)
        ),
        true
      );
    },
    [publishParts]
  );

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
  const getRunId = useCallback(() => runIdRef.current ?? clientRunTokenRef.current, []);
  const mintRunToken = useCallback(() => {
    const token =
      globalThis.crypto?.randomUUID?.() ??
      `run-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    clientRunTokenRef.current = token;
    runIdRef.current = undefined;
    return token;
  }, []);

  const restorePartsFromSeed = useCallback(
    (seed: AGUIPart[]) => {
      publishParts(seed, true);
      setStatus('idle');
      const approvalCount = seed.filter(
        (p) => p.type === 'tool' && p.state === 'approval-requested'
      ).length;
      setPendingApprovalCountSync(approvalCount);
    },
    [publishParts, setPendingApprovalCountSync]
  );

  // Optimistically update a tool part's state when user approves/denies
  // so buttons disappear instantly (no waiting for backend round-trip)
  const resolveApproval = useCallback(
    (approvalId: string, approved: boolean) => {
      publishParts(
        partsRef.current.map((p) =>
          p.type === 'tool' && p.approvalId === approvalId
            ? {
                ...p,
                state: approved ? ('running' as const) : ('error' as const),
                approvalId: undefined,
              }
            : p
        ),
        true
      );
    },
    [publishParts]
  );

  // Track pending approval count from parts
  const addApprovalDecision = useCallback(
    (
      approvalId: string,
      toolCallId: string,
      approved: boolean,
      remember?: ApprovalRememberScope,
      toolName?: string,
      args?: Record<string, unknown> | null,
      actionId?: string,
      feedback?: string
    ): boolean => {
      const nextDecision = {
        approvalId,
        toolCallId,
        approved,
        remember,
        toolName,
        args,
        actionId,
        feedback,
      };
      const existingIdx = approvalDecisionsRef.current.findIndex(
        (d) => d.approvalId === approvalId
      );
      if (existingIdx >= 0) {
        approvalDecisionsRef.current[existingIdx] = nextDecision;
      } else {
        approvalDecisionsRef.current.push(nextDecision);
      }
      const requiredDecisions = pendingApprovalCountRef.current;
      return requiredDecisions > 0 && approvalDecisionsRef.current.length >= requiredDecisions;
    },
    []
  );

  const consumeApprovalDecisions = useCallback(() => {
    const decisions = [...approvalDecisionsRef.current];
    resetApprovalTracking();
    return decisions;
  }, [resetApprovalTracking]);

  const sendMessage = useCallback(
    async (
      body: Record<string, unknown>,
      opts?: {
        urlOverride?: string;
        onStreamStart?: () => void;
        seedParts?: AGUIPart[];
      }
    ): Promise<boolean> => {
      const { url, onFinish, onCustomEvent, onMarkDeferred, onError } = optionsRef.current;
      const targetUrl = opts?.urlOverride ?? url;
      // For live-stream probes (urlOverride) we defer the state reset until we know
      // there is actually an active stream — this prevents every 204 probe from
      // clearing streaming parts that should stay visible.
      const isProbe = !!opts?.urlOverride;
      // Name the turn before asking for it: the Stop button goes live now, not
      // when the first protocol frame arrives with the backend's run_id. A probe
      // re-attaches to a turn that already has a name, so it mints nothing.
      const requestBody = isProbe ? body : { ...body, client_run_token: mintRunToken() };

      if (!isProbe) {
        // Normal send: reset immediately so the UI shows "submitted" while waiting.
        publishParts([], true);
        setError(undefined);
        setStatus('submitted');
        resetApprovalTracking();
      }

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const liveUrl = isProbe ? targetUrl : targetUrl.replace(/\/chat$/, '/chat/live');
        const observeBody = isProbe ? requestBody : { chat_id: requestBody.chat_id, wait_ms: 8000 };
        let started = false;
        for await (const batch of recoverableStream(
          liveUrl,
          observeBody,
          controller.signal,
          () => {
            started = true;
            setError(undefined);
            resetApprovalTracking();
            opts?.onStreamStart?.();
            setStatus('streaming');
          },
          isProbe ? undefined : { url: targetUrl, body: requestBody }
        )) {
          runIdRef.current = batch.runId;
          let currentParts = batch.reset ? [] : [...partsRef.current];
          if (batch.reset) resetApprovalTracking();
          for (const data of batch.events) {
            const result = processEvent(
              { type: data.type, data },
              currentParts,
              onCustomEvent,
              onMarkDeferred
            );
            currentParts = result.parts;
            if (result.error) {
              publishParts(currentParts, true);
              throw new Error(result.error);
            }
          }
          publishParts(currentParts, batch.reset);
          setPendingApprovalCountSync(
            currentParts.filter(
              (part) =>
                part.type === 'tool' && part.state === 'approval-requested' && !!part.approvalId
            ).length
          );
        }
        if (started) {
          publishParts(partsRef.current, true);
          setStatus('idle');
          await onFinish?.(partsRef.current, { confirmed: true });
        }
        return started;
      } catch (err) {
        if ((err as Error).name === 'AbortError') {
          // Silent stop (chat switch): discard parts, never finalize.
          if (suppressFinishRef.current) {
            suppressFinishRef.current = false;
            setStatus('idle');
          } else {
            publishParts(partsRef.current, true);
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
    },
    [mintRunToken, publishParts, resetApprovalTracking, setPendingApprovalCountSync]
  );

  return {
    parts,
    status,
    error,
    sendMessage,
    stop,
    stopSilently,
    getParts,
    getRunId,
    mintRunToken,
    clearParts,
    restorePartsFromSeed,
    removeInlineSurface,
    resolveApproval,
    pendingApprovalCount,
    addApprovalDecision,
    consumeApprovalDecisions,
  };
}
