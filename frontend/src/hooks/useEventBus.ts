/**
 * useEventBus — subscribes to /events/stream (SSE) to track which background
 * chat streams are currently active in real-time.
 *
 * A single EventSource is shared across all hook instances via module-level
 * state. The connection is opened on first subscriber and closed when the
 * last subscriber unmounts.
 *
 * Bus event shapes:
 *   {"event":"snapshot",      "streams":[...]}   — sent on connect
 *   {"event":"stream_started","chat_id":"..."}
 *   {"event":"stream_ended",  "chat_id":"..."}
 *   {"event":"chunk",         "chat_id":"...", "data":"data: {...}\n\n"}
 */
import { useEffect, useState } from 'react';
import { getApiBase } from '../lib/api';

// ─── Module-level shared state ────────────────────────────────────────────────

let _activeStreams: Set<string> = new Set();
const _listeners: Set<() => void> = new Set();
let _es: EventSource | null = null;

// Per-chat chunk handlers: chat_id → set of handlers
type ChunkHandler = (rawData: string) => void;
const _chunkHandlers: Map<string, Set<ChunkHandler>> = new Map();

// Per-chat stream lifecycle callbacks — called directly from the SSE handler,
// bypassing the React render cycle so there is no frame-delay between
// stream_started arriving and tryConnect() being invoked.
interface StreamEventCallbacks {
  onStart?: () => void;
  onEnd?: () => void;
}
const _streamEventListeners: Map<string, Set<StreamEventCallbacks>> = new Map();

function notify() {
  _listeners.forEach((fn) => fn());
}

function _handleMessage(evt: MessageEvent) {
  try {
    const msg = JSON.parse(evt.data);
    if (msg.event === 'snapshot') {
      _activeStreams = new Set(msg.streams ?? []);
      notify();
    } else if (msg.event === 'stream_started') {
      if (msg.chat_id) {
        _activeStreams = new Set([..._activeStreams, msg.chat_id]);
        notify();
        _streamEventListeners.get(msg.chat_id)?.forEach((cb) => cb.onStart?.());
      }
    } else if (msg.event === 'stream_ended') {
      if (msg.chat_id) {
        _activeStreams = new Set([..._activeStreams].filter((id) => id !== msg.chat_id));
        notify();
        _streamEventListeners.get(msg.chat_id)?.forEach((cb) => cb.onEnd?.());
      }
    } else if (msg.event === 'chunk') {
      if (msg.chat_id && msg.data) {
        const handlers = _chunkHandlers.get(msg.chat_id);
        if (handlers) {
          handlers.forEach((fn) => fn(msg.data as string));
        }
      }
    }
  } catch {
    /* ignore parse errors */
  }
}

function _hasSubscribers(): boolean {
  return _listeners.size > 0 || _chunkHandlers.size > 0 || _streamEventListeners.size > 0;
}

function _openEventSource() {
  if (_es) return;
  _es = new EventSource(`${getApiBase()}/events/stream`);
  _es.onmessage = _handleMessage;
  _es.onerror = () => {
    // EventSource auto-reconnects per spec; no manual action needed.
  };
}

function _closeEventSource() {
  _es?.close();
  _es = null;
}

function subscribe(fn: () => void): () => void {
  _listeners.add(fn);
  _openEventSource();
  return () => {
    _listeners.delete(fn);
    if (!_hasSubscribers()) {
      _closeEventSource();
      _activeStreams = new Set();
    }
  };
}

// ─── Standalone helpers (usable outside React) ────────────────────────────────

/** Returns true if a background stream for this chat is currently active. */
export function isBusStreaming(chatId: string): boolean {
  return _activeStreams.has(chatId);
}

/**
 * Subscribe to stream lifecycle events for a specific chat.
 * Callbacks are invoked directly from the SSE message handler — no React
 * render cycle delay. Safe to call from inside a useEffect.
 * Returns an unsubscribe function.
 */
export function subscribeToStreamEvents(
  chatId: string,
  callbacks: StreamEventCallbacks,
): () => void {
  if (!_streamEventListeners.has(chatId)) {
    _streamEventListeners.set(chatId, new Set());
  }
  _streamEventListeners.get(chatId)!.add(callbacks);
  _openEventSource();
  return () => {
    const set = _streamEventListeners.get(chatId);
    if (set) {
      set.delete(callbacks);
      if (set.size === 0) _streamEventListeners.delete(chatId);
    }
    if (!_hasSubscribers()) _closeEventSource();
  };
}

/**
 * Register a handler to receive raw SSE data strings for a specific chat.
 * Returns an unsubscribe function.
 */
export function subscribeToBusChunks(chatId: string, handler: ChunkHandler): () => void {
  if (!_chunkHandlers.has(chatId)) {
    _chunkHandlers.set(chatId, new Set());
  }
  _chunkHandlers.get(chatId)!.add(handler);
  _openEventSource();
  return () => {
    const set = _chunkHandlers.get(chatId);
    if (set) {
      set.delete(handler);
      if (set.size === 0) _chunkHandlers.delete(chatId);
    }
    if (!_hasSubscribers()) _closeEventSource();
  };
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useEventBus() {
  const [, forceUpdate] = useState(0);

  useEffect(() => {
    const unsub = subscribe(() => forceUpdate((n) => n + 1));
    return unsub;
  }, []);

  return {
    isStreaming: isBusStreaming,
    activeStreams: _activeStreams,
  };
}
