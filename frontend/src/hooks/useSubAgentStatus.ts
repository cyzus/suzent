/**
 * useSubAgentStatus — subscribes to /subagents/stream (SSE) to track
 * sub-agents in real-time. Used by StatusBar, ChatWindow and the sidebar.
 *
 * A single EventSource is shared across all hook instances via module-level
 * state. The connection is opened on first subscriber and closed when the
 * last subscriber unmounts.
 *
 * Two views of the same stream are exposed. `activeTasks` is only what is
 * running right now (the status bar's concern). `taskStates` also keeps the
 * terminal update that ended each run, because dropping it on completion is
 * what used to leave the sidebar showing "running" until someone reloaded it.
 */
import { useEffect, useState } from 'react';
import { getApiBase } from '../lib/api';
import {
  SubAgentSpawnedPayload,
  SubAgentCompletedPayload,
  SubAgentFailedPayload,
} from '../lib/streamEvents';
import { isSubAgentTerminal, SubAgentStatus } from '../components/chat/subAgentStatus';

export interface SubAgentSummary {
  task_id: string;
  parent_chat_id: string;
  chat_id: string;
  description: string;
  tools_allowed: string[];
  model_override?: string | null;
  status: SubAgentStatus;
  started_at: string | null;
  finished_at?: string | null;
  result_summary?: string | null;
  error?: string | null;
  inherit_context?: boolean;
  isolation?: string;
  worktree_path?: string | null;
  worktree_branch?: string | null;
}

interface SubAgentStatusState {
  activeTasks: SubAgentSummary[];
  /** Latest known state of every task seen this session, terminal ones included. */
  taskStates: Record<string, SubAgentSummary>;
  /** Notify the hook about a newly spawned task (from parent chat SSE event) */
  onSpawned: (payload: SubAgentSpawnedPayload) => void;
  /** Notify the hook that a task completed (from parent chat SSE event) */
  onCompleted: (payload: SubAgentCompletedPayload) => void;
  /** Notify the hook that a task failed (from parent chat SSE event) */
  onFailed: (payload: SubAgentFailedPayload) => void;
}

// ─── Module-level shared EventSource state ───────────────────────────────────

let _activeTasks: SubAgentSummary[] = [];
let _taskStates: Record<string, SubAgentSummary> = {};
const _listeners: Set<() => void> = new Set();
let _es: EventSource | null = null;

function notify() {
  _listeners.forEach((fn) => fn());
}

function _recordState(task: SubAgentSummary) {
  _taskStates = { ..._taskStates, [task.task_id]: { ..._taskStates[task.task_id], ...task } };
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

function _applyTask(task: SubAgentSummary) {
  _recordState(task);
  if (isSubAgentTerminal(task.status)) {
    _activeTasks = _activeTasks.filter((a) => a.task_id !== task.task_id);
  } else {
    _upsertTask(task);
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
        _activeTasks.forEach(_recordState);
        notify();
      } else if (msg.event === 'task_update') {
        _applyTask(msg.task as SubAgentSummary);
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
      _taskStates = {};
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
      const task: SubAgentSummary = {
        task_id: payload.task_id,
        parent_chat_id: payload.parent_chat_id,
        chat_id: payload.chat_id,
        description: payload.description,
        tools_allowed: payload.tools_allowed,
        model_override: payload.model_override ?? null,
        status: 'running',
        started_at: new Date().toISOString(),
      };
      _activeTasks = [..._activeTasks, task];
      _recordState(task);
      notify();
    }
  };

  const finish = (taskId: string, patch: Partial<SubAgentSummary>) => {
    const known = _taskStates[taskId] ?? _activeTasks.find((t) => t.task_id === taskId);
    if (known) _recordState({ ...known, ...patch } as SubAgentSummary);
    _activeTasks = _activeTasks.filter((t) => t.task_id !== taskId);
    notify();
  };

  const onCompleted = (payload: SubAgentCompletedPayload) => {
    finish(payload.task_id, {
      status: 'completed',
      finished_at: new Date().toISOString(),
      result_summary: payload.result_summary,
    });
  };

  const onFailed = (payload: SubAgentFailedPayload) => {
    finish(payload.task_id, {
      status: 'failed',
      finished_at: new Date().toISOString(),
      error: payload.error,
    });
  };

  return {
    activeTasks: _activeTasks,
    taskStates: _taskStates,
    onSpawned,
    onCompleted,
    onFailed,
  };
}
