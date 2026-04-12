/**
 * useSubAgentStatus — subscribes to /subagents/stream (SSE) to track
 * globally running sub-agents in real-time. Used by StatusBar and ChatWindow.
 *
 * A single EventSource is shared across all hook instances via module-level
 * state. The connection is opened on first subscriber and closed when the
 * last subscriber unmounts.
 */
import { useEffect, useState } from 'react';
import { getApiBase } from '../lib/api';
import {
  SubAgentSpawnedPayload,
  SubAgentCompletedPayload,
  SubAgentFailedPayload,
} from '../lib/streamEvents';

export interface SubAgentSummary {
  task_id: string;
  parent_chat_id: string;
  chat_id: string;
  description: string;
  tools_allowed: string[];
  status: 'queued' | 'running' | 'completed' | 'failed';
  started_at: string | null;
}

interface SubAgentStatusState {
  activeTasks: SubAgentSummary[];
  /** Notify the hook about a newly spawned task (from parent chat SSE event) */
  onSpawned: (payload: SubAgentSpawnedPayload) => void;
  /** Notify the hook that a task completed (from parent chat SSE event) */
  onCompleted: (payload: SubAgentCompletedPayload) => void;
  /** Notify the hook that a task failed (from parent chat SSE event) */
  onFailed: (payload: SubAgentFailedPayload) => void;
}

// ─── Module-level shared EventSource state ───────────────────────────────────

let _activeTasks: SubAgentSummary[] = [];
const _listeners: Set<() => void> = new Set();
let _es: EventSource | null = null;

function notify() {
  _listeners.forEach((fn) => fn());
}

function _upsertTask(task: SubAgentSummary) {
  const idx = _activeTasks.findIndex((t) => t.task_id === task.task_id);
  if (idx >= 0) {
    _activeTasks = [..._activeTasks];
    _activeTasks[idx] = task;
  } else {
    _activeTasks = [..._activeTasks, task];
  }
}

function _openEventSource() {
  if (_es) return;
  _es = new EventSource(`${getApiBase()}/subagents/stream`);

  _es.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      if (msg.event === 'snapshot') {
        _activeTasks = msg.tasks ?? [];
        notify();
      } else if (msg.event === 'task_update') {
        const t: SubAgentSummary = msg.task;
        if (t.status === 'completed' || t.status === 'failed') {
          _activeTasks = _activeTasks.filter((a) => a.task_id !== t.task_id);
        } else {
          _upsertTask(t);
        }
        notify();
      }
    } catch { /* ignore parse errors */ }
  };

  _es.onerror = () => {
    // EventSource auto-reconnects per spec; no manual action needed.
  };
}

function _closeEventSource() {
  _es?.close();
  _es = null;
}

function subscribe(fn: () => void) {
  _listeners.add(fn);
  _openEventSource();
  return () => {
    _listeners.delete(fn);
    if (_listeners.size === 0) {
      _closeEventSource();
      _activeTasks = [];
    }
  };
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useSubAgentStatus(): SubAgentStatusState {
  const [, forceUpdate] = useState(0);

  useEffect(() => {
    const unsub = subscribe(() => forceUpdate((n) => n + 1));
    return unsub;
  }, []);

  // Optimistic mutations from the parent chat SSE stream.
  // These apply immediately; the subagent SSE stream will confirm shortly after.
  const onSpawned = (payload: SubAgentSpawnedPayload) => {
    const existing = _activeTasks.find((t) => t.task_id === payload.task_id);
    if (!existing) {
      _activeTasks = [
        ..._activeTasks,
        {
          task_id: payload.task_id,
          parent_chat_id: payload.parent_chat_id,
          chat_id: payload.chat_id,
          description: payload.description,
          tools_allowed: payload.tools_allowed,
          status: 'running',
          started_at: new Date().toISOString(),
        },
      ];
      notify();
    }
  };

  const onCompleted = (payload: SubAgentCompletedPayload) => {
    _activeTasks = _activeTasks.filter((t) => t.task_id !== payload.task_id);
    notify();
  };

  const onFailed = (payload: SubAgentFailedPayload) => {
    _activeTasks = _activeTasks.filter((t) => t.task_id !== payload.task_id);
    notify();
  };

  return {
    activeTasks: _activeTasks,
    onSpawned,
    onCompleted,
    onFailed,
  };
}
