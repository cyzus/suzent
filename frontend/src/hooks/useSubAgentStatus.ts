/**
 * useSubAgentStatus — polls /subagents/active every 3 seconds to track
 * globally running sub-agents. Used by StatusBar and ChatWindow.
 */
import { useEffect, useRef, useState } from 'react';
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
  /** Notify the hook about a newly spawned task (from SSE event) */
  onSpawned: (payload: SubAgentSpawnedPayload) => void;
  /** Notify the hook that a task completed (from SSE event) */
  onCompleted: (payload: SubAgentCompletedPayload) => void;
  /** Notify the hook that a task failed (from SSE event) */
  onFailed: (payload: SubAgentFailedPayload) => void;
}

const POLL_INTERVAL_MS = 3000;

let _activeTasks: SubAgentSummary[] = [];
const _listeners: Set<() => void> = new Set();

function notify() {
  _listeners.forEach((fn) => fn());
}

async function pollActive() {
  try {
    const res = await fetch(`${getApiBase()}/subagents/active`);
    if (!res.ok) return;
    const data = await res.json();
    _activeTasks = data.tasks ?? [];
    notify();
  } catch { /* ignore */ }
}

// Module-level polling interval (shared across hook instances)
let _pollTimer: ReturnType<typeof setInterval> | null = null;
let _subscriberCount = 0;

function subscribe(fn: () => void) {
  _listeners.add(fn);
  _subscriberCount++;
  if (!_pollTimer) {
    pollActive();
    _pollTimer = setInterval(pollActive, POLL_INTERVAL_MS);
  }
  return () => {
    _listeners.delete(fn);
    _subscriberCount--;
    if (_subscriberCount === 0 && _pollTimer) {
      clearInterval(_pollTimer);
      _pollTimer = null;
    }
  };
}

export function useSubAgentStatus(): SubAgentStatusState {
  const [, forceUpdate] = useState(0);

  useEffect(() => {
    const unsub = subscribe(() => forceUpdate((n) => n + 1));
    return unsub;
  }, []);

  const onSpawned = (payload: SubAgentSpawnedPayload) => {
    // Optimistically add to active list
    const existing = _activeTasks.find((t) => t.task_id === payload.task_id);
    if (!existing) {
      _activeTasks = [
        ..._activeTasks,
        {
          task_id: payload.task_id,
          parent_chat_id: '',
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
    // Let next poll refresh the full list
    pollActive();
  };

  const onFailed = (payload: SubAgentFailedPayload) => {
    _activeTasks = _activeTasks.filter((t) => t.task_id !== payload.task_id);
    notify();
    pollActive();
  };

  return {
    activeTasks: _activeTasks,
    onSpawned,
    onCompleted,
    onFailed,
  };
}
