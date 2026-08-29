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

/** @returns false when the update was rejected as stale. */
function _recordState(task: SubAgentSummary): boolean {
  const previous = _taskStates[task.task_id];
  // A run does not un-finish. The stream and the poll below both write here,
  // and either can arrive late or replay an older frame; whichever source saw
  // the run end wins, so a settled task is never dragged back to 'running'.
  if (previous && isSubAgentTerminal(previous.status) && !isSubAgentTerminal(task.status)) {
    return false;
  }
  _taskStates = { ..._taskStates, [task.task_id]: { ...previous, ...task } };
  return true;
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
  const accepted = _recordState(task);
  // Branch on what the store settled on, not on what arrived. A stale 'running'
  // frame rejected above is still a finished run: adding it back to the active
  // list would strand it there -- visible as live in the status bar and
  // sidebar, yet skipped by the poll, which reads the (terminal) task state.
  const settled = _taskStates[task.task_id]?.status ?? task.status;
  if (!accepted || isSubAgentTerminal(settled)) {
    _activeTasks = _activeTasks.filter((a) => a.task_id !== task.task_id);
  } else {
    _upsertTask(task);
  }
}

// ─── Shared fallback poll ────────────────────────────────────────────────────
//
// The stream is the fast path but not a complete one: it can end before a run
// does, and it only carries tasks seen *this session* -- so a chat reopened on
// a sub-agent that is still working learns nothing from it until something
// changes. A poll covers that gap.
//
// One poll, not one per block. Each transcript block used to run its own 3s
// timer, so a chat showing ten sub-agents made ten independent requests every
// three seconds and stopped covering any of them the moment its block
// unmounted. Blocks now register interest and this resolves them together.

const SUBAGENT_POLL_INTERVAL_MS = 3000;
const _watched = new Set<string>();
let _pollTimer: ReturnType<typeof setInterval> | null = null;

function _unresolvedIds(): string[] {
  return [..._watched].filter((id) => !isSubAgentTerminal(_taskStates[id]?.status));
}

async function _pollUnresolved() {
  const ids = _unresolvedIds();
  if (ids.length === 0) {
    _stopPolling();
    return;
  }

  const results = await Promise.all(
    ids.map(async (id) => {
      try {
        const res = await fetch(`${getApiBase()}/subagents/${id}`);
        if (!res.ok) return null;
        const task = (await res.json())?.task as SubAgentSummary | undefined;
        return task?.task_id ? task : null;
      } catch {
        // Backend restarting or offline; the next tick retries.
        return null;
      }
    })
  );

  const seen = results.filter((task): task is SubAgentSummary => task !== null);
  if (seen.length === 0) return;
  seen.forEach(_applyTask);
  notify();
}

function _startPolling() {
  if (_pollTimer || _unresolvedIds().length === 0) return;
  _pollTimer = setInterval(() => {
    void _pollUnresolved();
  }, SUBAGENT_POLL_INTERVAL_MS);
  void _pollUnresolved();
}

function _stopPolling() {
  if (_pollTimer) {
    clearInterval(_pollTimer);
    _pollTimer = null;
  }
}

/**
 * Ask the shared poll to resolve `taskId` until it reaches a terminal state.
 * Returns the unregister function. Safe to call for a task the stream already
 * knows: it is dropped from the poll set as soon as its status settles.
 */
export function watchSubAgentTask(taskId: string): () => void {
  _watched.add(taskId);
  _startPolling();
  return () => {
    _watched.delete(taskId);
    if (_watched.size === 0) _stopPolling();
  };
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
    } catch {
      /* ignore parse errors */
    }
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
      _stopPolling();
      _watched.clear();
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
